"""Build a new public snapshot without touching the working Git index/history."""
import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_DIRS = ('src', 'scripts', 'tests', 'configs', 'docs', 'research')
ALLOWED_FILES = ('.gitignore', 'AGENTS.md', 'README.md', 'RESEARCH.md', 'environment.yml', 'pyproject.toml')
PATTERNS = [r'\b(?:ghp_|github_pat_)[A-Za-z0-9_]{20,}', r'\bsk-[A-Za-z0-9_-]{20,}',
            r'AKIA[0-9A-Z]{16}', r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----']


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.relative_to(ROOT / 'tmp')
    if output.exists():
        raise FileExistsError(output)
    selected, excluded, findings = [], [], []
    candidates = [ROOT / p for p in ALLOWED_FILES]
    for name in ALLOWED_DIRS:
        candidates.extend(p for p in (ROOT / name).rglob('*') if p.is_file())
    for path in sorted(candidates):
        rel = path.relative_to(ROOT)
        reason = None
        if any(p in ('__pycache__', 'markets', '.pytest_cache') for p in rel.parts):
            reason = 'cache or raw market observations'
        elif path.suffix.lower() in ('.log', '.sqlite', '.sqlite3', '.pyc', '.pdf', '.html', '.zip'):
            reason = 'runtime or third-party source material'
        elif path.name == 'account-fees-user-confirmed-v1.json':
            reason = 'personal account record'
        elif path.name.startswith('.env') or path.suffix in ('.key', '.pem'):
            reason = 'local credential configuration'
        if reason:
            excluded.append({'path': rel.as_posix(), 'reason': reason})
            continue
        source_raw = path.read_bytes()
        body = source_raw.decode('utf-8')
        if any(re.search(pattern, body) for pattern in PATTERNS):
            findings.append(rel.as_posix())
        # Git for Windows may normalize CRLF on commit. Hash and publish the
        # canonical LF bytes so the manifest describes GitHub blob contents.
        public_raw = source_raw.replace(b'\r\n', b'\n')
        selected.append((rel, hashlib.sha256(source_raw).hexdigest(), public_raw))
    if findings:
        raise ValueError('credential-shaped content in: ' + ', '.join(findings))
    output.mkdir(parents=True)
    manifest = []
    for rel, source_sha256, raw in selected:
        dest = output / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() != source_sha256:
            raise ValueError('source changed during snapshot: ' + str(rel))
        dest.write_bytes(raw)
        if dest.read_bytes() != raw:
            raise ValueError('snapshot write failed: ' + str(rel))
        manifest.append({'path': rel.as_posix(), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
    report = {'status': 'PUBLIC_RESEARCH_SNAPSHOT_NOT_CAPITAL_READY', 'files': manifest,
              'encoding': 'UTF-8 with CRLF normalized to LF',
              'excluded_selected_tree_files': excluded,
              'excluded_roots': ['data', 'mlruns', '.venv', '.venv-qlib', 'tmp', '.git'],
              'limitations': ['No historical Git objects exported.',
                             'Raw data and local account records are absent; data-dependent replay requires original local inputs.',
                             'Credential pattern scan is not a guarantee of absence of every possible secret.']}
    (output / 'PUBLIC_SNAPSHOT_MANIFEST.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps({'files': len(manifest), 'bytes': sum(x['bytes'] for x in manifest), 'excluded_files': len(excluded), 'output': str(output)}))


if __name__ == '__main__':
    main()
