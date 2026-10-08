"""Incremental wire measurements for the capture-v1 transport adapter."""
import json


class StreamMeter:
    """Consume bytes at the timestamp at which the bytes became available."""

    def __init__(self, choice=0):
        self.choice = choice
        self.buffer = bytearray()
        self.lines = []
        self.tokens = []
        self.token_times = []
        self.text = ""
        self.finish_ns = None
        self.done_ns = None
        self.usage = None
        self.error = None

    def feed(self, data, timestamp_ns):
        if self.done_ns is not None or self.error:
            return
        event_timestamp = getattr(self, "pending_since", timestamp_ns)
        self.pending_since = timestamp_ns
        self.buffer.extend(data)
        while b"\n" in self.buffer:
            pos = self.buffer.index(10)
            line = bytes(self.buffer[:pos]).removesuffix(b"\r")
            del self.buffer[:pos + 1]
            if line:
                self.lines.append(line)
            else:
                self._event(event_timestamp)
                self.lines = []
                if self.done_ns is not None or self.error:
                    self.buffer.clear()
                    break

    def _event(self, timestamp_ns):
        data, event_type = [], "message"
        for line in self.lines:
            if line.startswith(b":"):
                continue
            field, _, value = line.partition(b":")
            if value.startswith(b" "):
                value = value[1:]
            if field == b"data":
                data.append(value)
            elif field == b"event":
                try:
                    event_type = value.decode("utf-8")
                except UnicodeError:
                    self.error = "invalid_event"
                    return
        if not data:
            return
        payload = b"\n".join(data)
        if payload == b"[DONE]":
            self.done_ns = timestamp_ns
            if self.finish_ns is None:
                self.error = "missing_finish"
            if self.usage is not None and self.usage < len(self.tokens):
                self.error = "usage_mismatch"
            return
        try:
            obj = json.loads(payload)
            if event_type == "error" or "error" in obj:
                self.error = "server_error"
                return
            usage = obj.get("usage", {}).get("choice_tokens", {})
            if str(self.choice) in usage:
                count = usage[str(self.choice)]
                if type(count) is not int or count < 0:
                    raise ValueError("invalid token usage")
                if self.usage is not None and self.usage != count:
                    raise ValueError("conflicting token usage")
                self.usage = count
            for choice in obj.get("choices", [])[:1]:
                if choice.get("index") != self.choice:
                    continue
                delta = choice.get("delta", {})
                ids = delta.get("token_ids", [])
                content = delta.get("content") or ""
                if not isinstance(ids, list) or any(type(x) is not int or x < 0 for x in ids):
                    raise ValueError("invalid generated token ids")
                if not isinstance(content, str):
                    raise ValueError("invalid content")
                if self.finish_ns is not None and (ids or content):
                    raise ValueError("content after finish")
                self.tokens.extend(ids)
                self.token_times.extend([timestamp_ns] * len(ids))
                self.text += content
                if choice.get("finish_reason") is not None:
                    self.finish_ns = timestamp_ns
        except (ValueError, TypeError, AttributeError, UnicodeError):
            self.error = "invalid_event"

    def snapshot(self):
        first = self.token_times[0] if self.token_times else None
        last = self.token_times[-1] if self.token_times else None
        return {
            "tokens": list(self.tokens), "text": self.text,
            "first_token_ns": first, "last_token_ns": last,
            "finish_ns": self.finish_ns, "done_ns": self.done_ns,
            "tpot_ns": (last - first) / (len(self.tokens) - 1) if len(self.tokens) > 1 else None,
            "error": self.error,
        }
