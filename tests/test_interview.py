import json
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from app import engine, interview
from app.main import create_app
from app.language import normalize_search


def answer_next(state, role='homeowner'):
    q = engine.next_question(state, role)
    assert q
    engine.answer_question(state, q['id'], role, q['options'][0])
    return q


def test_ten_question_gate_and_optional_rounds():
    s = engine.create_project('Rounds')
    for _ in range(10):
        answer_next(s)
    assert engine.next_question(s, 'homeowner') is None
    assert len([a for a in s['attributes'] if a['status'] == 'confirmed']) == 6
    with pytest.raises(ValueError, match='limit'):
        engine.answer_question(s, 'detail_sound', 'homeowner', 'Quiet')
    before = engine.build_brief(s)['contentHash']
    engine.set_interview(s, 'homeowner', 'continue')
    assert engine.build_brief(s)['contentHash'] == before
    assert s['maxQuestions'] == 20
    q = answer_next(s)
    assert q['detail'] and q['sequence'] == 11
    for _ in range(9):
        answer_next(s)
    assert engine.next_question(s, 'homeowner') is None
    engine.set_interview(s, 'homeowner', 'continue')
    assert answer_next(s)['sequence'] == 21
    Draft202012Validator(json.loads(Path('schemas/design-brief.schema.json').read_text())).validate(engine.build_brief(s))


def test_followups_depend_on_actual_answers_and_revisions():
    s = engine.create_project('Wood')
    engine.answer_question(s, 'primary_material', 'homeowner', 'light_oak')
    engine.answer_question(s, 'detail_wood_grain', 'homeowner', 'Natural variation')
    assert engine._confirmed_map(s)['material'] == 'light_oak'
    assert not interview.active_details(s)[0]['needsReview']
    with pytest.raises(ValueError, match='does not apply'):
        engine.answer_question(s, 'detail_stone_finish', 'homeowner', 'Polished')
    s['answers'] = [a for a in s['answers'] if a['questionId'] != 'primary_material']
    engine.answer_question(s, 'primary_material', 'homeowner', 'stone', revision=True)
    assert interview.active_details(s)[0]['needsReview']
    engine.answer_question(s, 'detail_stone_finish', 'homeowner', 'Honed matte')
    assert engine._confirmed_map(s)['material'] == 'stone'


def test_pause_resumes_same_question_without_mutating_signed_content():
    s = engine.create_project('Pause')
    q = engine.next_question(s, 'homeowner')
    h = engine.build_brief(s)['contentHash']
    engine.set_interview(s, 'homeowner', 'pause')
    assert engine.next_question(s, 'homeowner') is None
    assert engine.next_question(s, 'designer')
    with pytest.raises(ValueError):
        engine.answer_question(s, q['id'], 'homeowner', q['options'][0])
    engine.set_interview(s, 'homeowner', 'continue')
    assert engine.next_question(s, 'homeowner')['id'] == q['id']
    assert engine.build_brief(s)['contentHash'] == h
    with pytest.raises(ValueError):
        engine.set_interview(s, 'homeowner', 'continue')


def test_round_api_is_authorized_and_version_checked(tmp_path):
    client = TestClient(create_app(tmp_path/'db', tmp_path/'images'))
    s = client.post('/api/projects', json={'name':'My room'}).json()
    endpoint = f"/api/projects/{s['id']}/interview"
    payload = {'role':'homeowner','action':'pause','expectedStateVersion':s['stateVersion']}
    assert TestClient(client.app).post(endpoint, json=payload).status_code == 403
    assert client.post(endpoint, json={**payload,'role':'designer'}).status_code == 403
    assert client.post(endpoint, json=payload).status_code == 200
    assert client.post(endpoint, json=payload).status_code == 409


@pytest.mark.parametrize('note', ['我喜欢浅橡木，但不喜欢大理石和工业风。', 'I like 浅橡木 but dislike marble and industrial.', '我喜欢浅橡木。但我不想要大理石。'])
def test_bilingual_likes_and_negation(note):
    s = engine.create_project('Bilingual')
    engine.add_reference(s, {'id':'r1','filename':'note','note':note})
    engine.analyse_references(s)
    assert [(a['dimension'], a['value']) for a in s['attributes']] == [('material','light_oak')]
    s['antiPreferences'] = ['不要大理石']
    with pytest.raises(ValueError):
        engine.validate_preference(s, 'material', 'stone')


def test_search_aliases_preserve_unknown_text():
    assert normalize_search('我想找北欧风客厅') == 'Scandinavian living room'
    assert normalize_search('Japandi wood') == 'Japandi wood'
    assert normalize_search('北欧 Tampines') == 'Scandinavian Tampines'

def test_second_level_questions_require_the_specific_parent_answer():
    s = engine.create_project('Follow through')
    engine.answer_question(s, 'style_direction', 'homeowner', 'japandi')
    with pytest.raises(ValueError, match='does not apply'):
        engine.answer_question(s, 'detail_curve_placement', 'homeowner', 'Seating')
    engine.answer_question(s, 'detail_silhouette', 'homeowner', 'Soft curves')
    engine.answer_question(s, 'detail_curve_placement', 'homeowner', 'Seating')
    detail = interview.active_details(s)[-1]
    assert detail['questionId'] == 'detail_curve_placement' and not detail['needsReview']
    s['answers'] = [a for a in s['answers'] if a['questionId'] != 'detail_silhouette']
    engine.answer_question(s, 'detail_silhouette', 'homeowner', 'Straight lines', revision=True)
    assert next(d for d in interview.active_details(s) if d['questionId'] == 'detail_curve_placement')['needsReview']


def test_optional_details_clear_existing_approvals_but_pause_does_not():
    s = engine.create_project('Signed')
    for q, role, value in engine.demo_answers():
        engine.answer_question(s, q, role, value)
    engine.approve(s, 'homeowner', 'owner')
    h = engine.build_brief(s)['contentHash']
    engine.set_interview(s, 'homeowner', 'pause')
    assert s['approvals'] and engine.build_brief(s)['contentHash'] == h
    engine.set_interview(s, 'homeowner', 'continue')
    answer_next(s)
    assert not s['approvals'] and engine.build_brief(s)['contentHash'] != h

def test_detail_can_be_revised_or_removed_without_using_an_interview_turn(tmp_path):
    c = TestClient(create_app(tmp_path/'db', tmp_path/'images'))
    s = c.post('/api/projects', json={'name':'Revisions'}).json()
    base = '/api/projects/' + s['id']
    for q,value in [('primary_material','light_oak'),('detail_wood_grain','Strong character')]:
        s = c.post(base+'/questions/'+q+'/answer', json={'role':'homeowner','value':value,'expectedStateVersion':s['stateVersion']}).json()
    assert len(s['detailQuestions']) == 1
    count = s['questionCount']
    for q,value in [('primary_material','stone'),('detail_wood_grain','not_sure')]:
        response = c.put(base+'/decisions/'+q,json={'role':'homeowner','value':value,'expectedStateVersion':s['stateVersion']})
        assert response.status_code == 200
        s = response.json()
    assert s['questionCount'] == count and not s['brief']['designDetails']
