"""Replay multi-export journal deliveries and write query-specific materializations."""
import argparse
import gzip
import json
from pathlib import Path
from .live import ReplaySession


def run(root, output):
    manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8-sig'))
    session = ReplaySession(manifest['partitions'])
    for delivery in manifest['deliveries']:
        path = root / delivery
        text = gzip.decompress(path.read_bytes()).decode('utf-8-sig') if path.suffix == '.gz' else path.read_text(encoding='utf-8-sig')
        session.ingest([json.loads(line) for line in text.split('\n') if line.strip()])
        session = ReplaySession.from_checkpoint(json.loads(json.dumps(session.checkpoint())))
    output.mkdir(parents=True, exist_ok=True)
    for query in manifest['queries']:
        target = output / query['id']
        target.mkdir(exist_ok=True)
        report = session.snapshot(query['frontier'], query['valid_ns'], query.get('cutoff_ns'))
        for name, value in report.items():
            (target / name).write_text(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf8')
    (output / 'checkpoint.json').write_text(json.dumps(session.checkpoint(), ensure_ascii=False), encoding='utf8')
    return len(manifest['queries'])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps({'snapshots': run(args.input, args.output)}))


if __name__ == '__main__':
    main()
