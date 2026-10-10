"""Public raw-export/recovery entry point for the KV replay service."""
import argparse
import json
from pathlib import Path
from .sources import load_evidence
from .session import ReplaySession


def main():
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--input', type=Path)
    source.add_argument('--restore', type=Path)
    parser.add_argument('--queries', type=Path)
    parser.add_argument('--append', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.input:
        manifest, records = load_evidence(args.input)
        session = ReplaySession(manifest)
        session.ingest(records)
        queries = [dict(id='default', **manifest['query'])]
    else:
        session = ReplaySession.from_checkpoint(json.loads(args.restore.read_text('utf8')))
        if not args.queries:
            parser.error('--restore requires --queries')
        queries = []
    if args.append:
        session.ingest(json.loads(args.append.read_text('utf8')))
    if args.queries:
        queries = json.loads(args.queries.read_text('utf8'))
    views = {q['id']: session.snapshot(q['observed_ns'], q['valid_ns']) for q in queries}
    args.output.mkdir(parents=True, exist_ok=True)
    for name, value in [('views.json', views), ('checkpoint.json', session.checkpoint())]:
        (args.output / name).write_text(json.dumps(value, ensure_ascii=False, allow_nan=False), encoding='utf8')


if __name__ == '__main__':
    main()
