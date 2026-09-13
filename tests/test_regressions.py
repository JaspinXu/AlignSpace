import io
import json

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import engine
from app.gateway import Gateway, GatewayError
from app.main import create_app


def complete():
    state = engine.create_project('Regression room','under_15k_sgd')
    for q,r,v in engine.demo_answers():
        engine.answer_question(state,q,r,v)
    return state


def test_negation_is_not_a_positive_preference():
    state = engine.create_project('Negative note','under_15k_sgd')
    engine.add_reference(state, {'id':'r1','filename':'industrial-marble.jpg',
        'note':'I do not like industrial style, dark wood or marble. But I like light oak.'})
    engine.analyse_references(state)
    assert [(a['dimension'],a['value']) for a in state['attributes']] == [('material','light_oak')]
    assert state['attributes'][0]['evidence'][0]['sourceType'] == 'homeowner_answer'


def test_confirmation_replaces_previous_dimension_and_invalidates_approval():
    state = complete()
    engine.approve(state,'homeowner','h')
    engine.add_reference(state,{'id':'r1','filename':'room.jpg','note':'industrial'})
    engine.analyse_references(state)
    proposal = next(a for a in state['attributes'] if a['status']=='proposed')
    engine.review_attribute(state,proposal['id'],'confirm')
    confirmed = [a for a in state['attributes'] if a['dimension']=='style' and a['status']=='confirmed']
    assert [a['value'] for a in confirmed] == ['industrial']
    assert state['approvals'] == []


def test_review_cannot_bypass_designer_constraint():
    state = complete()
    engine.add_constraint(state,{'category':'maintenance','statement':'Avoid stone','severity':'important',
        'affectedDimension':'material','incompatibleValue':'stone'})
    engine.add_reference(state,{'id':'r1','filename':'room.jpg','note':'marble'})
    engine.analyse_references(state)
    proposal = next(a for a in state['attributes'] if a['status']=='proposed')
    with pytest.raises(ValueError,match='constraint'):
        engine.review_attribute(state,proposal['id'],'confirm')


def test_legacy_duplicate_values_block_approval():
    state = complete()
    state['attributes'].append({**state['attributes'][1], 'id':'duplicate','value':'industrial'})
    engine.recompute(state)
    assert not state['readiness']['readyForApproval']
    assert state['readiness']['blockers']


def test_must_avoid_filters_candidates_and_budget_is_visible():
    state = engine.create_project('Budget room','under_15k_sgd')
    engine.add_preferences(state,[],['industrial','marble'])
    engine.answer_question(state, 'primary_material', 'homeowner', 'light_oak')
    assert state['shortlist']
    assert all('industrial' not in (c['title'] + c['text']).lower() and
               'marble' not in c['text'].lower() for c in state['shortlist'])
    assert all(c['overBudget'] is None and c['budget'] is None for c in state['shortlist'])
    with pytest.raises(ValueError,match='must-avoid'):
        engine.answer_question(state,'style_direction','homeowner','industrial')


def test_project_isolation_invitation_and_role_spoofing(tmp_path):
    app = create_app(tmp_path/'db.sqlite',tmp_path/'images')
    owner, stranger = TestClient(app), TestClient(app)
    p = owner.post('/api/demo').json()
    base = '/api/projects/'+p['id']
    assert stranger.get('/api/projects').json() == []
    for suffix in ['', '/brief', '/audit', '/analysis-runs']:
        assert stranger.get(base+suffix).status_code == 403
    assert owner.post(base+'/approvals',json={'role':'designer','actorId':'forged','expectedStateVersion':p['stateVersion']}).status_code == 403
    invite = owner.post(base+'/invitations').json()['invitationFragment'].split('=',1)[1]
    assert owner.post('/api/invitations/claim',json={'token':invite}).status_code == 409
    assert stranger.post('/api/invitations/claim',json={'token':invite}).status_code == 200
    assert TestClient(app).post('/api/invitations/claim',json={'token':invite}).status_code == 403
    assert stranger.put(base+'/preferences',json={'goals':['spoof']}).status_code == 403
    assert owner.post(base+'/approvals',json={'role':'homeowner','actorId':'forged'}).status_code==422
    a = owner.post(base+'/approvals',json={'role':'homeowner','actorId':'forged','expectedStateVersion':p['stateVersion']}).json()
    b = stranger.post(base+'/approvals',json={'role':'designer','actorId':'forged','expectedStateVersion':a['stateVersion']}).json()
    assert a['approvals'][0]['actorId'] != 'forged'
    assert len({r['actorId'] for r in b['approvals']}) == 2
    assert b['status']=='approved'


def test_csrf_is_rejected(tmp_path):
    client=TestClient(create_app(tmp_path/'db',tmp_path/'images'))
    assert client.post('/api/demo',headers={'Origin':'https://evil.example'}).status_code==403


def test_upload_requires_consent_decodes_and_is_project_private(tmp_path):
    client=TestClient(create_app(tmp_path/'db',tmp_path/'images'))
    p=client.post('/api/demo').json();base='/api/projects/'+p['id']
    content=io.BytesIO();Image.new('RGB',(40,40),'red').save(content,format='PNG')
    files={'file':('room.png',content.getvalue(),'image/png')}
    assert client.post(base+'/references',files=files).status_code==422
    assert client.post(base+'/references',files={'file':('bad.png',b'\x89PNG\r\n\x1a\nnot-a-picture','image/png')},data={'consent':'true'}).status_code==422
    p=client.post(base+'/references',files=files,data={'consent':'true'}).json()
    ref=p['references'][0]
    image_path=base+'/references/'+ref['id']+'/image'
    assert client.get(image_path).status_code==200
    assert TestClient(client.app).get(image_path).status_code==403
    assert ref['consentActor'] and ref['contentType']=='image/jpeg'


def test_analysis_cooldown_and_budget_survive_store_restart(tmp_path):
    client=TestClient(create_app(tmp_path/'db',tmp_path/'images'))
    p=client.post('/api/demo/start').json();base='/api/projects/'+p['id']
    assert client.post(base+'/analysis-runs').status_code==200
    assert client.post(base+'/analysis-runs').status_code==422
    runs=client.get(base+'/analysis-runs').json()
    assert len(runs)==1 and runs[0]['mode']=='offline_notes'
    from app.store import ProjectStore
    assert len(ProjectStore(tmp_path/'db').analysis_runs(p['id']))==1


@pytest.mark.parametrize('bad', [
    {'proposals':[{'dimension':'colour','value':'warm_neutral','confidence':0.8,'sourceId':'other-project','description':'test'}]},
    {'proposals':[{'dimension':'colour','value':'invented','confidence':0.8,'sourceId':'r1','description':'test'}]},
    {'proposals':[], 'approve':True},
])
def test_model_outputs_have_no_authority_or_unknown_sources(monkeypatch,tmp_path,bad):
    monkeypatch.setenv('LLM_GATEWAY_URL','https://gateway.example')
    monkeypatch.setenv('LLM_GATEWAY_API_KEY','test-key')
    monkeypatch.setenv('LLM_MODEL','test-model')
    monkeypatch.setattr(httpx.Client,'post',lambda *a,**k:httpx.Response(200,json={'message':{'content':json.dumps(bad)}}))
    state=engine.create_project('Gateway test','under_15k_sgd')
    engine.add_reference(state,{'id':'r1','note':'cream'})
    with pytest.raises(GatewayError): Gateway().analyse(state,tmp_path)
    assert state['attributes']==[]


def test_auth_failure_is_not_retried_or_exposed(monkeypatch,tmp_path):
    calls=[]
    monkeypatch.setenv('LLM_GATEWAY_URL','https://gateway.example')
    monkeypatch.setenv('LLM_GATEWAY_API_KEY','test-key')
    monkeypatch.setenv('LLM_MODEL','test-model')
    def failed(*a,**k):
        calls.append(1)
        return httpx.Response(403,text='sensitive upstream details')
    monkeypatch.setattr(httpx.Client,'post',failed)
    state=engine.create_project('Gateway test','under_15k_sgd')
    engine.add_reference(state,{'id':'r1','note':'cream'})
    with pytest.raises(GatewayError,match='HTTP 403') as error: Gateway().analyse(state,tmp_path)
    assert len(calls)==1 and 'sensitive' not in str(error.value)


@pytest.mark.parametrize('protocol',['ollama','openai','anthropic'])
def test_independent_vision_adapters_send_images_and_validate_output(monkeypatch,tmp_path,protocol):
    monkeypatch.setenv('ALIGNSPACE_ALLOW_IMAGES','true')
    monkeypatch.setenv('VISION_GATEWAY_URL','https://vision.example')
    monkeypatch.setenv('VISION_GATEWAY_API_KEY','vision-test-key')
    monkeypatch.setenv('VISION_MODEL','vision-test-model')
    monkeypatch.setenv('VISION_API_FORMAT',protocol)
    Image.new('RGB',(16,16),'beige').save(tmp_path/'r.jpg')
    output=json.dumps({'proposals':[{'dimension':'colour','value':'warm_neutral','confidence':0.8,'sourceId':'r1','description':'Beige area in the reference'}]})
    def response(client,url,**kwargs):
        body=kwargs['json']
        assert body['model']=='vision-test-model'
        assert 'images' in json.dumps(body) if protocol=='ollama' else 'image' in json.dumps(body)
        if protocol=='ollama': result={'message':{'content':output},'prompt_eval_count':10,'eval_count':20}
        elif protocol=='openai': result={'choices':[{'message':{'content':output}}],'usage':{'prompt_tokens':10,'completion_tokens':20}}
        else: result={'content':[{'type':'text','text':output}],'usage':{'input_tokens':10,'output_tokens':20}}
        return httpx.Response(200,json=result)
    monkeypatch.setattr(httpx.Client,'post',response)
    state=engine.create_project('Vision test','under_15k_sgd')
    engine.add_reference(state,{'id':'r1','note':'test','storageKey':'r.jpg'})
    proposals,usage=Gateway().analyse(state,tmp_path)
    assert proposals[0]['sourceType']=='image'
    assert usage['inputTokens']==10 and usage['outputTokens']==20


def test_concatenated_gateway_output_uses_only_first_valid_envelope(monkeypatch,tmp_path):
    monkeypatch.setenv('LLM_GATEWAY_URL','https://gateway.example')
    monkeypatch.setenv('LLM_GATEWAY_API_KEY','test')
    monkeypatch.setenv('LLM_MODEL','test')
    monkeypatch.setattr(httpx.Client,'post',lambda *a,**k:httpx.Response(200,json={'message':{'content':'```json\n{"proposals":[]}\n``````json\n{"approve":true}'}}))
    state=engine.create_project('Envelope test','under_15k_sgd');engine.add_reference(state,{'id':'r1','note':'cream'})
    proposals,usage=Gateway().analyse(state,tmp_path)
    assert proposals==[] and usage['ignoredTrailingOutput']


def test_model_result_cannot_overwrite_a_newer_human_edit(tmp_path):
    app=create_app(tmp_path/'db',tmp_path/'images')
    client=TestClient(app)
    p=client.post('/api/demo/start').json();base='/api/projects/'+p['id']
    class ConcurrentGateway:
        mode='gateway'
        prompt_version='test'
        def analyse(self,snapshot,upload_dir):
            app.state.store.mutate(p['id'],'human_edit','homeowner',lambda s:engine.add_preferences(s,['Newer goal'],[]))
            return [], {'mode':'gateway_notes','inputTokens':10,'outputTokens':10}
    app.state.gateway=ConcurrentGateway()
    assert client.post(base+'/analysis-runs').status_code==409
    assert client.get(base).json()['goals']==['Newer goal']
    assert client.get(base+'/analysis-runs').json()[0]['status']=='failed'


def test_note_only_input_supports_users_without_images(tmp_path):
    client=TestClient(create_app(tmp_path/'db',tmp_path/'images'))
    p=client.post('/api/projects',json={'name':'Notes only','budgetBand':'under_15k_sgd'}).json()
    base='/api/projects/'+p['id']
    assert client.post(base+'/reference-notes',json={'note':'I like light oak'}).status_code==422
    p=client.post(base+'/reference-notes',json={'note':'I like light oak','consent':True,'expectedStateVersion':p['stateVersion']}).json()
    assert p['references'][0]['status']=='note'
    assert client.post(base+'/analysis-runs').json()['attributes'][0]['value']=='light_oak'
