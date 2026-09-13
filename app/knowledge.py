"""Local, deterministic retrieval. Source text is evidence, never executable policy.

Aliases are editorial query expansions, NOT style definitions or user preferences.
Scores measure lexical relevance, not design suitability or calibrated confidence.
"""
import hashlib
import json
import math
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).with_name('knowledge_data')
ALIASES = {
    'warm_modern': ['modern', 'warm', '暖色现代'],
    'japandi': ['japandi', 'japanese', 'scandinavian', '日式', '侘寂'],
    'contemporary_luxe': ['quiet luxury', 'luxury', '轻奢'],
    'industrial': ['industrial', 'loft', '工业风'],
    'scandinavian': ['scandinavian', 'nordic', '北欧'],
    'calm': ['calm', 'quiet', '安静'], 'cosy': ['cosy', 'cozy', 'comfort', '温馨'],
    'bright': ['bright', 'daylight', '明亮'], 'dramatic': ['dramatic', 'contrast'],
    'social': ['togetherness', 'conversation'],
    'warm_neutral': ['warm', 'beige'], 'light_neutral': ['off-white', 'pale'],
    'earthy': ['earth', 'earthy', '大地色'], 'monochrome': ['monochrome'],
    'deep_tones': ['dark', 'deep'], 'light_oak': ['oak', 'pale wood', '浅橡木'],
    'walnut': ['walnut', '胡桃木'], 'stone': ['stone', 'marble', '石材', '大理石'],
    'metal': ['metal', 'steel', '金属'], 'soft_textiles': ['textiles', 'linen', 'wool', '布艺'],
    'soft_layered': ['layer', 'ambient', '柔和灯光'],
    'natural_bright': ['daylight', 'natural light', '自然光'],
    'warm_ambient': ['warm light', 'ambient'], 'statement': ['pendant', 'decorative'],
    'task_focused': ['task', 'reading'], 'family_relaxing': ['comfort', 'togetherness'],
    'hosting': ['conversation', 'gathering'], 'tv_and_media': ['television', 'screen'],
    'flexible_use': ['flexible', 'modular'], 'quiet_retreat': ['quiet', 'calm'],
    'open_flow': ['open plan', 'circulation'], 'zoned': ['zone', 'zoning'],
    'compact': ['compact', 'small'], 'conversation_focused': ['conversation'],
    'storage_led': ['storage'], 'easy_care': ['maintenance', 'cleaning'],
    'balanced': ['maintenance'], 'premium_care': ['maintenance'],
}
STOP = set('a an the and or of to for in on is it with as by from this that be at per'.split())


def tokens(text):
    return [t for t in re.findall(r'[a-z0-9]+|[\u4e00-\u9fff]+', text.lower()) if t not in STOP]


def contains(text, phrase):
    return bool(re.search(r'(?<![a-z0-9])' + re.escape(phrase.lower()) + r'(?![a-z0-9])', text.lower()))


def expand(text):
    terms = [text.replace('_', ' ')]
    for value, aliases in ALIASES.items():
        if contains(text, value) or any(contains(text, a) for a in aliases):
            terms.extend(aliases)
    # AAT is a broader material concept, never an oak species/style identity.
    for record in terminology():
        if any(contains(text, a) for a in record['queryAliases']):
            terms.append(record['preferredLabel'])
    return ' '.join(terms)


@lru_cache(maxsize=1)
def terminology():
    return json.loads((DATA / 'terminology.json').read_text(encoding='utf-8'))


@lru_cache(maxsize=1)
def corpus():
    raw = (DATA / 'handbook.json').read_bytes()
    data = json.loads(raw)
    records = data['records']
    counts = [Counter(tokens(r['title'] + ' ' + r['section'] + ' ' + r['text'])) for r in records]
    frequency = Counter(t for c in counts for t in c)
    return records, counts, frequency, hashlib.sha256(raw).hexdigest()


def retrieve(query, limit=3, excluded_terms=()):
    """BM25 over the reviewed local subset; empty/no-overlap queries abstain."""
    records, counts, frequency, digest = corpus()
    query_tokens = set(tokens(expand(query)))
    if not query_tokens:
        return []
    average = sum(sum(c.values()) for c in counts) / max(1, len(counts))
    ranked = []
    for record, count in zip(records, counts):
        content = record['title'] + ' ' + record['text']
        # Conservative: even an incidental excluded material suppresses the excerpt.
        if any(contains(content, phrase) for phrase in excluded_terms if phrase):
            continue
        overlap = query_tokens & count.keys()
        score = sum(math.log(1 + (len(records) - frequency[t] + .5) / (frequency[t] + .5)) *
                    count[t] * 2.2 / (count[t] + 1.2 * (.25 + .75 * sum(count.values()) / average))
                    for t in overlap)
        if score > 0:
            ranked.append({**record, 'retrievalScore': round(score, 4),
                           'matchedTerms': sorted(overlap), 'corpusVersion': digest})
    ranked.sort(key=lambda r: (-r['retrievalScore'], r['id']))
    # Prefer distinct sources so one long style chapter cannot fill the shortlist.
    selected, paths = [], set()
    for record in ranked:
        if record['path'] not in paths:
            selected.append(record)
            paths.add(record['path'])
        if len(selected) >= min(max(limit, 1), 6):
            break
    return selected


def exclusions(state):
    phrases = list(state.get('antiPreferences', []))
    values = [c.get('incompatibleValue', '') for c in state.get('constraints', []) if not c.get('waived')]
    for text in [*phrases, *values]:
        for value, aliases in ALIASES.items():
            if contains(text, value.replace('_', ' ')) or contains(text, value) or any(contains(text, a) for a in aliases):
                phrases.extend(aliases)
    return phrases


def directions(state):
    confirmed = {a['dimension']: a['value'] for a in state['attributes'] if a['status'] == 'confirmed'}
    # Goals/notes may include dislikes or hypotheticals. Use confirmed values only.
    query = ' '.join(v for v in confirmed.values() if v != 'no_fixed_style')
    records = retrieve(query, excluded_terms=exclusions(state)) if query else []
    results = []
    for record in records:
        results.append({**record, 'kind': 'knowledge_reference',
            'budget': None, 'overBudget': None, 'budgetLabel': 'Cost not assessed; obtain a project-specific quote',
            'relevantDimensions': [d for d, v in confirmed.items()
                if set(tokens(expand(v))) & set(tokens(record['text'] + ' ' + record['title']))],
            'unassessed': ['Budget', 'Site fit', 'Maintenance suitability', 'Singapore compliance']})
    return results


def terminology_for(state):
    values = {a['value'] for a in state['attributes'] if a['status'] == 'confirmed'}
    return [r for r in terminology() if values.intersection(r['localValues'])]
