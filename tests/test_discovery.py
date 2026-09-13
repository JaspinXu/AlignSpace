"""The discovery handoff must preserve sources without declaring preferences."""
import json
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import create_app


def test_saved_homes_are_imported_once_with_server_owned_sources(tmp_path):
    client = TestClient(create_app(tmp_path / 'homes.db'))
    response = client.post('/api/projects', json={
        'name': 'My Singapore room', 'budgetBand': 'under_15k_sgd',
        'inspirationIds': ['tampines', 'tampines', 'tengah'], 'inspirationConsent': True,
    })
    assert response.status_code == 201
    project = response.json()
    assert len(project['references']) == 2
    assert project['attributes'] == []
    assert project['budgetBand'] == 'under_15k_sgd'
    assert project['references'][0]['sourceDetails']['cost'] == 60000
    assert project['references'][1]['sourceDetails']['cost'] is None
    assert all(ref['sourceUrl'].startswith('https://qanvast.com/sg/') for ref in project['references'])
    assert all(ref['consentConfirmed'] and ref['consentActor'] for ref in project['references'])
    restored = client.get('/api/projects/' + project['id']).json()
    assert restored['references'] == project['references']
    assert client.get('/api/projects/' + project['id'] + '/brief').status_code == 200
    outsider = TestClient(client.app)
    assert outsider.get('/api/projects/' + project['id']).status_code == 403


def test_invalid_or_unconsented_import_does_not_create_project(tmp_path):
    client = TestClient(create_app(tmp_path / 'homes.db'))
    base = {'name': 'My room', 'budgetBand': '15k_to_30k_sgd'}
    for extra in [
        {'inspirationIds': ['tampines']},
        {'inspirationIds': ['not-a-home'], 'inspirationConsent': True},
        {'inspirationIds': ['tampines'] * 7, 'inspirationConsent': True},
    ]:
        assert client.post('/api/projects', json={**base, **extra}).status_code == 422
    assert client.get('/api/projects').json() == []


def test_catalogue_keeps_unknown_costs_and_benchmark_years_explicit():
    data = json.loads((Path(__file__).resolve().parents[1] / 'app/static/singapore.json').read_text(encoding='utf-8'))
    assert len({p['id'] for p in data['projects']}) == len(data['projects'])
    assert {p['propertyType'] for p in data['projects']} == {'HDB', 'Condo', 'Landed'}
    assert next(p for p in data['projects'] if p['id'] == 'tengah')['cost'] is None
    for benchmark in data['budgets']:
        assert 0 < benchmark['low'] <= benchmark['high']
        assert str(benchmark['year']) in benchmark['sourceUrl']
        assert benchmark['year'] == (2025 if benchmark['type'] == 'Condo' else 2026)
