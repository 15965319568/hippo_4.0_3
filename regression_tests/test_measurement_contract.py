"""Small executable examples; the source contracts define the complete scope."""
import json
from pathlib import Path

import pytest
from genai_perf.profile_data_parser import LLMProfileDataParser
from genai_perf.release_audit.stream import StreamMeter
from genai_perf.goodput_calculator.llm_goodput_calculator import LLMGoodputCalculator


def event(choices):
    return ("data: " + json.dumps({"choices": choices}, ensure_ascii=False) + "\r\n\r\n").encode()


def test_first_token_waits_for_event_delimiter():
    meter = StreamMeter()
    data = event([{"index": 0, "delta": {"token_ids": [7], "content": "你"}}])
    meter.feed(data[:-1], 100)
    assert meter.snapshot()["first_token_ns"] is None
    meter.feed(data[-1:], 200)
    assert meter.snapshot()["first_token_ns"] == 200
    assert meter.snapshot()["text"] == "你"


def test_selected_choice_and_simultaneous_tokens():
    meter = StreamMeter()
    meter.feed(event([{"index": 1, "delta": {"token_ids": [9], "content": "wrong"}},
                      {"index": 0, "delta": {"token_ids": [2, 2], "content": "ok"}}]), 17)
    assert meter.snapshot()["tokens"] == [2, 2]
    assert meter.snapshot()["tpot_ns"] == 0


def test_usage_after_finish_is_not_incremental_tokens():
    meter = StreamMeter()
    meter.feed(event([{"index": 0, "delta": {"token_ids": [4], "content": "x"}, "finish_reason": "stop"}]), 10)
    meter.feed(b'data: {"choices":[],"usage":{"choice_tokens":{"0":1}}}\n\ndata: [DONE]\n\n', 30)
    assert meter.snapshot()["done_ns"] == 30
    assert meter.snapshot()["last_token_ns"] == 10
    assert meter.snapshot()["error"] is None


def test_usage_mismatch_fails():
    meter = StreamMeter()
    meter.feed(event([{"index": 0, "delta": {"token_ids": [4]}, "finish_reason": "stop"}]), 10)
    meter.feed(b'data: {"usage":{"choice_tokens":{"0":3}}}\n\ndata: [DONE]\n\n', 30)
    assert meter.snapshot()["error"]


def make_profile(tmp_path):
    rows = []
    for i, (ttft, tpot, tokens, weight) in enumerate([(90, None, 1, 4), (120, 20, 3, 1), (70, 80, 2, 2)]):
        rows.append({"run": "r", "request_id": str(i), "status": "success", "output_tokens": tokens,
                     "weight": weight, "ttft_ms": ttft, "tpot_ms": tpot, "latency_ms": ttft+100, "good": True})
    profile = {"service_kind": "openai", "endpoint": "v1/completions", "experiments": [
        {"experiment": {"mode": "capture_v1", "value": "r"}, "capture_window_ns": 1_000_000_000,
         "requests": [{"capture_v1": row} for row in rows]}]}
    file = tmp_path / "p.json"
    file.write_text(json.dumps(profile))
    parser = LLMProfileDataParser(file, None, {"time_to_first_token": 100, "inter_token_latency": 50})
    return parser.get_statistics("capture_v1", "r")


def test_joint_slo_remains_request_aligned(tmp_path):
    statistics = make_profile(tmp_path)
    assert statistics.metrics.request_goodputs == [4.0]
    calculator = LLMGoodputCalculator({"time_to_first_token": 80}, statistics.metrics, 1)
    calculator.compute()
    assert calculator.goodput == [2.0]


def test_statistics_use_capture_sample_weights(tmp_path):
    statistics = make_profile(tmp_path)
    statistics.scale_data()
    assert statistics.stats_dict["time_to_first_token"]["avg"] == pytest.approx(620 / 7)
    assert statistics.stats_dict["time_to_first_token"]["p50"] == 90


@pytest.mark.parametrize("chunk_size", [1, 2, 7, 1024])
def test_byte_partition_equivalence(chunk_size):
    data = event([{"index": 0, "delta": {"token_ids": [1, 2], "content": "你好"}, "finish_reason": "stop"}]) + b'data: [DONE]\n\n'
    meter = StreamMeter()
    for pos in range(0, len(data), chunk_size):
        meter.feed(data[pos:pos+chunk_size], 200)
    assert meter.snapshot()["text"] == "你好"
    assert meter.snapshot()["tokens"] == [1, 2]
    assert meter.snapshot()["done_ns"] == 200
