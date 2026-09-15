"""Read public project-list previews, never execute source scripts or mirror pages."""
import json
import re
import sqlite3
import threading
import time
from collections import OrderedDict
from copy import deepcopy
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlencode, urlparse

import httpx
from app.language import normalize_search

BASE = 'https://qanvast.com/sg/interior-design-singapore'
STYLES = ('All', 'Contemporary', 'Modern', 'Scandinavian', 'Minimalist', 'Industrial', 'Eclectic', 'Japandi', 'Wabi-Sabi')
KINDS = {'All': None, 'HDB': 'Apartment', 'Condo': 'Condo', 'Landed': 'Landed'}
STYLE_CUES = {
    'Scandinavian': 'Look at pale timber, soft textures and the balance of light and warmth.',
    'Minimalist': 'Look at visual simplicity, concealed storage and the space between objects.',
    'Industrial': 'Look at exposed surfaces, metal details and contrasting textures.',
    'Contemporary': 'Look at the focal point, layered surfaces and the mix of furniture shapes.',
    'Modern': 'Look at clean lines, repeated materials and how the room flows.',
    'Eclectic': 'Look at how contrasting colours, objects and eras are brought together.',
    'Japandi': 'Look at timber, tactile finishes and the balance of warmth and simplicity.',
    'Wabi-Sabi': 'Look at uneven textures, muted colours and materials that show their character.',
}
PREVIEW_FIELDS = {'id', 'title', 'town', 'propertyType', 'condition', 'flatType', 'area', 'year',
                  'style', 'designer', 'sourceUrl', 'imageUrl', 'features', 'rooms', 'works', 'prompt',
                  'styleCue', 'checkedAt', 'source'}


def source_url(query='', style='All', kind='All'):
    if style not in STYLES or kind not in KINDS:
        raise ValueError('Choose a supported style and home type')
    params = {}
    if query.strip():
        params['search'] = normalize_search(query)[:100]
    if style != 'All':
        params['style'] = style
    if kind != 'All':
        params['houseType'] = KINDS[kind]
    return BASE + ('?' + urlencode(params) if params else '')


class FlightParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_script = False
        self.body = []
        self.chunks = []

    def handle_starttag(self, tag, attrs):
        if tag == 'script':
            self.in_script, self.body = True, []

    def handle_data(self, data):
        if self.in_script:
            self.body.append(data)

    def handle_endtag(self, tag):
        if tag == 'script' and self.in_script:
            self.in_script = False
            script = ''.join(self.body).strip()
            prefix = 'self.__next_f.push('
            if script.startswith(prefix) and script.endswith(')'):
                try:
                    item = json.loads(script[len(prefix):-1])
                    if isinstance(item, list) and len(item) == 2 and item[0] == 1 and isinstance(item[1], str):
                        self.chunks.append(item[1])
                except ValueError:
                    pass


def parse_listing(html):
    parser = FlightParser()
    parser.feed(html)
    text = ''.join(parser.chunks)
    marker = '"initialProjects":'
    if marker not in text:
        raise ValueError('The source preview format changed')
    start = text.index(marker) + len(marker)
    projects, end = json.JSONDecoder().raw_decode(text[start:])
    if not isinstance(projects, list) or len(projects) > 60:
        raise ValueError('Unexpected source preview list')
    count = re.search(r'"initialItemCount":(\d+)', text[start + end:start + end + 200])
    return projects, int(count[1]) if count else len(projects)


def safe_url(value, host, path_prefix):
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    return parsed.scheme == 'https' and parsed.netloc == host and parsed.path.startswith(path_prefix)


def clean_preview(raw):
    """Explicit field selection: no arbitrary upstream content reaches the app."""
    url = raw.get('url', '')
    images = raw.get('images') or {}
    gallery = images.get('Gallery') or []
    cover = images.get('Cover') or (gallery[0] if gallery else {})
    if isinstance(cover, list):
        cover = cover[0] if cover else {}
    # Prefer a living-room photo, preserving source attribution and room labels.
    photo = next((p for p in gallery if p.get('metadata', {}).get('roomType') == 'Living Room'), cover)
    image = photo.get('baseUrl', '')
    if not safe_url(url, 'qanvast.com', '/sg/interior-design-singapore/') or not safe_url(image, 'd1hy6t2xeg0mdl.cloudfront.net', '/image/'):
        return None
    if not isinstance(raw.get('id'), int):
        return None
    styles = [str(s)[:50] for s in raw.get('styles', []) if isinstance(s, str)][:5]
    rooms = sorted({p.get('metadata', {}).get('roomType') for p in gallery if p.get('metadata', {}).get('roomType')})
    tags = list(dict.fromkeys(str(t)[:60] for t in photo.get('tags', []) if isinstance(t, str)))[:8]
    property_type = {'Apartment': 'HDB', 'Condominium': 'Condo'}.get(raw.get('type'), raw.get('type', 'Home'))
    if property_type not in {'HDB', 'Condo', 'Landed'}:
        property_type = 'Home'
    return {'id': 'q-' + str(raw['id']), 'title': str(raw.get('title', 'Design reference'))[:120],
        'town': 'Singapore', 'propertyType': property_type,
        'condition': 'New' if raw.get('isNewProperty') is True else 'Resale' if raw.get('isNewProperty') is False else 'Not specified',
        'flatType': str(raw.get('commonName') or property_type)[:80],
        'area': raw.get('size') if isinstance(raw.get('size'), (int, float)) and raw['size'] > 0 else None,
        'year': str(raw.get('yearOfCompletion') or '')[:4], 'style': ' / '.join(styles) or 'Style not labelled',
        'designer': str((raw.get('company') or {}).get('name') or 'Source designer')[:120],
        'sourceUrl': url, 'imageUrl': image + '/standard',
        'features': tags, 'rooms': rooms[:10], 'works': [str(w)[:60] for w in raw.get('otherWorks', [])][:10],
        'styleCue': next((STYLE_CUES[s] for s in styles if s in STYLE_CUES), 'Look at the colours, material contrasts and arrangement of furniture.'),
        'prompt': 'Which two details would you keep, and what would you change to make this room feel like you?',
        'checkedAt': datetime.now(timezone.utc).date().isoformat(), 'source': 'Qanvast'}


def fetch_listing(url):
    # Fixed host, no redirects, limited response size; source scripts are only parsed as JSON.
    with httpx.Client(timeout=12, follow_redirects=False) as client:
        with client.stream('GET', url, headers={'User-Agent': 'AlignSpace/1.1 public-preview'}) as response:
            response.raise_for_status()
            content = bytearray()
            for part in response.iter_bytes():
                content.extend(part)
                if len(content) > 2_000_000:
                    raise ValueError('Source preview response too large')
    raw, count = parse_listing(content.decode('utf-8'))
    return [p for r in raw if (p := clean_preview(r)) is not None], count


class Discovery:
    def __init__(self, database_path):
        self.database_path = database_path
        self.seed = json.loads((Path(__file__).with_name('static') / 'singapore.json').read_text(encoding='utf-8'))
        self.cache = OrderedDict()
        self.lock = threading.Lock()
        self.slots = threading.BoundedSemaphore(2)
        with sqlite3.connect(database_path) as db:
            db.execute('CREATE TABLE IF NOT EXISTS inspiration_previews (id TEXT PRIMARY KEY, preview_json TEXT NOT NULL, fetched REAL NOT NULL)')

    def remember(self, projects):
        with sqlite3.connect(self.database_path) as db:
            db.executemany('INSERT OR REPLACE INTO inspiration_previews VALUES (?,?,?)',
                [(p['id'], json.dumps(p), time.time()) for p in projects])
            db.execute('DELETE FROM inspiration_previews WHERE id NOT IN (SELECT id FROM inspiration_previews ORDER BY fetched DESC LIMIT 1000)')

    def find(self, ids):
        wanted = tuple(dict.fromkeys(ids))
        if not wanted:
            return {}
        found = {p['id']: p for p in self.seed['projects'] if p['id'] in wanted}
        with sqlite3.connect(self.database_path) as db:
            rows = db.execute(
                f"SELECT id, preview_json FROM inspiration_previews WHERE id IN ({','.join('?' * len(wanted))})",
                wanted).fetchall()
        # A remembered live preview is newer than the checked-in seed copy.
        found.update({row[0]: json.loads(row[1]) for row in rows})
        return found

    def search(self, query='', style='All', kind='All'):
        url = source_url(query, style, kind)
        with self.lock:
            cached = self.cache.get(url)
            if cached and time.monotonic() - cached[0] < 900:
                return deepcopy(cached[1])
        if not self.slots.acquire(blocking=False):
            return self.fallback(query, style, kind, url)
        try:
            projects, count = fetch_listing(url)
            existing_ids = {p['sourceUrl']: p['id'] for p in self.seed['projects']}
            for project in projects:
                project['id'] = existing_ids.get(project['sourceUrl'], project['id'])
            self.remember(projects)
            result = {'projects': projects, 'sourceUrl': url, 'sourceTotal': count,
                      'mode': 'live', 'message': 'Previewing the first source results. Open the source to explore the complete selection.'}
            with self.lock:
                self.cache[url] = (time.monotonic(), result)
                self.cache.move_to_end(url)
                while len(self.cache) > 64:
                    self.cache.popitem(last=False)
            return deepcopy(result)
        except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError):
            return self.fallback(query, style, kind, url)
        finally:
            self.slots.release()

    def fallback(self, query, style, kind, url):
        words = normalize_search(query).casefold().split()
        projects = [p for p in self.seed['projects'] if (style == 'All' or style.casefold() in p['style'].casefold())
            and (kind == 'All' or p['propertyType'] == kind)
            and all(w in json.dumps(p, ensure_ascii=False).casefold() for w in words)]
        return {'projects': projects, 'sourceUrl': url, 'sourceTotal': None, 'mode': 'saved',
                'message': 'The live source is unavailable. Showing matching saved previews; you can also open the source directly.'}
