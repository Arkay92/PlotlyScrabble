from pathlib import Path
from dash import Dash
import pytest
from wordgame.ui import configure_app


def test_setup_requires_dictionary_and_app_assets_work():
    app = Dash(__name__,assets_folder=str(Path(__file__).resolve().parents[1]/'assets'))
    configure_app(app)
    client = app.server.test_client()
    assert client.get('/').status_code==200
    assert client.get('/assets/board.js').status_code==200
    assert client.get('/assets/styles.css').status_code==200
    assert client.get('/_dash-layout').status_code==200
    output,config = next(iter(app.callback_map.items()))
    inputs = [{'id':'action','property':'data','value':None},{'id':'start','property':'n_clicks','value':1},
              {'id':'dictionary','property':'value','value':None},
              {'id':'mode','property':'value','value':'pvp'}]
    states = [{'id':'player-one','property':'value','value':'Alice'},{'id':'player-two','property':'value','value':'Bob'},
              {'id':'session','property':'data','value':None}]
    def invoke(trigger):
        response = client.post('/_dash-update-component',json={
            'output':output,'outputs':[{'id':o.component_id,'property':o.component_property} for o in config['output']],
            'inputs':inputs,'state':states,'changedPropIds':[trigger]})
        assert response.status_code==200
        return response.get_json()['response']
    rejected = invoke('start.n_clicks')
    assert rejected['session']['data'] is None
    assert rejected['start']['disabled']
    inputs[2]['value']='en_GB'
    started = invoke('start.n_clicks')
    assert started['session']['data']['dictionary']=='en_GB'
    assert started['setup']['style']=={'display':'none'}
    states[2]['value']=started['session']['data']
    inputs[2]['value']='en_US'
    unchanged = invoke('dictionary.value')
    assert unchanged['session']['data']['dictionary']=='en_GB'
    inputs[0]['value']={'type':'new'}
    reset = invoke('action.data')
    assert reset['session']['data'] is None


def test_computer_mode_replies_after_human_pass_and_persists_mode():
    import random
    from wordgame.rules import new_game
    app = Dash(__name__)
    configure_app(app)
    client = app.server.test_client()
    output,config = next(iter(app.callback_map.items()))
    state = new_game('en_US',('Alice','Bob'),rng=random.Random(1),mode='computer')
    response = client.post('/_dash-update-component',json={
        'output':output,'outputs':[{'id':o.component_id,'property':o.component_property} for o in config['output']],
        'inputs':[{'id':'action','property':'data','value':{'type':'pass'}},
                  {'id':'start','property':'n_clicks','value':1},{'id':'dictionary','property':'value','value':'en_GB'},
                  {'id':'mode','property':'value','value':'pvp'}],
        'state':[{'id':'player-one','property':'value','value':'Alice'},
                 {'id':'player-two','property':'value','value':'Bob'},
                 {'id':'session','property':'data','value':state}],
        'changedPropIds':['action.data']})
    assert response.status_code==200
    after = response.get_json()['response']['session']['data']
    assert after['mode']=='computer' and after['dictionary']=='en_US'
    assert len(after['history'])==2
    assert after['turn']==0 and not after['handoff']
    assert 'Computer' in after['ai_message']


@pytest.mark.parametrize('mode,finished',[('pvp',False),('pvp',True),('computer',False),('computer',True)])
def test_new_game_preserves_settings_and_home_clears_game(mode,finished):
    import random
    from wordgame.rules import new_game
    app = Dash(__name__)
    configure_app(app)
    client = app.server.test_client()
    output,config = next(iter(app.callback_map.items()))
    state = new_game('en_GB',('Alice','Bob'),rng=random.Random(8),mode=mode)
    state.update(scores=[17,8],turn=1,handoff=True,finished=finished)
    state['board']={'112':{'letter':'A','blank':False}}
    state['history']=[{'player':0,'kind':'pass','score':0}]
    def invoke(kind,current):
        response = client.post('/_dash-update-component',json={
            'output':output,'outputs':[{'id':o.component_id,'property':o.component_property} for o in config['output']],
            'inputs':[{'id':'action','property':'data','value':{'type':kind}},
                      {'id':'start','property':'n_clicks','value':1},
                      {'id':'dictionary','property':'value','value':'en_US'},
                      {'id':'mode','property':'value','value':'pvp'}],
            'state':[{'id':'player-one','property':'value','value':'Different name'},
                     {'id':'player-two','property':'value','value':'Different name'},
                     {'id':'session','property':'data','value':current}],
            'changedPropIds':['action.data']})
        assert response.status_code==200
        return response.get_json()['response']
    restarted = invoke('restart',state)
    fresh = restarted['session']['data']
    assert fresh['mode']==mode and fresh['dictionary']=='en_GB'
    assert fresh['players']==state['players']
    assert fresh['scores']==[0,0] and not fresh['board'] and not fresh['history']
    assert fresh['turn']==0 and not fresh['finished'] and not fresh['handoff']
    assert len(fresh['bag'])==86 and all(len(r)==7 for r in fresh['racks'])
    assert restarted['setup']['style']=={'display':'none'}
    home = invoke('home',state)
    assert home['session']['data'] is None
    assert home['game-view']['style']=={'display':'none'}
    assert home['setup']['style']=={}
