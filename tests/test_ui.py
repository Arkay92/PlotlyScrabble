from pathlib import Path
from dash import Dash
import pytest
from wordgame.ui import configure_app
import random
from wordgame.rules import new_game


def _make_inputs(action=None, mode='pvp', dictionary='en_GB', search='', pathname='/', start_clicks=0, **kwargs):
    return [
        {'id': 'action', 'property': 'data', 'value': action},
        {'id': 'url', 'property': 'search', 'value': search},
        {'id': 'url', 'property': 'pathname', 'value': pathname},
        {'id': 'mp-poll', 'property': 'n_intervals', 'value': 0},
        {'id': 'auth-login-btn', 'property': 'n_clicks', 'value': kwargs.get('login_clicks', 0)},
        {'id': 'auth-register-btn', 'property': 'n_clicks', 'value': kwargs.get('register_clicks', 0)},
        {'id': 'auth-guest-btn', 'property': 'n_clicks', 'value': kwargs.get('guest_clicks', 0)},
        {'id': 'auth-logout-btn', 'property': 'n_clicks', 'value': kwargs.get('logout_clicks', 0)},
        {'id': 'auth-username', 'property': 'n_submit', 'value': 0},
        {'id': 'auth-password', 'property': 'n_submit', 'value': 0},
        {'id': 'brand-home-btn', 'property': 'n_clicks', 'value': kwargs.get('brand_clicks', 0)},
        {'id': 'nav-play-btn', 'property': 'n_clicks', 'value': kwargs.get('play_btn_clicks', 0)},
        {'id': 'nav-leaderboard-btn', 'property': 'n_clicks', 'value': kwargs.get('nav_lb_clicks', 0)},
        {'id': 'leaderboard-back-btn', 'property': 'n_clicks', 'value': kwargs.get('lb_back_clicks', 0)},
        {'id': 'nav-about-btn', 'property': 'n_clicks', 'value': kwargs.get('nav_about_clicks', 0)},
        {'id': 'footer-about-btn', 'property': 'n_clicks', 'value': 0},
        {'id': 'menu-about-btn', 'property': 'n_clicks', 'value': 0},
        {'id': 'about-back-btn', 'property': 'n_clicks', 'value': 0},
        {'id': 'about-tab-tech-btn', 'property': 'n_clicks', 'value': kwargs.get('about_tech_clicks', 0)},
        {'id': 'about-tab-why-btn', 'property': 'n_clicks', 'value': kwargs.get('about_why_clicks', 0)},
        {'id': 'nav-profile-btn', 'property': 'n_clicks', 'value': kwargs.get('nav_profile_clicks', 0)},
        {'id': 'profile-back-btn', 'property': 'n_clicks', 'value': 0},
        {'id': 'profile-save-btn', 'property': 'n_clicks', 'value': kwargs.get('save_profile_clicks', 0)},
        {'id': 'profile-password-btn', 'property': 'n_clicks', 'value': 0},
        {'id': 'profile-woogles-btn', 'property': 'n_clicks', 'value': 0},
        {'id': 'profile-isc-btn', 'property': 'n_clicks', 'value': 0},
        {'id': 'start', 'property': 'n_clicks', 'value': start_clicks},
        {'id': 'mode', 'property': 'value', 'value': mode},
        {'id': 'dictionary', 'property': 'value', 'value': dictionary},
        {'id': 'mp-tab-lobby-btn', 'property': 'n_clicks', 'value': kwargs.get('mp_tab_lobby_clicks', 0)},
        {'id': 'mp-tab-find-btn', 'property': 'n_clicks', 'value': kwargs.get('mp_tab_find_clicks', 0)},
        {'id': 'mp-host-btn', 'property': 'n_clicks', 'value': kwargs.get('mp_host_clicks', 0)},
        {'id': 'mp-create-btn', 'property': 'n_clicks', 'value': kwargs.get('mp_create_clicks', 0)},
        {'id': 'mp-choose-join-btn', 'property': 'n_clicks', 'value': kwargs.get('mp_choose_join_clicks', 0)},
        {'id': 'mp-join-submit', 'property': 'n_clicks', 'value': kwargs.get('mp_join_clicks', 0)},
        {'id': 'join-code-input', 'property': 'n_submit', 'value': 0},
        {'id': 'mp-back-choice', 'property': 'n_clicks', 'value': 0},
        {'id': 'mp-leave-btn', 'property': 'n_clicks', 'value': 0},
    ]


def _make_state(session_data=None, screen='home', saved_games=None, auth_data=None, **kwargs):
    return [
        {'id': 'session', 'property': 'data', 'value': session_data},
        {'id': 'saved-games-store', 'property': 'data', 'value': saved_games or []},
        {'id': 'auth-store', 'property': 'data', 'value': auth_data or {'role': 'guest', 'username': 'guest', 'display_name': 'Guest', 'avatar': 'A'}},
        {'id': 'active-screen', 'property': 'data', 'value': screen},
        {'id': 'viewed-profile', 'property': 'data', 'value': None},
        {'id': 'about-subtab', 'property': 'data', 'value': 'tech'},
        {'id': 'mp-tab', 'property': 'data', 'value': 'lobby'},
        {'id': 'auth-username', 'property': 'value', 'value': kwargs.get('auth_user', '')},
        {'id': 'auth-password', 'property': 'value', 'value': kwargs.get('auth_pass', '')},
        {'id': 'player-one', 'property': 'value', 'value': kwargs.get('p1', 'Alice')},
        {'id': 'player-two', 'property': 'value', 'value': kwargs.get('p2', 'Bob')},
        {'id': 'join-code-input', 'property': 'value', 'value': kwargs.get('join_code', '')},
        {'id': 'profile-display-name', 'property': 'value', 'value': kwargs.get('disp_name', 'Alice')},
        {'id': 'profile-avatar-select', 'property': 'value', 'value': 'A'},
        {'id': 'profile-current-password', 'property': 'value', 'value': ''},
        {'id': 'profile-new-password', 'property': 'value', 'value': ''},
        {'id': 'profile-woogles-input', 'property': 'value', 'value': ''},
        {'id': 'profile-isc-input', 'property': 'value', 'value': ''},
    ]


def test_setup_requires_dictionary_and_app_assets_work():
    app = Dash(__name__, assets_folder=str(Path(__file__).resolve().parents[1]/'assets'))
    configure_app(app)
    client = app.server.test_client()
    assert client.get('/').status_code == 200
    assert client.get('/assets/board.js').status_code == 200
    assert client.get('/assets/styles.css').status_code == 200
    assert client.get('/_dash-layout').status_code == 200

    output, config = next(iter(app.callback_map.items()))

    def invoke(trigger, inputs, states):
        response = client.post('/_dash-update-component', json={
            'output': output,
            'outputs': [{'id': o.component_id, 'property': o.component_property} for o in config['output']],
            'inputs': inputs,
            'state': states,
            'changedPropIds': [trigger]
        })
        assert response.status_code == 200
        return response.get_json()['response']

    # Without dictionary, start should be disabled
    inputs = _make_inputs(dictionary=None, start_clicks=1)
    states = _make_state()
    rejected = invoke('start.n_clicks', inputs, states)
    assert rejected['session']['data'] is None
    assert rejected['start']['disabled']

    # With valid dictionary, game starts
    inputs = _make_inputs(dictionary='en_GB', start_clicks=1)
    started = invoke('start.n_clicks', inputs, states)
    assert started['session']['data']['dictionary'] == 'en_GB'
    assert started['active-screen']['data'] == 'game'
    assert started['home-screen']['style'] == {'display': 'none'}

    # Home action returns to home screen
    inputs = _make_inputs(action={'type': 'home'})
    states = _make_state(session_data=started['session']['data'], screen='game')
    reset = invoke('action.data', inputs, states)
    assert reset['session']['data'] is None
    assert reset['active-screen']['data'] == 'home'
    assert reset['home-screen']['style'] == {}


def test_computer_mode_replies_after_human_pass_and_persists_mode():
    app = Dash(__name__)
    configure_app(app)
    client = app.server.test_client()
    output, config = next(iter(app.callback_map.items()))
    state = new_game('en_US', ('Alice', 'Computer'), rng=random.Random(1), mode='computer')

    inputs = _make_inputs(action={'type': 'pass'}, mode='computer', dictionary='en_US')
    states = _make_state(session_data=state, screen='game')

    response = client.post('/_dash-update-component', json={
        'output': output,
        'outputs': [{'id': o.component_id, 'property': o.component_property} for o in config['output']],
        'inputs': inputs,
        'state': states,
        'changedPropIds': ['action.data']
    })
    assert response.status_code == 200
    after = response.get_json()['response']['session']['data']
    assert after['mode'] == 'computer' and after['dictionary'] == 'en_US'
    assert len(after['history']) == 2
    assert after['turn'] == 0
    assert 'Computer' in after['ai_message']


@pytest.mark.parametrize('mode,finished', [('pvp', False), ('pvp', True), ('computer', False), ('computer', True)])
def test_new_game_preserves_settings_and_home_clears_game(mode, finished):
    app = Dash(__name__)
    configure_app(app)
    client = app.server.test_client()
    output, config = next(iter(app.callback_map.items()))
    state = new_game('en_GB', ('Alice', 'Bob'), rng=random.Random(8), mode=mode)
    state.update(scores=[17, 8], turn=1, handoff=True, finished=finished)
    state['board'] = {'112': {'letter': 'A', 'blank': False}}
    state['history'] = [{'player': 0, 'kind': 'pass', 'score': 0}]

    def invoke(kind, current):
        inputs = _make_inputs(action={'type': kind}, mode=mode, dictionary='en_GB')
        states = _make_state(session_data=current, screen='game')
        response = client.post('/_dash-update-component', json={
            'output': output,
            'outputs': [{'id': o.component_id, 'property': o.component_property} for o in config['output']],
            'inputs': inputs,
            'state': states,
            'changedPropIds': ['action.data']
        })
        assert response.status_code == 200
        return response.get_json()['response']

    restarted = invoke('restart', state)
    fresh = restarted['session']['data']
    assert fresh['mode'] == mode and fresh['dictionary'] == 'en_GB'
    assert fresh['players'] == state['players']
    assert fresh['scores'] == [0, 0] and not fresh['board'] and not fresh['history']
    assert fresh['turn'] == 0 and not fresh['finished'] and not fresh['handoff']
    assert len(fresh['bag']) == 86 and all(len(r) == 7 for r in fresh['racks'])
    assert restarted['home-screen']['style'] == {'display': 'none'}

    home = invoke('home', state)
    assert home['session']['data'] is None
    assert home['game-view-container']['style'] == {'display': 'none'}
    assert home['home-screen']['style'] == {}


def test_auth_and_navigation():
    app = Dash(__name__)
    configure_app(app)
    client = app.server.test_client()
    output, config = next(iter(app.callback_map.items()))
    outputs_def = [{'id': o.component_id, 'property': o.component_property} for o in config['output']]

    # 1. Fresh unauthenticated visit shows auth screen and hides user menu
    inputs = _make_inputs()
    states = _make_state(auth_data={})
    # Passing empty auth_data dict will trigger unauthenticated state
    states[2]['value'] = None
    res = client.post('/_dash-update-component', json={
        'output': output,
        'outputs': outputs_def,
        'inputs': inputs,
        'state': states,
        'changedPropIds': []
    }).get_json()['response']
    assert res['auth-screen']['style']['display'] == 'flex'
    assert res['home-screen']['style']['display'] == 'none'
    assert res['user-menu']['style']['display'] == 'none'
    assert res['user-badge']['children'] == 'Welcome'

    # 2. Click "Play as guest →"
    inputs = _make_inputs(guest_clicks=1)
    res = client.post('/_dash-update-component', json={
        'output': output,
        'outputs': outputs_def,
        'inputs': inputs,
        'state': states,
        'changedPropIds': ['auth-guest-btn.n_clicks']
    }).get_json()['response']
    assert res['auth-store']['data']['role'] == 'guest'
    assert res['user-badge']['children'] == 'Playing as Guest'
    assert res['user-menu']['style']['display'] == 'inline-block'
    assert res['home-screen']['style'] == {}
    assert res['auth-screen']['style']['display'] == 'none'

    # 3. Leaderboard navigation as authenticated user
    inputs = _make_inputs(nav_lb_clicks=1)
    states = _make_state(auth_data=res['auth-store']['data'])
    res = client.post('/_dash-update-component', json={
        'output': output,
        'outputs': outputs_def,
        'inputs': inputs,
        'state': states,
        'changedPropIds': ['nav-leaderboard-btn.n_clicks']
    }).get_json()['response']
    assert res['active-screen']['data'] == 'leaderboard'
    assert res['leaderboard-screen']['style'] == {}

    # 4. About navigation and tab switching
    inputs = _make_inputs(about_why_clicks=1)
    states = _make_state(screen='about')
    res = client.post('/_dash-update-component', json={
        'output': output,
        'outputs': outputs_def,
        'inputs': inputs,
        'state': states,
        'changedPropIds': ['about-tab-why-btn.n_clicks']
    }).get_json()['response']
    assert res['about-subtab']['data'] == 'why'

    # 5. Click "Switch account" (logout)
    inputs = _make_inputs(logout_clicks=1)
    states = _make_state()
    res = client.post('/_dash-update-component', json={
        'output': output,
        'outputs': outputs_def,
        'inputs': inputs,
        'state': states,
        'changedPropIds': ['auth-logout-btn.n_clicks']
    }).get_json()['response']
    assert res['auth-store']['data'] is None
    assert res['auth-screen']['style']['display'] == 'flex'
    assert res['home-screen']['style']['display'] == 'none'
    assert res['user-menu']['style']['display'] == 'none'
    assert 'Signed out' in res['auth-feedback']['children']

    # 6. Register a new user
    import time
    test_user = f'user_{int(time.time()*1000)}'
    inputs = _make_inputs(register_clicks=1)
    states = _make_state(auth_data={}, auth_user=test_user, auth_pass='pass1234')
    states[2]['value'] = None
    res = client.post('/_dash-update-component', json={
        'output': output,
        'outputs': outputs_def,
        'inputs': inputs,
        'state': states,
        'changedPropIds': ['auth-register-btn.n_clicks']
    }).get_json()['response']
    assert res['auth-store']['data']['role'] == 'user'
    assert res['auth-store']['data']['username'] == test_user
    assert test_user in res['user-badge']['children']
    assert res['user-menu']['style']['display'] == 'inline-block'
    assert res['home-screen']['style'] == {}

    # 7. Log out and log back in with test_user
    inputs = _make_inputs(logout_clicks=2)
    states = _make_state(auth_data=res['auth-store']['data'])
    res = client.post('/_dash-update-component', json={
        'output': output,
        'outputs': outputs_def,
        'inputs': inputs,
        'state': states,
        'changedPropIds': ['auth-logout-btn.n_clicks']
    }).get_json()['response']
    assert res['auth-store']['data'] is None
    assert res['auth-screen']['style']['display'] == 'flex'

    inputs = _make_inputs(login_clicks=1)
    states = _make_state(auth_data={}, auth_user=test_user, auth_pass='pass1234')
    states[2]['value'] = None
    res = client.post('/_dash-update-component', json={
        'output': output,
        'outputs': outputs_def,
        'inputs': inputs,
        'state': states,
        'changedPropIds': ['auth-login-btn.n_clicks']
    }).get_json()['response']
    assert res['auth-store']['data']['username'] == test_user
    assert res['home-screen']['style'] == {}
    assert res['user-menu']['style']['display'] == 'inline-block'

    # 8. Start a local game as logged in user - ensure auth is preserved
    logged_in_auth = res['auth-store']['data']
    inputs = _make_inputs(start_clicks=1, mode='computer', dictionary='en_US')
    states = _make_state(screen='home', auth_data=logged_in_auth, p1='')
    res = client.post('/_dash-update-component', json={
        'output': output,
        'outputs': outputs_def,
        'inputs': inputs,
        'state': states,
        'changedPropIds': ['start.n_clicks']
    }).get_json()['response']
    assert res['auth-store']['data']['role'] == 'user'
    assert res['auth-store']['data']['username'] == test_user
    assert res['session']['data']['auth']['username'] == test_user
    assert res['session']['data']['players'][0] == test_user

    # 9. Return home - ensure user remains logged in (never reverts to guest)
    inputs = _make_inputs(brand_clicks=1)
    states = _make_state(session_data=res['session']['data'], screen='game', auth_data=logged_in_auth)
    res = client.post('/_dash-update-component', json={
        'output': output,
        'outputs': outputs_def,
        'inputs': inputs,
        'state': states,
        'changedPropIds': ['brand-home-btn.n_clicks']
    }).get_json()['response']
    assert res['auth-store']['data']['role'] == 'user'
    assert res['auth-store']['data']['username'] == test_user
    assert test_user in res['user-badge']['children']
