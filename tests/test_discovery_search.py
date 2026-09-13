import json
from copy import deepcopy
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi.testclient import TestClient

from app import discovery, engine
from app.main import create_app


def source_project():
    return {'id': 987654, 'title': 'Room with timber', 'type': 'Apartment', 'commonName': '4-room HDB',
        'styles': ['Scandinavian'], 'size': 93, 'company': {'name': 'Example Studio'},
        'url': discovery.BASE + '/example-room-987654', 'internalOnly': 'must not be copied',
        'images': {'Gallery': [{'baseUrl': 'https://d1hy6t2xeg0mdl.cloudfront.net/image/123/abc',
                               'metadata': {'roomType': 'Living Room'}, 'tags': ['timber', 'scandinavian']}]}}


def flight_html(projects):
    payload = '1:' + json.dumps({'initialProjects': projects, 'initialItemCount': len(projects)}, separators=(',', ':'))
    return '<script>self.__next_f.push(' + json.dumps([1, payload]) + ')</script>'


def test_source_parser_selects_preview_fields_without_executing_scripts():
    projects, count = discovery.parse_listing(flight_html([source_project()]))
    preview = discovery.clean_preview(projects[0])
    assert count == 1 and preview['features'] == ['timber', 'scandinavian']
    assert preview['rooms'] == ['Living Room']
    assert set(preview) <= discovery.PREVIEW_FIELDS
    assert 'internalOnly' not in preview
    with pytest.raises(ValueError):
        discovery.parse_listing('<script>window.stealEverything()</script>')


@pytest.mark.parametrize('field,value', [('url', 'https://qanvast.com.evil.test/sg/interior-design-singapore/x'),
    ('url', 'javascript:alert(1)'), ('image', 'http://127.0.0.1/secret')])
def test_untrusted_preview_urls_are_rejected(field, value):
    raw = source_project()
    if field == 'image':
        raw['images']['Gallery'][0]['baseUrl'] = value
    else:
        raw[field] = value
    assert discovery.clean_preview(raw) is None


def test_search_parameters_cannot_change_the_source_host():
    url = discovery.source_url('oak & search=other', 'Scandinavian', 'HDB')
    assert urlparse(url).netloc == 'qanvast.com'
    assert parse_qs(urlparse(url).query) == {'search': ['oak & search=other'], 'style': ['Scandinavian'], 'houseType': ['Apartment']}
    with pytest.raises(ValueError):
        discovery.source_url(style='unrecognised')


def test_live_search_saves_server_owned_previews_and_restores_after_restart(monkeypatch, tmp_path):
    calls = []
    preview = discovery.clean_preview(source_project())
    def fetch(url):
        calls.append(url)
        return [deepcopy(preview)], 123
    monkeypatch.setattr(discovery, 'fetch_listing', fetch)
    database = tmp_path / 'search.db'
    app = create_app(database)
    client = TestClient(app)
    response = client.get('/api/inspiration/search', params={'q': 'timber', 'style': 'Scandinavian', 'kind': 'HDB'})
    assert response.status_code == 200
    assert response.json()['sourceTotal'] == 123
    assert response.json()['mode'] == 'live'
    # Caller mutation cannot poison the cached source response.
    app.state.discovery.search('timber', 'Scandinavian', 'HDB')['projects'].clear()
    assert len(client.get('/api/inspiration/search', params={'q': 'timber', 'style': 'Scandinavian', 'kind': 'HDB'}).json()['projects']) == 1
    assert len(calls) == 1
    restarted = TestClient(create_app(database))
    assert restarted.post('/api/inspiration/resolve', json={'ids': [preview['id']]}).json()['projects'][0]['title'] == preview['title']
    created = restarted.post('/api/projects', json={'name': 'From a search', 'inspirationIds': [preview['id']], 'inspirationConsent': True})
    assert created.status_code == 201
    state = created.json()
    assert state['attributes'] == []
    assert state['references'][0]['sourceDetails']['style'] == 'Scandinavian'
    assert set(state['brief']['project']) == {'id', 'roomType', 'housingType', 'status'}
    assert restarted.get('/api/inspiration/search', params={'q': 'x' * 101}).status_code == 422


def test_live_empty_results_and_source_failure_are_distinct(monkeypatch, tmp_path):
    app = create_app(tmp_path / 'search.db')
    monkeypatch.setattr(discovery, 'fetch_listing', lambda url: ([], 0))
    empty = app.state.discovery.search('no results')
    assert empty['mode'] == 'live' and empty['projects'] == []
    def fail(url):
        raise httpx.ConnectError('unavailable')
    monkeypatch.setattr(discovery, 'fetch_listing', fail)
    fallback = app.state.discovery.search(style='Scandinavian')
    assert fallback['mode'] == 'saved' and fallback['projects']
    assert all('scandinavian' in p['style'].lower() for p in fallback['projects'])


def test_schema_migration_retains_preferences_and_invalidates_old_signatures(tmp_path):
    db = tmp_path / 'legacy.db'
    app = create_app(db)
    old = engine.create_project('Existing room', 'HDB')
    for q, role, value in engine.demo_answers():
        engine.answer_question(old, q, role, value)
    engine.approve(old, 'homeowner', 'h')
    engine.approve(old, 'designer', 'd')
    old['schemaVersion'] = '1.0.0'
    old['retiredField'] = 'obsolete'
    old['references'] = [{'id': 'r1', 'note': 'I like this wood', 'sourceDetails': {'designer': 'Studio', 'retiredField': 42}}]
    old['constraints'] = [{'id': 'old-c', 'category': 'retired', 'severity': 'important'}]
    old['conflicts'] = [{'id': 'old-conflict', 'constraintId': 'old-c', 'status': 'open'}]
    app.state.store.create(old)
    migrated_app = create_app(db)
    state = migrated_app.state.store.get(old['id'])
    assert state['schemaVersion'] == '1.1.0'
    assert 'retiredField' not in state
    assert state['attributes'] == old['attributes']
    assert state['references'][0]['sourceDetails'] == {'designer': 'Studio'}
    assert state['constraints'] == state['conflicts'] == state['approvals'] == []
    assert state['stateVersion'] == old['stateVersion'] + 1
    assert create_app(db).state.store.get(old['id'])['stateVersion'] == state['stateVersion']
