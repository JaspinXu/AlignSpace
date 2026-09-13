"""Grounding regression cases, not a claim of evaluated aesthetic quality."""
import json
import httpx
import pytest

from app import engine, knowledge
from app.gateway import Gateway, GatewayError
from tests.test_engine import completed_state


def test_no_evidence_abstains_and_does_not_create_preferences():
    assert knowledge.retrieve('') == []
    assert knowledge.retrieve('xyzzynonexistent') == []
    state = engine.create_project('No inference', 'under_15k_sgd')
    engine.add_preferences(state, ['Maybe cosy but not Scandinavian'], [])
    assert state['shortlist'] == []
    assert state['attributes'] == []
    engine.answer_question(state, 'style_direction', 'homeowner', 'no_fixed_style')
    assert state['shortlist'] == []


def test_bilingual_retrieval_returns_stable_original_source_passages():
    english = knowledge.retrieve('scandinavian oak')
    chinese = knowledge.retrieve('北欧 浅橡木')
    assert english and chinese
    assert english[0]['path'] == chinese[0]['path'] == 'styles/scandinavian.md'
    records = {r['id']: r for r in knowledge.corpus()[0]}
    for record in english:
        original = records[record['id']]
        assert record['text'] == original['text']
        assert record['revision'] in record['url']
        assert '#L' in record['url']
        assert record['sourceType'] == 'secondary_handbook'
    assert english == knowledge.retrieve('scandinavian oak')


def test_constraint_exclusion_is_applied_before_retrieval_and_waiver_releases_it():
    state = engine.create_project('Materials', 'under_15k_sgd')
    engine.answer_question(state, 'primary_material', 'homeowner', 'light_oak')
    state['constraints'] = [{'incompatibleValue': 'stone', 'affectedDimension': 'material', 'waived': False}]
    exclusions = knowledge.exclusions(state)
    assert 'marble' in exclusions
    refs = knowledge.directions(state)
    assert refs
    assert all(not any(knowledge.contains(r['text'], p) for p in exclusions) for r in refs)
    state['constraints'][0]['waived'] = True
    assert 'marble' not in knowledge.exclusions(state)


def test_citations_are_snapshotted_and_part_of_approved_content():
    state = completed_state()
    brief = engine.build_brief(state)
    assert brief['knowledgeReferences']
    assert 'terminology' in brief
    engine.approve(state, 'homeowner', 'h1')
    assert engine.build_brief(state)['contentHash'] == brief['contentHash']
    state['shortlist'][0]['text'] += ' Changed reference.'
    assert engine.build_brief(state)['contentHash'] != brief['contentHash']
    # The second person cannot complete an approval of different content.
    engine.approve(state, 'designer', 'd1')
    assert state['status'] != 'approved'


def test_approval_does_not_refresh_corpus_mid_signature(monkeypatch):
    state = completed_state()
    before = engine.build_brief(state)['contentHash']
    monkeypatch.setattr(knowledge, 'directions', lambda state: [])
    engine.approve(state, 'homeowner', 'h1')
    engine.approve(state, 'designer', 'd1')
    assert state['status'] == 'approved'
    assert engine.build_brief(state)['contentHash'] == before


def test_aat_broader_mapping_does_not_claim_exact_oak_equivalence():
    state = engine.create_project('Wood', 'under_15k_sgd')
    engine.answer_question(state, 'primary_material', 'homeowner', 'light_oak')
    term = state['terminology'][0]
    assert 'not exact' in term['mappingRelation']
    assert term['license'] == 'ODC-By-1.0'
    assert state['attributes'][0]['value'] == 'light_oak'


def test_runtime_corpus_omits_building_codes_and_blender_integration():
    data = json.loads((knowledge.DATA / 'handbook.json').read_text(encoding='utf-8'))
    assert len(data['files']) == 9
    assert all(r['section'] in {'Anchor description', 'In', 'Warm vs. cool palettes',
               'Color adjacency (Albers / simultaneous contrast)', 'The four-layer model'} for r in data['records'])
    assert not any(r['path'] in {'codes.md', 'spatial.md'} for r in data['records'])


def test_gateway_retrieval_is_bounded_and_cannot_become_user_evidence(monkeypatch, tmp_path):
    monkeypatch.setenv('LLM_GATEWAY_URL', 'https://gateway.example')
    monkeypatch.setenv('LLM_GATEWAY_API_KEY', 'test-key')
    monkeypatch.setenv('LLM_MODEL', 'test-model')
    monkeypatch.setenv('ALIGNSPACE_ALLOW_IMAGES', 'false')
    state = engine.create_project('Grounded notes', 'under_15k_sgd')
    engine.add_reference(state, {'id': 'user-ref', 'note': 'I like Scandinavian oak.'})
    captured = []

    def respond(client, url, **kwargs):
        messages = kwargs['json']['messages']
        context = json.loads(messages[1]['content'])['referenceOnlyHandbook']
        assert 0 < len(context) <= 3
        assert sum(len(r['text']) for r in context) <= 7000
        assert 'untrusted secondary reference data' in messages[0]['content']
        captured.extend(context)
        return httpx.Response(200, json={'message': {'content': json.dumps({'proposals': []})}})

    monkeypatch.setattr(httpx.Client, 'post', respond)
    proposals, usage = Gateway().analyse(state, tmp_path)
    assert proposals == []
    assert usage['retrievedChunkIds'] == [r['id'] for r in captured]
    assert state['attributes'] == []
    fabricated_evidence = {'proposals': [{'dimension': 'style', 'value': 'scandinavian',
        'confidence': 0.8, 'sourceId': captured[0]['id'], 'description': 'Handbook says so'}]}
    monkeypatch.setattr(httpx.Client, 'post', lambda *a, **k: httpx.Response(200,
        json={'message': {'content': json.dumps(fabricated_evidence)}}))
    with pytest.raises(GatewayError, match='unknown attribute or evidence source'):
        Gateway().analyse(state, tmp_path)
