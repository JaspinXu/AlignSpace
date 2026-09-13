"""Refresh the reviewed handbook subset at an immutable revision (no code imports)."""
import hashlib
import json
import re
from pathlib import Path
from urllib.request import urlopen

REVISION = 'b21325782089bb26bbc0ff96204d4602264f86ea'
ROOT = Path(__file__).resolve().parents[1] / 'app' / 'knowledge_data'
STYLES = ['scandinavian', 'japanese-wabi-sabi', 'muji-minimal', 'modern-minimal',
          'quiet-luxury', 'industrial-loft', 'mid-century-modern']
SELECTION = {f'styles/{name}.md': {'Anchor description', 'In'} for name in STYLES}
SELECTION.update({'materials.md': {'Warm vs. cool palettes', 'Color adjacency (Albers / simultaneous contrast)'},
                  'lighting.md': {'The four-layer model'}})


def build():
    records, files = [], []
    for path, headings in SELECTION.items():
        url = f'https://raw.githubusercontent.com/MickeyBadBad/atelier-mcp/{REVISION}/docs/handbook/{path}'
        raw = urlopen(url, timeout=30).read()
        lines = raw.decode('utf-8').splitlines()
        files.append({'path': path, 'sha256': hashlib.sha256(raw).hexdigest()})
        title = lines[0].lstrip('# ')
        section, start, body = '', 0, []

        def flush():
            if section not in headings:
                return
            # Paragraphs retain inline citations; no arbitrary character truncation.
            for paragraph in re.split(r'\n\s*\n', '\n'.join(body).strip()):
                if not paragraph or len(paragraph) > 4000:
                    continue
                digest = hashlib.sha256((path + section + paragraph).encode()).hexdigest()[:16]
                records.append({'id': digest, 'title': title, 'section': section,
                    'text': paragraph, 'path': path, 'line': start,
                    'url': f'https://github.com/MickeyBadBad/atelier-mcp/blob/{REVISION}/docs/handbook/{path}#L{start}',
                    'revision': REVISION, 'sourceType': 'secondary_handbook',
                    'verification': 'Upstream citations retained; not independently verified. Design discussion only; not Singapore compliance or pricing.'})

        for number, line in enumerate(lines, 1):
            if re.match(r'^#{1,6} ', line):
                flush()
                section, start, body = line.lstrip('# '), number, []
            else:
                body.append(line)
        flush()
    return {'version': 'handbook-subset-v1', 'revision': REVISION, 'files': files, 'records': records}


if __name__ == '__main__':
    data = build()
    license_text = urlopen(f'https://raw.githubusercontent.com/MickeyBadBad/atelier-mcp/{REVISION}/LICENSE', timeout=30).read()
    ROOT.mkdir(parents=True, exist_ok=True)
    (ROOT / 'handbook.json').write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (ROOT / 'ATELIER-LICENSE.txt').write_bytes(license_text)
    print(f"Imported {len(data['records'])} excerpts from {len(data['files'])} chapters at {REVISION}")
