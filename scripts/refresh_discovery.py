"""Refresh lightweight attributed previews from public style collections."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.discovery import fetch_listing, source_url


if __name__ == '__main__':
    path = Path(__file__).resolve().parents[1] / 'app/static/singapore.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    projects = {p['sourceUrl']: p for p in data['projects']}
    for style in ['All', 'Scandinavian', 'Minimalist', 'Industrial', 'Eclectic', 'Modern']:
        previews, _ = fetch_listing(source_url(style=style))
        for p in previews:
            previous = projects.get(p['sourceUrl'])
            if previous:
                p['id'] = previous['id']
            projects[p['sourceUrl']] = p
        print(style, len(previews))
    data = {'checkedAt': '2026-09-13', 'projects': list(projects.values())}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Saved previews:', len(data['projects']))
