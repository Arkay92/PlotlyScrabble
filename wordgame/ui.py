"""Interactive Scrabble web UI with authentication, multiplayer, leaderboards, and profile tracking."""
import secrets
import time
from urllib.parse import parse_qs

from dash import Input, Output, State, ctx, dcc, html, no_update

from .ai import ScrabbleAI
from .auth import DEFAULT_AUTH, rank_for_rating
from .dictionaries import DICTIONARIES
from .multiplayer import DEFAULT_HUB
from .rules import CENTER, POINTS, PREMIUMS, act, evaluate, new_game

AVATAR_OPTIONS = [
    {'label': f'Tile {c} ({POINTS[c]} pt{"s" if POINTS[c] != 1 else ""})', 'value': c}
    for c in 'AEIOULNSTRDGBCMPFHVWYKJXQZ'
] + [{'label': '★ Blank / Wild (0 pts)', 'value': '★'}]


def tile(letter, blank=False):
    pts = '0' if blank else str(POINTS.get(letter, 0))
    classes = 'letter-tile blank-tile' if blank else 'letter-tile'
    return html.Span([
        html.Span(letter, className='tile-letter'),
        html.Sub(pts, className='tile-points')
    ], className=classes)


def avatar_badge(letter, class_name='user-avatar-badge'):
    return html.Span(letter or 'A', className=class_name)


def control(label, action, class_name='button secondary', disabled=False, **extra):
    return html.Button(label, type='button', className=class_name, disabled=disabled,
                       **{'data-action': action, **extra})


def extract_code_from_url(search, pathname=None):
    if search:
        params = parse_qs(search.lstrip('?'))
        for key in ('code', 'game', 'join', 'room'):
            values = params.get(key)
            if values and values[0].strip():
                return values[0].strip().upper()
    if pathname and pathname.startswith('/join/'):
        code = pathname.split('/join/', 1)[1].strip('/').upper()
        if code:
            return code
    return None


def board_view(state, player_idx=None):
    is_my_turn = (player_idx is None or state['turn'] == player_idx) and not state.get('handoff') and not state.get('finished')
    cells = []
    for square in range(225):
        key = str(square)
        draft = state['pending'].get(key)
        placed = draft or state['board'].get(key)
        premium = PREMIUMS.get(key, '')
        classes = ['board-cell', premium.lower() or 'plain']
        label = f'{chr(65+square%15)}{square//15+1}'
        if placed:
            children = tile(placed['letter'], placed['blank'])
            label += f', {placed["letter"]}' + (', blank tile' if placed['blank'] else '')
            classes.append('draft' if draft else 'committed')
        else:
            children = html.Span('★' if square == CENTER else premium, className='premium-label')
            label += f', {premium or "empty"}'
        if key in state.get('last', set()):
            classes.append('last-play')
        if state.get('selected') == f'cell:{key}':
            classes.append('selected')
        cells.append(html.Button(
            children, id=f'cell-{square}', type='button', className=' '.join(classes),
            title=label, **{
                'aria-label': label,
                'data-cell': key,
                'data-action': 'cell',
                'data-source': f'cell:{key}' if draft else '',
                'data-draggable': str(bool(draft and is_my_turn)).lower()
            }
        ))
    return html.Div([
        html.Div([html.Span(chr(65+i)) for i in range(15)], className='column-labels'),
        html.Div([
            html.Div([html.Span(str(i+1)) for i in range(15)], className='row-labels'),
            html.Div(cells, className='scrabble-grid', role='group', **{'aria-label': '15 by 15 word board'})
        ], className='board-with-ranks'),
    ], className='board-frame')


def rack_view(state, player_idx=None):
    turn = state['turn']
    is_mp = bool(state.get('mp'))
    active_player = player_idx if (is_mp and player_idx is not None) else turn
    is_my_turn = (player_idx is None or turn == player_idx) and not state.get('finished')

    if state.get('mode') == 'computer' and turn == 1 and not state['finished']:
        return html.Div([
            html.H3('Computer turn'),
            html.P('The computer’s rack stays hidden.'),
            control('Retry computer move', 'retry', 'button secondary')
        ], className='handoff')

    if state.get('handoff') and not state['finished'] and not is_mp:
        return html.Div([
            html.Div('YOUR TURN', className='eyebrow'),
            html.H3(f"Pass the device to {state['players'][turn]}"),
            html.P('Keep your letters to yourself. Reveal your rack when you are ready.'),
            control('Reveal my tiles →', 'ready', 'button primary')
        ], className='handoff')

    if state.get('finished'):
        top = max(state['scores'])
        leaders = [state['players'][i] for i, score in enumerate(state['scores']) if score == top]
        return html.Div([
            html.Div('FINAL SCORE', className='eyebrow'),
            html.H3('A well-played draw.' if len(leaders) > 1 else f'{leaders[0]} wins!'),
            html.P(state.get('end_reason', 'Game over.')),
            control('Play another game', 'restart', 'button primary')
        ], className='handoff')

    used = {t['rack'] for t in state['pending'].values()}
    slots = []
    rack_tiles = state['racks'][active_player] if active_player < len(state['racks']) else []

    for index, letter in enumerate(rack_tiles):
        classes = ['rack-slot']
        if index in used:
            classes.append('used')
        if state.get('selected') == f'rack:{index}' or index in state.get('exchange_tiles', set()):
            classes.append('selected')
        slots.append(html.Button(
            tile(letter) if index not in used else html.Span('·'),
            id=f'rack-{index}', className=' '.join(classes), type='button',
            **{
                'aria-label': f'Rack tile {index+1}: {"blank" if letter == "?" else letter}',
                'aria-pressed': str('selected' in classes).lower(),
                'data-action': 'rack',
                'data-slot': str(index),
                'data-source': f'rack:{index}',
                'data-draggable': str(bool(index not in used and not state.get('exchange') and is_my_turn)).lower()
            }
        ))

    heading_title = state['players'][active_player] if active_player < len(state['players']) else 'Your Rack'
    if is_mp and not is_my_turn:
        heading_sub = f"Waiting for {state['players'][turn]} to play..."
    else:
        heading_sub = 'YOUR LETTERS'

    return html.Div([
        html.Div([
            html.Div([html.Span(heading_sub, className='eyebrow'), html.Strong(heading_title)]),
            control('↻  Shuffle', 'shuffle', 'text-button', bool(used) or state.get('exchange') or not is_my_turn)
        ], className='rack-heading'),
        html.Div(slots, className='rack', role='group', **{'aria-label': 'Your tile rack', 'data-rack-target': 'true'}),
        html.Div([
            html.Span('Blank tile represents'),
            html.Select([html.Option(chr(i), value=chr(i), selected=(chr(i) == state.get('blank_choice', 'A'))) for i in range(65, 91)],
                        id='blank-letter', **{'aria-label': 'Letter represented by blank tiles'}),
            html.Span('Choose before placing a blank.', className='blank-help')
        ], className='blank-picker'),
    ], className='rack-panel')


def game_view(state, message, player_idx=None):
    is_mp = bool(state.get('mp'))
    is_my_turn = (player_idx is None or state['turn'] == player_idx)
    active = not state.get('handoff') and not state.get('finished') and not (state.get('mode') == 'computer' and state['turn'] == 1) and is_my_turn

    scorecards = []
    for i, name in enumerate(state['players']):
        is_current = (i == state['turn'] and not state['finished'])
        sub = 'Your turn' if (is_current and (player_idx is None or player_idx == i)) else ('Opponent turn' if is_current else f'Player {i+1}')
        scorecards.append(html.Div([
            html.Div([
                html.Span(f'0{i+1}', className='player-avatar'),
                html.Div([html.Strong(name), html.Small(sub)])
            ], className='player-info'),
            html.Span(str(state['scores'][i]), className='score')
        ], className='player-card active' if is_current else 'player-card'))

    preview, valid = 'Place tiles to build your word.', False
    if state.get('pending'):
        try:
            result = evaluate(state)
            preview = ' + '.join(f"{w['word']} ({w['score']})" for w in result['words'])
            if result['bonus']:
                preview += ' + 50 bingo'
            preview += f" = {result['score']} points"
            valid = True
        except ValueError as error:
            preview = str(error)

    history = [
        html.Div([
            html.Span(str(index+1).zfill(2), className='move-number'),
            html.Div([
                html.Strong(', '.join(w['word'] for w in event['words']) if event['kind'] == 'play' else
                            'Passed' if event['kind'] == 'pass' else f"Exchanged {event['count']} tiles"),
                html.Small(state['players'][event['player']])
            ]),
            html.Span(f"+{event['score']}", className='history-score')
        ], className='history-row')
        for index, event in reversed(list(enumerate(state.get('history', []))))
    ]

    mp_banner = None
    if is_mp:
        mp_info = state.get('mp') or {}
        code = mp_info.get('code', '')
        connected = mp_info.get('connected', False)
        mp_banner = html.Div([
            html.Div([
                html.Span(className='online-dot' if connected else 'status-dot offline', style={'marginRight': '6px'}),
                html.Strong(f"Room {code}"),
                html.Span('Connected' if connected else 'Waiting for player…', className='muted', style={'marginLeft': '8px', 'fontSize': '11px'}),
            ], style={'display': 'flex', 'alignItems': 'center'}),
            html.Div([
                html.Button('Copy code', id='mp-copy-btn', type='button', className='button quiet',
                            **{'data-code': code}, style={'padding': '4px 8px', 'fontSize': '10px'}),
                html.Button('Share link', id='mp-copy-link-btn', type='button', className='button quiet',
                            **{'data-code': code}, style={'padding': '4px 8px', 'fontSize': '10px'}),
                control('Leave game', 'leave-room', 'button quiet', id='mp-game-leave-btn',
                        style={'padding': '4px 8px', 'fontSize': '10px', 'color': '#c56a49'}),
            ], style={'display': 'flex', 'gap': '6px', 'marginLeft': 'auto'})
        ], className='panel mp-session', **{'data-room-code': code},
           style={'padding': '8px 12px', 'marginBottom': '12px', 'display': 'flex', 'alignItems': 'center'})

    mode_badge = 'MULTIPLAYER' if is_mp else ('VS COMPUTER' if state.get('mode') == 'computer' else 'TWO PLAYERS')

    return html.Div([
        html.Div([
            html.Div([
                html.P('MAKE EVERY LETTER COUNT', className='eyebrow'),
                html.H1('A little room for a big word.')
            ]),
            html.Div([
                html.Div([html.Span('●', className='online-dot'), DICTIONARIES[state['dictionary']][0]], className='dictionary-badge'),
                control('New game', 'restart', 'button secondary', id='new-game') if not is_mp else None,
                control('Back to home', 'home', 'button quiet', id='back-home'),
            ], className='page-tools')
        ], className='page-intro'),

        mp_banner,

        html.Div([
            html.Section([
                html.Div([
                    html.Span(f"{state['players'][state['turn']]} to play" if not state.get('finished') else 'Game complete'),
                    html.Span(f"{len(state.get('bag', []))} tiles in the bag", id='bag-count')
                ], className='board-caption'),
                html.Div(board_view(state, player_idx=player_idx), className='board-shell'),
                html.Div('Drag a tile onto the board, or click a tile and a square. Draft tiles can be moved or recalled.', className='board-help'),
                rack_view(state, player_idx=player_idx)
            ], className='play-area'),

            html.Aside([
                html.Section([
                    html.Div([html.H2('Your game'), html.Span(mode_badge, className='small-badge')], className='card-heading'),
                    *scorecards,
                    html.Div(message, id='feedback', className='feedback', role='status', **{'aria-live': 'polite'}),
                    html.Div(preview, id='preview', className='score-preview valid' if valid else 'score-preview'),
                    control('Play word →', 'play', 'button primary full', not active or not valid, id='play-word'),
                    html.Div([
                        control('Recall tiles', 'recall', 'button secondary', not active or not state.get('pending')),
                        control('Pass turn', 'pass', 'button quiet', not active)
                    ], className='game-actions'),
                    control('Cancel exchange' if state.get('exchange') else 'Exchange tiles', 'exchange', 'text-button full',
                            not active or len(state.get('bag', [])) < 7),
                    control(f"Exchange {len(state.get('exchange_tiles', []))} selected tiles", 'exchange-confirm', 'button primary full',
                            not state.get('exchange_tiles')) if state.get('exchange') else None,
                ], className='panel'),

                html.Section([
                    html.Div([html.H2('Word history'), html.Span(f"{len(history)} turns", id='turn-count', className='muted')], className='card-heading'),
                    html.Div(history or [html.P('Your next idea starts here.', className='history-empty')], className='history-list')
                ], className='panel history-panel'),

                html.Details([
                    html.Summary('A quick guide'),
                    html.P('First word: cover the centre star. After that, connect to the board. Every word you form must be in the selected dictionary.'),
                    html.P('Use all seven tiles for a 50-point bonus. Blanks score zero and keep their chosen letter.'),
                    html.P('Exchange needs at least seven tiles in the bag. Six scoreless turns end the game, with remaining tile values deducted.'),
                    html.P('To remove one draft tile, drag it back to the rack.'),
                    html.P('Regional ESDB casual dictionaries for casual play.')
                ], className='panel guide'),

                html.Div('NPC conditional expert routing', className='npc-badge') if state.get('mode') == 'computer' else None,
                html.Details([
                    html.Summary('Computer decision'),
                    html.P(state.get('ai_message', 'The computer will respond after your turn.')),
                    html.P('Score, rack balance and defence specialists. Normalized categorical sum-product circuits combined via gradient-trained gating.'),
                    *[html.P('Expert weights: ' + ', '.join(f'{w:.0%}' for w in event['ai']['weights']))
                      for event in state.get('history', [])[-1:] if 'weights' in event.get('ai', {})]
                ], className='panel guide') if state.get('mode') == 'computer' else None,
            ], className='game-sidebar'),
        ], className='game-layout'),

        html.Div([
            html.Span([html.I(className='legend dw'), 'Double word']),
            html.Span([html.I(className='legend tw'), 'Triple word']),
            html.Span([html.I(className='legend dl'), 'Double letter']),
            html.Span([html.I(className='legend tl'), 'Triple letter'])
        ], className='board-legend'),
    ], className='current-game')


def render_recent_games(matches):
    """Render community feed cards of recent completed multiplayer matches."""
    if not matches:
        return html.Div([
            html.P('No multiplayer games completed yet. Host or join a match to be the first on the board!',
                   style={'fontSize': '12px', 'color': '#7a827e', 'margin': '14px 0', 'fontStyle': 'italic'})
        ], style={'background': '#fafbf8', 'border': '1px dashed #d5d9d1', 'borderRadius': '8px', 'textAlign': 'center', 'padding': '16px 14px', 'marginTop': '8px'})

    cards = []
    for m in matches:
        p1_user = m.get('p1_user')
        p2_user = m.get('p2_user')
        p1_name = m.get('p1_name') or 'Player 1'
        p2_name = m.get('p2_name') or 'Player 2'
        p1_score = m.get('p1_score', 0)
        p2_score = m.get('p2_score', 0)
        turns = m.get('turns_count', 0)
        score_str = f"{p1_score} - {p2_score}"

        score_class = 'draw'
        if p1_score > p2_score:
            score_class = 'win-p1'
        elif p2_score > p1_score:
            score_class = 'win-p2'

        p1_btn = html.Button(p1_name, type='button', className='feed-player-btn',
                             **{'data-view-profile': p1_user}) if p1_user else html.Span(p1_name, className='feed-player-plain')
        p2_btn = html.Button(p2_name, type='button', className='feed-player-btn',
                             **{'data-view-profile': p2_user}) if p2_user else html.Span(p2_name, className='feed-player-plain')

        cards.append(html.Div([
            html.Div([
                html.Span(m.get('p1_avatar', 'A'), className='feed-avatar'),
                p1_btn,
            ], className='feed-player feed-player-p1'),
            html.Div([
                html.Span(score_str, className=f'feed-score-badge {score_class}'),
                html.Small(f"{turns} turns", className='feed-detail'),
            ], className='feed-center'),
            html.Div([
                p2_btn,
                html.Span(m.get('p2_avatar', 'E'), className='feed-avatar'),
            ], className='feed-player feed-player-p2'),
        ], className='feed-match-card'))
    return html.Div(cards, className='feed-grid')


def render_friends_widget_content(friends, auth):
    """Render friend list items with online status indicator dots."""
    if not auth or auth.get('role') != 'user':
        return html.Div([
            html.P('Sign in to view your friends list and see who is online.',
                   style={'fontSize': '11px', 'color': '#78847e', 'margin': '10px 4px', 'lineHeight': '1.4'}),
        ])
    if not friends:
        return html.Div([
            html.P('No friends added yet. Click on any player in the match feed or leaderboard to view their profile and add them!',
                   style={'fontSize': '11px', 'color': '#78847e', 'margin': '10px 4px', 'lineHeight': '1.4'}),
        ])
    items = []
    for f in friends:
        online = f.get('is_online', False)
        dot_class = 'online' if online else 'offline'
        disp = f.get('display_name') or f['username']
        items.append(html.Div([
            html.Div([
                html.Span(className=f'status-dot {dot_class}', title='Online' if online else 'Offline'),
                html.Span(f.get('avatar', 'A'), className='friends-avatar'),
                html.Div([
                    html.Strong(disp, className='friends-item-name'),
                    html.Small(f'{f.get("rank", "Wordsmith")} · {f.get("rating", 1000)} pts', className='friends-item-sub'),
                ], className='friends-item-info'),
            ], className='friends-item-left'),
            html.Div([
                html.Button('Profile', type='button', className='friends-action-btn',
                            **{'data-view-profile': f['username']}, title=f"View @{f['username']}'s profile"),
                html.Button('✕', type='button', className='friends-action-btn',
                            **{'data-toggle-friend': f['username']}, title=f"Remove @{f['username']} from friends",
                            style={'color': '#9e9e9e', 'padding': '3px 6px'}),
            ], className='friends-item-actions'),
        ], className='friends-item'))
    return html.Div(items, className='friends-list-body')


def render_active_games(saved_games, active_id):
    if not saved_games:
        return html.Div([
            html.Span('No active games saved yet.', className='empty-title',
                      style={'display': 'block', 'fontWeight': '600', 'fontSize': '12px', 'marginBottom': '4px'}),
            html.P('Start or join a game to switch between multiple games here.',
                   style={'margin': '0', 'fontSize': '11px', 'color': '#7a827e'}),
        ], className='history-empty', style={'minHeight': '70px', 'textAlign': 'center', 'padding': '14px'})

    rows = []
    for item in saved_games:
        gid = item.get('id', '')
        is_current = (gid == active_id)
        turns_count = item.get('turns_count', 0)
        turn_str = f"{turns_count} {'turn' if turns_count == 1 else 'turns'}"
        is_ended = item.get('finished', False)

        if item.get('mode') == 'multiplayer':
            title = f"Room {item.get('code', '')}"
            if is_ended:
                sub = f"Completed · {turn_str}"
            elif not item.get('connected'):
                sub = f"Waiting for opponent · {turn_str}"
            else:
                sub = f"{'Your turn' if item.get('my_turn') else 'Opponent turn'} · {turn_str}"
        else:
            mode_label = 'Vs computer' if item.get('mode') == 'computer' else 'Two players'
            title = f"{mode_label} · #{item.get('local_id', gid[-4:])}"
            sub = f"{'Completed' if is_ended else 'In progress'} · {turn_str}"

        action_el = (
            html.Span('Active', style={
                'fontSize': '10px', 'fontWeight': '650', 'padding': '5px 9px',
                'borderRadius': '5px', 'background': '#e8eee2', 'color': '#52674a',
            })
            if is_current else
            html.Button('Resume →', type='button', className='button secondary',
                        style={'padding': '5px 10px', 'fontSize': '10px', 'flex': '0'},
                        **{'data-resume-game': gid})
        )
        rows.append(html.Div([
            html.Div([
                html.Strong(title, style={'fontSize': '12px', 'display': 'block'}),
                html.Small(sub, style={'fontSize': '10px', 'color': '#7a827e'}),
            ], style={'flex': '1', 'minWidth': '0'}),
            action_el,
            html.Button('✕', type='button', title='Remove from list', className='button quiet',
                        style={'padding': '4px 7px', 'fontSize': '10px'},
                        **{'data-dismiss-game': gid}),
        ], style={
            'display': 'flex', 'alignItems': 'center', 'gap': '8px', 'padding': '9px 10px',
            'borderRadius': '6px', 'border': '1px solid #e7e8e2',
            'background': '#f0f3eb' if is_current else '#fafbf8', 'marginBottom': '6px',
        }))
    return html.Div(rows)


def render_leaderboard_content(entries, current_auth):
    current_user = (current_auth or {}).get('username', '').lower() if (current_auth or {}).get('role') == 'user' else None
    if current_auth and current_auth.get('role') == 'user':
        w, l, d = current_auth.get('wins', 0), current_auth.get('losses', 0), current_auth.get('draws', 0)
        total = w + l + d
        win_rate = f'{(w / total * 100):.0f}%' if total else '0%'
        avatar_sym = current_auth.get('avatar', 'A')
        display_name = current_auth.get('display_name') or current_auth['username']
        standing_banner = html.Div([
            html.Span(avatar_sym, className='player-avatar', style={'fontSize': '18px', 'fontWeight': '700', 'padding': '10px 14px'}),
            html.Div([
                html.Span('YOUR STANDING', className='field-label', style={'marginBottom': '4px'}),
                html.Strong(display_name, style={'fontSize': '18px'}),
                html.Span(current_auth.get('rank', 'Novice Wordsmith'),
                          style={'marginLeft': '10px', 'fontSize': '11px', 'fontWeight': '650', 'padding': '4px 9px',
                                 'borderRadius': '5px', 'background': '#e8eee2', 'color': '#52674a'}),
            ]),
            html.Div([
                html.Div([html.Small('RATING', className='muted'), html.Strong(str(current_auth.get('rating', 1000)), style={'fontSize': '16px'})],
                         style={'display': 'flex', 'flexDirection': 'column', 'alignItems': 'center'}),
                html.Div([html.Small('RECORD (W-L-D)', className='muted'), html.Strong(f'{w} - {l} - {d}', style={'fontSize': '16px'})],
                         style={'display': 'flex', 'flexDirection': 'column', 'alignItems': 'center'}),
                html.Div([html.Small('WIN RATE', className='muted'), html.Strong(win_rate, style={'fontSize': '16px'})],
                         style={'display': 'flex', 'flexDirection': 'column', 'alignItems': 'center'}),
                html.Div([html.Small('HIGH SCORE', className='muted'), html.Strong(str(current_auth.get('high_score', 0)), style={'fontSize': '16px'})],
                         style={'display': 'flex', 'flexDirection': 'column', 'alignItems': 'center'}),
            ], style={'display': 'flex', 'gap': '24px', 'marginLeft': 'auto'}),
        ], className='panel', style={'display': 'flex', 'alignItems': 'center', 'flexWrap': 'wrap', 'gap': '16px', 'marginBottom': '18px', 'background': '#f9f8f4'})
    else:
        standing_banner = html.Div([
            html.Strong('Playing as Guest'),
            html.Span(' — Register or log in to record your wins, losses, rating, rank, and high score on the global leaderboard.',
                      style={'color': '#7a827e', 'fontSize': '12px', 'marginLeft': '6px'}),
        ], className='panel', style={'marginBottom': '18px', 'padding': '16px 20px', 'background': '#f9f8f4'})

    if not entries:
        table = html.Div([
            html.Span('No ranked players yet.', className='empty-title'),
            html.P('Register an account and complete a game to claim the #1 spot on the leaderboard.'),
        ], className='history-empty', style={'minHeight': '140px'})
    else:
        grid_cols = '40px 1.4fr 1.1fr 75px 95px 65px 75px 1.5fr'
        header = html.Div([
            html.Span('#'), html.Span('PLAYER'), html.Span('RANK'), html.Span('RATING'),
            html.Span('W / L / D'), html.Span('WIN %'), html.Span('HIGH'), html.Span('LINKED ACCOUNTS'),
        ], style={'display': 'grid', 'gridTemplateColumns': grid_cols, 'gap': '8px',
                  'fontSize': '10px', 'fontWeight': '650', 'letterSpacing': '1px', 'color': '#7a827e',
                  'padding': '10px 14px', 'borderBottom': '1px solid #e7e8e2'})
        rows = []
        for entry in entries:
            w, l, d = entry['wins'], entry['losses'], entry['draws']
            total = entry['games']
            win_pct = f'{(w / total * 100):.0f}%' if total else '—'
            is_me = current_user and entry['username'].lower() == current_user
            disp = entry.get('display_name') or entry['username']

            badges = []
            if entry.get('woogles_username'):
                badges.append(html.Span(f"Woogles ({entry['woogles_username']}): {entry.get('woogles_rating', 1200)}",
                                        style={'fontSize': '9.5px', 'padding': '2px 6px', 'borderRadius': '4px',
                                               'background': '#eef2eb', 'color': '#3f5238', 'fontWeight': '600'}))
            if entry.get('isc_username'):
                badges.append(html.Span(f"ISC ({entry['isc_username']}): {entry.get('isc_rating', 1200)}",
                                        style={'fontSize': '9.5px', 'padding': '2px 6px', 'borderRadius': '4px',
                                               'background': '#f4efe6', 'color': '#6e5233', 'fontWeight': '600'}))

            row = html.Div([
                html.Span(f"#{entry['rank_num']}", style={'fontWeight': '700', 'color': '#44514a'}),
                html.Div([
                    html.Span(entry.get('avatar', 'A'), className='feed-avatar', style={'width': '20px', 'height': '20px', 'fontSize': '11px'}),
                    html.Button(disp, type='button', className='feed-player-btn',
                                **{'data-view-profile': entry['username']}),
                ], style={'display': 'flex', 'alignItems': 'center', 'gap': '6px'}),
                html.Span(entry.get('rank', 'Novice'), style={'fontSize': '11px', 'color': '#5a6660'}),
                html.Strong(str(entry['rating']), style={'fontSize': '12px'}),
                html.Span(f"{w} - {l} - {d}", style={'fontSize': '11px', 'color': '#68766c'}),
                html.Span(win_pct, style={'fontSize': '11px', 'color': '#68766c'}),
                html.Span(str(entry.get('high_score', 0)), style={'fontSize': '11px', 'fontWeight': '600'}),
                html.Div(badges or [html.Span('—', style={'color': '#a0a6a2'})], style={'display': 'flex', 'gap': '4px', 'flexWrap': 'wrap'}),
            ], style={'display': 'grid', 'gridTemplateColumns': grid_cols, 'gap': '8px', 'alignItems': 'center',
                      'padding': '9px 14px', 'borderBottom': '1px solid #f0f2ed',
                      'background': '#f0f3eb' if is_me else '#fff'})
            rows.append(row)
        table = html.Div([header, *rows], className='panel', style={'padding': '0', 'overflowX': 'auto'})

    return html.Div([standing_banner, table])


def render_profile_content(user_data, current_auth, is_friend=False):
    if not user_data:
        return html.Div('User not found.', className='panel', style={'padding': '24px'})

    disp = user_data.get('display_name') or user_data['username']
    w, l, d = user_data.get('wins', 0), user_data.get('losses', 0), user_data.get('draws', 0)
    total = user_data.get('games', 0)
    win_rate = f'{(w / total * 100):.0f}%' if total else '0%'
    is_me = current_auth and current_auth.get('username') == user_data['username']

    friend_action = None
    if current_auth and current_auth.get('role') == 'user' and not is_me:
        friend_action = html.Button(
            'Remove Friend' if is_friend else '+ Add Friend',
            type='button',
            className='button quiet' if is_friend else 'button primary',
            **{'data-toggle-friend': user_data['username']},
            style={'padding': '7px 14px', 'fontSize': '11px'}
        )

    stats = html.Div([
        html.Div([html.Small('RATING', className='muted'), html.Strong(str(user_data.get('rating', 1000)), style={'fontSize': '16px'})],
                 style={'display': 'flex', 'flexDirection': 'column', 'alignItems': 'center'}),
        html.Div([html.Small('RECORD (W-L-D)', className='muted'), html.Strong(f'{w} - {l} - {d}', style={'fontSize': '16px'})],
                 style={'display': 'flex', 'flexDirection': 'column', 'alignItems': 'center'}),
        html.Div([html.Small('WIN RATE', className='muted'), html.Strong(win_rate, style={'fontSize': '16px'})],
                 style={'display': 'flex', 'flexDirection': 'column', 'alignItems': 'center'}),
        html.Div([html.Small('HIGH SCORE', className='muted'), html.Strong(str(user_data.get('high_score', 0)), style={'fontSize': '16px'})],
                 style={'display': 'flex', 'flexDirection': 'column', 'alignItems': 'center'}),
        html.Div([html.Small('TOTAL GAMES', className='muted'), html.Strong(str(total), style={'fontSize': '16px'})],
                 style={'display': 'flex', 'flexDirection': 'column', 'alignItems': 'center'}),
    ], style={'display': 'flex', 'gap': '28px', 'flexWrap': 'wrap', 'marginTop': '12px'})

    return disp, user_data.get('rank', 'Novice Wordsmith'), friend_action, stats


def render_about_content(subtab='tech'):
    subtab = subtab or 'tech'
    if subtab == 'tech':
        return html.Div([
            html.Div([
                html.Div([
                    html.Div('RM', className='author-avatar'),
                    html.Div([
                        html.H3('Robert McMenemy'),
                        html.P('Senior AI & Data Solutions Architect · Full-Stack Python Specialist'),
                    ], className='author-details'),
                ], className='author-profile'),
                html.Div([
                    html.A('💼 LinkedIn', href='https://www.linkedin.com/in/robert-mcmenemy-%F0%9F%91%BE-70a0709b/',
                           target='_blank', rel='noopener noreferrer', className='author-btn'),
                    html.A('🐙 GitHub', href='https://github.com/arkay92',
                           target='_blank', rel='noopener noreferrer', className='author-btn'),
                    html.A('✍️ Medium', href='https://medium.com/@rabmcmenemy',
                           target='_blank', rel='noopener noreferrer', className='author-btn'),
                ], className='author-links-row'),
            ], className='author-banner'),

            html.Div([
                html.P('PROJECT ARCHITECTURE & ENGINEERING WRITEUP', className='eyebrow'),
                html.H2('How Letterroom Was Built & What It Can Do', style={'fontSize': '20px', 'marginBottom': '10px'}),
                html.P(
                    'Letterroom was built to demonstrate the full capabilities of Plotly Dash in production. '
                    'Far beyond static charts or analytical dashboards, it showcases a fully server-authoritative, '
                    'reactive word strategy game combining real-time bidirectional WebSockets, '
                    'touch/drag-and-drop gestures, durable cloud network filesystems, and machine-learned probabilistic circuits.',
                    style={'color': '#5a6662', 'fontSize': '13px', 'lineHeight': '1.7', 'margin': '0'},
                ),
            ], className='panel', style={'margin': '20px 0'}),

            html.Div([
                html.Div([
                    html.Div([
                        html.Span('NETWORKING', className='feature-tag'),
                        html.Span('LOW LATENCY', style={'fontSize': '10px', 'color': '#7a827e', 'fontWeight': '600'}),
                    ], className='feature-card-header'),
                    html.H3('Real-Time Duplex WebSocket Multiplayer', className='feature-title'),
                    html.P(
                        'Persistent RFC 6455 WebSocket transport (/ws) with client-side pushes via window.dash_clientside.set_props. '
                        'Features private tile rack obfuscation (ensuring opponent rack secrecy on the server before network serialization), '
                        '6-character room codes, public game hosting lobby, and seamless HTTP long-polling fallback.',
                        className='feature-desc',
                    ),
                ], className='feature-card'),

                html.Div([
                    html.Div([
                        html.Span('INFRASTRUCTURE', className='feature-tag'),
                        html.Span('PLOTLY CLOUD', style={'fontSize': '10px', 'color': '#7a827e', 'fontWeight': '600'}),
                    ], className='feature-card-header'),
                    html.H3("Persistent Cloud Storage ('Games')", className='feature-title'),
                    html.P(
                        "Directly integrates with Plotly Cloud's persistent storage mount (/Games). Multi-worker Gunicorn "
                        'processes share durable SQLite databases configured with PRAGMA journal_mode=WAL and busy_timeout=10000. '
                        'Active multiplayer rooms, user accounts, and leaderboards survive container restarts and redeployments.',
                        className='feature-desc',
                    ),
                ], className='feature-card'),

                html.Div([
                    html.Div([
                        html.Span('AI & ML', className='feature-tag'),
                        html.Span('PROBABILISTIC CIRCUITS', style={'fontSize': '10px', 'color': '#7a827e', 'fontWeight': '600'}),
                    ], className='feature-card-header'),
                    html.H3('Neural Probabilistic Circuit (NPC) AI', className='feature-title'),
                    html.P(
                        'Adapts conditional expert routing to Scrabble. Specialist categorical sum-product circuits learn '
                        'rack vowel/consonant balance, high-value tile preservation (Q, Z, X), board expansion mobility, and defence. '
                        'A gradient-trained neural gating layer combines expert posteriors based on turn phase and bag depth.',
                        className='feature-desc',
                    ),
                ], className='feature-card'),

                html.Div([
                    html.Div([
                        html.Span('ECOSYSTEM', className='feature-tag'),
                        html.Span('REST & PERSISTENCE', style={'fontSize': '10px', 'color': '#7a827e', 'fontWeight': '600'}),
                    ], className='feature-card-header'),
                    html.H3('Multi-Game Tracking & Live Profile Sync', className='feature-title'),
                    html.P(
                        'Track and resume in-progress matches across local, AI, and multiplayer modes. Includes PBKDF2 '
                        'account authentication, custom avatar letter tiles, live Leaderboard rankings, and external profile '
                        'linking with stats syncing from Woogles and Internet Scrabble Club (ISC).',
                        className='feature-desc',
                    ),
                ], className='feature-card'),
            ], className='tech-cards-grid'),
        ])

    return html.Div([
        html.Div([
            html.P('DASH ENTERPRISE & PLOTLY CLOUD', className='eyebrow'),
            html.H2('Why Plotly: A Production Platform IT Can Govern', style={'fontSize': '22px', 'marginBottom': '12px'}),
            html.P(
                'Dash Enterprise is the secure production platform for organizations scaling data apps and AI workflows. '
                'Domain experts get one consistent way to deploy and run Python apps. '
                'IT keeps full control over who can access them, what they can reach, and the infrastructure resources they use.',
                style={'color': '#5a6662', 'fontSize': '13px', 'lineHeight': '1.7', 'margin': '0'},
            ),
        ], className='panel'),

        html.Div([
            html.Span('🛡️ SOC 2 Type II', className='compliance-pill'),
            html.Span('🔒 ISO 27001', className='compliance-pill'),
            html.Span('📋 ISO 27701', className='compliance-pill'),
            html.Span('🤖 ISO 42001', className='compliance-pill'),
            html.Span('☁️ Runs in your cloud or air-gapped', className='compliance-pill'),
            html.Span('🔑 SSO: Entra ID · Okta · SAML · OIDC · LDAP', className='compliance-pill'),
        ], className='compliance-bar'),

        html.Div([
            html.H3('The Questions IT, Security and Risk Will Ask, Answered', style={'fontSize': '16px', 'margin': '0 0 6px'}),
            html.P('Every point below is a platform capability, so each new app inherits it without extra code.',
                   style={'color': '#7a827e', 'fontSize': '12px', 'margin': '0 0 16px'}),
            html.Div([
                html.Div([
                    html.Div('IDENTITY & ACCESS', className='qa-topic'),
                    html.H4('Who can sign in, and who sees what?', className='qa-q'),
                    html.Div([
                        html.Ul([
                            html.Li('Single sign-on through your IdP: Entra ID, Okta, Ping, SAML 2.0, OIDC or LDAP/Active Directory.'),
                            html.Li('Three roles: everyone is a viewer, licensed users build and deploy, admins run the platform.'),
                            html.Li('New apps start Restricted. Platform checks access before a request reaches the app.'),
                        ]),
                    ], className='qa-a'),
                ], className='qa-card'),

                html.Div([
                    html.Div('INFRASTRUCTURE & DATA', className='qa-topic'),
                    html.H4('Where does it run, and does our data leave?', className='qa-q'),
                    html.Div([
                        html.Ul([
                            html.Li('One Helm install into a single namespace of your existing EKS, AKS or GKE cluster.'),
                            html.Li('Apps, users and data stay in your network, with fully air-gapped installs supported.'),
                            html.Li('Apps reach databases and buckets through Kubernetes workload identity, without hardcoded credentials.'),
                        ]),
                    ], className='qa-a'),
                ], className='qa-card'),

                html.Div([
                    html.Div('APPLICATION SECURITY', className='qa-topic'),
                    html.H4('Is the code and runtime hardened?', className='qa-q'),
                    html.Div([
                        html.Ul([
                            html.Li('App images in your private container registry; app code in your GitHub organisation.'),
                            html.Li('Read-only filesystems, seccomp profiles, and no sudo or privilege escalation.'),
                            html.Li('Independent penetration testing with summaries available via trust.plotly.com.'),
                        ]),
                    ], className='qa-a'),
                ], className='qa-card'),

                html.Div([
                    html.Div('CONTINUITY', className='qa-topic'),
                    html.H4('What happens when something breaks?', className='qa-q'),
                    html.Div([
                        html.Ul([
                            html.Li('Scheduled and on-demand backups to your own S3, Azure Blob or GCS bucket.'),
                            html.Li('Backups include SSO settings, users and groups; apps redeploy automatically after a restore.'),
                            html.Li('Backup, restore and app operations run as durable workflows that resume after a node failure.'),
                        ]),
                    ], className='qa-a'),
                ], className='qa-card'),
            ], className='qa-grid'),
        ], className='panel', style={'marginTop': '20px'}),
    ])


def configure_app(app):
    app.title = 'Letterroom · A word worth playing'

    app.layout = html.Main([
        dcc.Location(id='url'),
        dcc.Store(id='session', storage_type='session'),
        dcc.Store(id='action'),
        dcc.Store(id='auth-store', storage_type='local'),
        dcc.Store(id='saved-games-store', storage_type='local'),
        dcc.Store(id='active-screen', data='home'),
        dcc.Store(id='viewed-profile', data=None),
        dcc.Store(id='about-subtab', data='tech'),
        dcc.Store(id='mp-tab', data='lobby'),
        dcc.Interval(id='mp-poll', interval=2500, disabled=False),

        # Header
        html.Header([
            html.Button([
                html.Span(['L', html.Sub('1')], className='brand-tile'),
                html.Span(['letter', html.Strong('room')])
            ], id='brand-home-btn', n_clicks=0, type='button', className='brand', title='Return to home'),
            html.Span('A word worth playing.', className='brand-note'),
            html.Button([
                html.Span(className='burger-bar'),
                html.Span(className='burger-bar'),
                html.Span(className='burger-bar'),
            ], id='burger-menu-btn', type='button', className='burger-menu-btn',
               **{'aria-label': 'Toggle navigation menu', 'aria-expanded': 'false'}),
            html.Div([
                html.Button('🏠 Home', id='nav-play-btn', n_clicks=0, type='button',
                            className='button quiet', style={'display': 'none', 'padding': '6px 10px', 'fontSize': '11px'}),
                html.Button('🏆 Leaderboard', id='nav-leaderboard-btn', n_clicks=0, type='button',
                            className='button secondary', style={'display': 'none', 'padding': '6px 10px', 'fontSize': '11px'}),
                html.Button('⚡ Why Plotly & About', id='nav-about-btn', n_clicks=0, type='button',
                            className='button quiet', style={'padding': '6px 11px', 'fontSize': '11px'}),
                html.Details([
                    html.Summary([
                        html.Span('A', id='header-avatar', className='user-avatar-badge'),
                        html.Span('Guest', id='user-badge', style={'fontWeight': '600', 'fontSize': '12px', 'color': '#26312f'}),
                        html.Span('▾', style={'fontSize': '10px', 'color': '#7a827e'}),
                    ], id='user-avatar-trigger', className='user-avatar-btn'),
                    html.Div([
                        html.Button('👤  My Profile', id='nav-profile-btn', n_clicks=0, type='button', className='button quiet'),
                        html.Button('⚡  Why Plotly & About', id='menu-about-btn', n_clicks=0, type='button', className='button quiet'),
                        html.Button('↪  Switch account', id='auth-logout-btn', n_clicks=0, type='button', className='button quiet',
                                    style={'color': '#c56a49'}),
                    ], className='user-dropdown-menu'),
                ], id='user-menu', className='user-dropdown', style={'display': 'none'}),
            ], id='site-nav', className='site-nav'),
        ], className='site-header'),

        # Auth Screen
        html.Section([
            html.Div([
                html.P('WELCOME TO LETTERROOM', className='eyebrow'),
                html.H1('Make your word count.', style={'fontSize': '28px', 'marginBottom': '8px'}),
                html.P('Log in to your account, register a new profile, or play right away as a guest.',
                       style={'color': '#7a827e', 'fontSize': '13px', 'margin': '0 0 22px', 'lineHeight': '1.5'}),
                html.Label('USERNAME', htmlFor='auth-username', className='field-label'),
                dcc.Input(id='auth-username', type='text', value='', placeholder='Enter username',
                          autoComplete='username', n_submit=0,
                          style={'width': '100%', 'padding': '10px 12px', 'border': '1px solid #e7e8e2',
                                 'borderRadius': '6px', 'fontSize': '13px', 'marginBottom': '14px', 'background': '#fafbf8'}),
                html.Label('PASSWORD', htmlFor='auth-password', className='field-label'),
                dcc.Input(id='auth-password', type='password', value='', placeholder='Enter password',
                          autoComplete='current-password', n_submit=0,
                          style={'width': '100%', 'padding': '10px 12px', 'border': '1px solid #e7e8e2',
                                 'borderRadius': '6px', 'fontSize': '13px', 'marginBottom': '16px', 'background': '#fafbf8'}),
                html.Div([
                    html.Button('Login', id='auth-login-btn', n_clicks=0, type='button',
                                className='button primary', style={'flex': '1', 'padding': '11px 14px'}),
                    html.Button('Register', id='auth-register-btn', n_clicks=0, type='button',
                                className='button secondary', style={'flex': '1', 'padding': '11px 14px'}),
                ], style={'display': 'flex', 'gap': '10px'}),
                html.Div('Enter your details or continue as guest.', id='auth-feedback', role='status',
                         style={'color': '#c56a49', 'fontSize': '11px', 'minHeight': '20px', 'margin': '12px 0'}),
                html.Div([
                    html.Span(style={'flex': '1', 'height': '1px', 'background': '#e7e8e2'}),
                    html.Span('OR', style={'fontSize': '9px', 'letterSpacing': '1.2px', 'color': '#7a827e', 'fontWeight': '650'}),
                    html.Span(style={'flex': '1', 'height': '1px', 'background': '#e7e8e2'}),
                ], style={'display': 'flex', 'alignItems': 'center', 'gap': '12px', 'margin': '6px 0 14px'}),
                html.Button('Play as guest →', id='auth-guest-btn', n_clicks=0, type='button',
                            className='button quiet', style={'width': '100%', 'padding': '11px 14px', 'fontSize': '12px'}),
            ], className='panel auth-card', style={'maxWidth': '420px', 'width': '100%', 'margin': '48px auto', 'padding': '30px'}),
        ], id='auth-screen', style={'display': 'none'}),

        # Profile Screen
        html.Section([
            html.Div([
                html.Div([
                    html.P('ACCOUNT & STATS', className='eyebrow'),
                    html.H1('Player Profile'),
                ]),
                html.Button('← Back to board', id='profile-back-btn', n_clicks=0, type='button',
                            className='button primary', style={'padding': '10px 16px'}),
            ], className='page-intro'),
            html.Div('', id='profile-feedback', role='status',
                     style={'fontSize': '12px', 'fontWeight': '600', 'color': '#52674a', 'minHeight': '22px', 'marginBottom': '12px'}),
            html.Div([
                html.Div([
                    html.Div([
                        html.Span('A', id='profile-avatar-preview', className='player-avatar',
                                  style={'fontSize': '20px', 'fontWeight': '700', 'padding': '12px 16px'}),
                        html.Div([
                            html.Strong('Player', id='profile-header-name', style={'fontSize': '18px', 'display': 'block'}),
                            html.Small('Novice Wordsmith · 1000 pts', id='profile-header-sub', style={'color': '#7a827e', 'fontSize': '12px'}),
                        ]),
                        html.Div(id='profile-friend-action-container', style={'marginLeft': 'auto'}),
                    ], style={'display': 'flex', 'alignItems': 'center', 'gap': '14px', 'marginBottom': '16px'}),
                    html.Div(id='profile-public-stats-container', style={'marginBottom': '16px'}),
                ], className='panel', style={'marginBottom': '18px'}),

                html.Div([
                    html.Div([
                        html.Div([
                            html.Label('DISPLAY NAME', htmlFor='profile-display-name', className='field-label'),
                            dcc.Input(id='profile-display-name', type='text', value='', placeholder='Display name',
                                      style={'width': '100%', 'padding': '9px 11px', 'border': '1px solid #e7e8e2',
                                             'borderRadius': '6px', 'fontSize': '13px', 'marginBottom': '14px', 'background': '#fafbf8'}),
                            html.Label('CHOOSE AVATAR TILE', htmlFor='profile-avatar-select', className='field-label'),
                            dcc.Dropdown(id='profile-avatar-select', options=AVATAR_OPTIONS, value='A',
                                         clearable=False, searchable=False, style={'marginBottom': '16px'}),
                            html.Button('Save profile changes', id='profile-save-btn', n_clicks=0, type='button',
                                        className='button primary', style={'width': '100%'}),
                        ], className='panel', style={'marginBottom': '18px'}),

                        html.Div([
                            html.H2('Change password', style={'marginBottom': '16px'}),
                            html.Label('CURRENT PASSWORD', htmlFor='profile-current-password', className='field-label'),
                            dcc.Input(id='profile-current-password', type='password', value='', placeholder='Current password',
                                      style={'width': '100%', 'padding': '9px 11px', 'border': '1px solid #e7e8e2',
                                             'borderRadius': '6px', 'fontSize': '13px', 'marginBottom': '12px', 'background': '#fafbf8'}),
                            html.Label('NEW PASSWORD', htmlFor='profile-new-password', className='field-label'),
                            dcc.Input(id='profile-new-password', type='password', value='', placeholder='New password (4+ chars)',
                                      style={'width': '100%', 'padding': '9px 11px', 'border': '1px solid #e7e8e2',
                                             'borderRadius': '6px', 'fontSize': '13px', 'marginBottom': '16px', 'background': '#fafbf8'}),
                            html.Button('Update password', id='profile-password-btn', n_clicks=0, type='button',
                                        className='button secondary', style={'width': '100%'}),
                        ], className='panel'),
                    ]),

                    html.Div([
                        html.Div([
                            html.Div([html.H2('Link Woogles Account'), html.Span('STAT SYNC', className='small-badge')], className='card-heading'),
                            html.P('Connect your Woogles handle to sync your tournament stats to your profile and the leaderboard.',
                                   style={'color': '#7a827e', 'fontSize': '12px', 'margin': '0 0 12px'}),
                            html.Label('WOOGLES USERNAME', htmlFor='profile-woogles-input', className='field-label'),
                            html.Div([
                                dcc.Input(id='profile-woogles-input', type='text', value='', placeholder='e.g. WordMaster',
                                          style={'flex': '1', 'minWidth': '0', 'padding': '9px 11px', 'border': '1px solid #e7e8e2',
                                                 'borderRadius': '6px', 'fontSize': '13px', 'background': '#fafbf8'}),
                                html.Button('Link Woogles', id='profile-woogles-btn', n_clicks=0, type='button', className='button primary'),
                            ], style={'display': 'flex', 'gap': '8px'}),
                            html.Div(id='profile-woogles-status'),
                        ], className='panel', style={'marginBottom': '18px'}),

                        html.Div([
                            html.Div([html.H2('Link ISC Account'), html.Span('STAT SYNC', className='small-badge')], className='card-heading'),
                            html.P('Connect your Internet Scrabble Club handle to display your ISC rating.',
                                   style={'color': '#7a827e', 'fontSize': '12px', 'margin': '0 0 12px'}),
                            html.Label('ISC USERNAME', htmlFor='profile-isc-input', className='field-label'),
                            html.Div([
                                dcc.Input(id='profile-isc-input', type='text', value='', placeholder='e.g. ISCPlayer',
                                          style={'flex': '1', 'minWidth': '0', 'padding': '9px 11px', 'border': '1px solid #e7e8e2',
                                                 'borderRadius': '6px', 'fontSize': '13px', 'background': '#fafbf8'}),
                                html.Button('Link ISC', id='profile-isc-btn', n_clicks=0, type='button', className='button primary'),
                            ], style={'display': 'flex', 'gap': '8px'}),
                            html.Div(id='profile-isc-status'),
                        ], className='panel'),
                    ]),
                ], id='profile-settings-section', style={'display': 'grid', 'gridTemplateColumns': 'repeat(auto-fit, minmax(320px, 1fr))', 'gap': '24px'}),
            ]),
        ], id='profile-screen', style={'display': 'none', 'minHeight': '65vh'}),

        # Leaderboard Screen
        html.Section([
            html.Div([
                html.Div([
                    html.P('RANKINGS & STANDINGS', className='eyebrow'),
                    html.H1('Word Leaderboard'),
                ]),
                html.Button('← Back to board', id='leaderboard-back-btn', n_clicks=0, type='button',
                            className='button primary', style={'padding': '10px 16px'}),
            ], className='page-intro'),
            html.Div(id='leaderboard-content'),
        ], id='leaderboard-screen', style={'display': 'none', 'minHeight': '65vh'}),

        # About Screen
        html.Section([
            html.Div([
                html.Div([
                    html.P('PRODUCTION DATA APPS · PLATFORM SHOWCASE', className='eyebrow'),
                    html.H1('Why Plotly & About This App'),
                ]),
                html.Button('← Return to game', id='about-back-btn', n_clicks=0, type='button',
                            className='button primary', style={'padding': '10px 18px'}),
            ], className='page-intro'),
            html.Div([
                html.Button('🔤  How Letterroom Was Built & Architecture', id='about-tab-tech-btn', n_clicks=0, type='button',
                            className='button primary', style={'padding': '10px 18px', 'borderRadius': '7px', 'fontSize': '12px', 'cursor': 'pointer'}),
                html.Button('⚡  Why Plotly: Deploy, Scale, Govern (IT Platform)', id='about-tab-why-btn', n_clicks=0, type='button',
                            className='button quiet', style={'padding': '10px 18px', 'borderRadius': '7px', 'fontSize': '12px', 'cursor': 'pointer'}),
            ], style={'display': 'flex', 'gap': '10px', 'marginBottom': '26px', 'flexWrap': 'wrap'}),
            html.Div(id='about-content'),
        ], id='about-screen', style={'display': 'none', 'minHeight': '65vh'}),

        # Home / Setup Screen
        html.Div([
            html.Section([
                html.P('SAME TABLE. DIFFERENT POSSIBILITIES.', className='eyebrow'),
                html.H1(['Good company.', html.Br(), 'Even better words.']),
                html.P('Make a little space for a classic. Build words, find the perfect square, and make every letter count.', className='setup-description'),
                html.Div([tile(letter) for letter in 'PLAY'], className='hero-tiles', **{'aria-hidden': 'true'}),
                html.Div([html.Span('15 × 15 board'), html.Span('100 tiles'), html.Span('Endless possibilities')], className='setup-facts'),

                # Active Games Drawer
                html.Section([
                    html.Div([
                        html.H2('In-progress games', style={'fontSize': '14px', 'fontWeight': '700', 'margin': '0'}),
                        html.Span('0 active', id='active-games-count', className='muted', style={'fontSize': '11px'}),
                    ], className='card-heading', style={'marginBottom': '10px', 'display': 'flex', 'justifyContent': 'space-between', 'alignItems': 'center'}),
                    html.Div(id='active-games-list'),
                ], className='panel active-games-panel', style={'marginTop': '24px'}),
            ], className='setup-intro'),

            html.Section([
                html.Div([html.H2('Make it your game'), html.Span('01 / SET UP', className='small-badge')], className='card-heading'),
                html.Label('PLAY MODE', className='field-label'),
                dcc.RadioItems(
                    id='mode',
                    options=[
                        {'label': 'Player vs computer', 'value': 'computer'},
                        {'label': 'Two players', 'value': 'pvp'},
                        {'label': 'Multiplayer', 'value': 'multiplayer'},
                    ],
                    value='computer', className='mode-options'
                ),

                # Multiplayer Lobby Sub-Panel
                html.Div([
                    html.Div([
                        html.Button('Host / Join', id='mp-tab-lobby-btn', n_clicks=0, type='button',
                                    className='button primary', style={'padding': '6px 12px', 'fontSize': '11px'}),
                        html.Button('Find a game', id='mp-tab-find-btn', n_clicks=0, type='button',
                                    className='button quiet', style={'padding': '6px 12px', 'fontSize': '11px'}),
                    ], id='mp-tabs-row', style={'display': 'flex', 'gap': '8px', 'margin': '12px 0 16px'}),

                    html.Div([
                        html.Div([
                            html.P('Host an open game for anyone to join, create a private room code, or join a friend’s game.',
                                   style={'fontSize': '11.5px', 'color': '#7a827e', 'margin': '0 0 12px', 'lineHeight': '1.4'}),
                            html.Div([
                                html.Button('Host game', id='mp-host-btn', n_clicks=0, type='button', className='button primary', style={'flex': '1'}),
                                html.Button('Create game', id='mp-create-btn', n_clicks=0, type='button', className='button secondary', style={'flex': '1'}),
                                html.Button('Join game', id='mp-choose-join-btn', n_clicks=0, type='button', className='button quiet', style={'flex': '1'}),
                            ], style={'display': 'flex', 'gap': '8px'}),
                        ], id='mp-view-choice'),

                        html.Div([
                            html.Label('ENTER ROOM CODE', htmlFor='join-code-input', className='field-label'),
                            html.Div([
                                dcc.Input(id='join-code-input', type='text', placeholder='6-letter code', maxLength=6,
                                          style={'flex': '1', 'minWidth': '0', 'textTransform': 'uppercase', 'letterSpacing': '2px',
                                                 'fontWeight': '700', 'padding': '9px 12px', 'border': '1px solid #e7e8e2', 'borderRadius': '6px'}),
                                html.Button('Join room →', id='mp-join-submit', n_clicks=0, type='button', className='button primary'),
                            ], style={'display': 'flex', 'gap': '8px', 'marginBottom': '8px'}),
                            html.Button('← Back to choices', id='mp-back-choice', n_clicks=0, type='button', className='button quiet', style={'fontSize': '11px'}),
                        ], id='mp-view-join', style={'display': 'none'}),

                        html.Div([
                            html.Div(id='mp-open-games-list'),
                        ], id='mp-view-find', style={'display': 'none'}),

                        html.Div(id='mp-view-room', style={'display': 'none', 'marginTop': '12px'}),
                        html.Div([
                            html.Button('Leave room', id='mp-leave-btn', n_clicks=0, type='button', className='button quiet',
                                        style={'fontSize': '11px', 'color': '#c56a49'}),
                        ], id='mp-leave-row', style={'display': 'none', 'marginTop': '8px'}),
                    ]),
                ], id='multiplayer-panel', style={'display': 'none'}),

                html.Label('CHOOSE YOUR DICTIONARY', className='field-label', style={'marginTop': '16px'}),
                dcc.RadioItems(
                    id='dictionary',
                    options=[{'label': html.Div([html.Span(key[-2:], className='region-code'),
                                                html.Span([html.Strong(label), html.Small(description)])]), 'value': key}
                             for key, (label, description) in DICTIONARIES.items()],
                    value='en_US', className='dictionary-options'
                ),
                html.P('Regional ESDB word lists for casual play.', className='dictionary-note'),

                html.Div([
                    html.Div([html.Label('PLAYER ONE', htmlFor='player-one', className='field-label'),
                              dcc.Input(id='player-one', value='Player 1', maxLength=24)]),
                    html.Div([html.Label('PLAYER TWO', htmlFor='player-two', className='field-label'),
                              dcc.Input(id='player-two', value='Player 2', maxLength=24)], id='second-player-field'),
                ], className='name-fields'),

                html.Button('Let’s play →', id='start', n_clicks=0, className='button primary full', disabled=False),
                html.Div('Ready when you are.', id='setup-feedback', className='setup-feedback', role='status'),
                html.Small('Two players: pass-and-play. Computer: NPC-powered replies. Multiplayer: private racks.', className='privacy-note'),
            ], className='panel setup-panel'),

            # Recent Multiplayer Matches Feed
            html.Section([
                html.Div([
                    html.H2('Recent Multiplayer Matches', style={'fontSize': '15px', 'fontWeight': '700', 'margin': '0'}),
                    html.Span('Live Community Feed · Click any player to view profile', className='muted', style={'fontSize': '11px'}),
                ], className='card-heading', style={'marginBottom': '10px', 'display': 'flex', 'justifyContent': 'space-between', 'alignItems': 'center'}),
                html.Div(render_recent_games([]), id='recent-games-feed'),
            ], className='panel recent-games-panel', id='recent-games-panel', style={'gridColumn': '1 / -1', 'marginTop': '20px'}),
        ], id='home-screen', className='setup-layout'),

        # Active Game View Container
        html.Div(id='game-view-container', style={'display': 'none'}),

        # Floating Friends Widget
        html.Div([
            html.Div([
                html.Div([
                    html.Span('👥  Friends', className='friends-box-title'),
                    html.Button('✕', id='friends-close-btn', type='button', className='friends-close-btn', title='Close'),
                ], className='friends-box-header'),
                html.Div(render_friends_widget_content([], None), id='friends-widget-content'),
            ], id='friends-widget', className='friends-box'),
            html.Button([
                html.Span('👥 Friends'),
                html.Span('0 online', id='friends-online-badge', className='friends-online-badge'),
            ], id='friends-toggle-btn', type='button', className='friends-toggle-btn', title='Toggle friends list'),
        ], className='friends-widget-container', id='friends-widget-container'),

        html.Div('Updating your game…', id='thinking', className='thinking', style={'display': 'none'}, role='status'),

        # Footer
        html.Footer([
            html.Span('Less distraction. More wordplay.'),
            html.Span([
                'Built with Python & Plotly Dash · ',
                html.Button('Why Plotly & Architecture ↗', id='footer-about-btn', n_clicks=0, type='button',
                            className='button quiet', style={'padding': '0', 'border': '0', 'background': 'none', 'color': 'inherit', 'textDecoration': 'underline', 'cursor': 'pointer'})
            ])
        ]),
    ], className='app-container')

    # Main Universal Coordinator Callback
    @app.callback(
        Output('session', 'data'),
        Output('saved-games-store', 'data'),
        Output('auth-store', 'data'),
        Output('url', 'search'),
        Output('active-screen', 'data'),
        Output('viewed-profile', 'data'),
        Output('about-subtab', 'data'),
        Output('mp-tab', 'data'),
        Output('mp-poll', 'disabled'),
        Output('user-badge', 'children'),
        Output('header-avatar', 'children'),
        Output('user-menu', 'style'),
        Output('nav-play-btn', 'style'),
        Output('nav-leaderboard-btn', 'style'),
        Output('auth-screen', 'style'),
        Output('auth-feedback', 'children'),
        Output('home-screen', 'style'),
        Output('game-view-container', 'style'),
        Output('game-view-container', 'children'),
        Output('leaderboard-screen', 'style'),
        Output('leaderboard-content', 'children'),
        Output('about-screen', 'style'),
        Output('about-content', 'children'),
        Output('about-tab-tech-btn', 'className'),
        Output('about-tab-why-btn', 'className'),
        Output('profile-screen', 'style'),
        Output('profile-feedback', 'children'),
        Output('profile-avatar-preview', 'children'),
        Output('profile-header-name', 'children'),
        Output('profile-header-sub', 'children'),
        Output('profile-friend-action-container', 'children'),
        Output('profile-public-stats-container', 'children'),
        Output('profile-settings-section', 'style'),
        Output('profile-display-name', 'value'),
        Output('profile-avatar-select', 'value'),
        Output('profile-woogles-status', 'children'),
        Output('profile-isc-status', 'children'),
        Output('active-games-count', 'children'),
        Output('active-games-list', 'children'),
        Output('recent-games-feed', 'children'),
        Output('friends-widget-content', 'children'),
        Output('friends-online-badge', 'children'),
        Output('multiplayer-panel', 'style'),
        Output('mp-view-choice', 'style'),
        Output('mp-view-join', 'style'),
        Output('mp-view-find', 'style'),
        Output('mp-open-games-list', 'children'),
        Output('mp-view-room', 'style'),
        Output('mp-view-room', 'children'),
        Output('mp-tab-lobby-btn', 'style'),
        Output('mp-tab-find-btn', 'style'),
        Output('start', 'disabled'),
        Output('setup-feedback', 'children'),
        Output('second-player-field', 'style'),

        Input('action', 'data'),
        Input('url', 'search'),
        Input('url', 'pathname'),
        Input('mp-poll', 'n_intervals'),
        Input('auth-login-btn', 'n_clicks'),
        Input('auth-register-btn', 'n_clicks'),
        Input('auth-guest-btn', 'n_clicks'),
        Input('auth-logout-btn', 'n_clicks'),
        Input('auth-username', 'n_submit'),
        Input('auth-password', 'n_submit'),
        Input('brand-home-btn', 'n_clicks'),
        Input('nav-play-btn', 'n_clicks'),
        Input('nav-leaderboard-btn', 'n_clicks'),
        Input('leaderboard-back-btn', 'n_clicks'),
        Input('nav-about-btn', 'n_clicks'),
        Input('footer-about-btn', 'n_clicks'),
        Input('menu-about-btn', 'n_clicks'),
        Input('about-back-btn', 'n_clicks'),
        Input('about-tab-tech-btn', 'n_clicks'),
        Input('about-tab-why-btn', 'n_clicks'),
        Input('nav-profile-btn', 'n_clicks'),
        Input('profile-back-btn', 'n_clicks'),
        Input('profile-save-btn', 'n_clicks'),
        Input('profile-password-btn', 'n_clicks'),
        Input('profile-woogles-btn', 'n_clicks'),
        Input('profile-isc-btn', 'n_clicks'),
        Input('start', 'n_clicks'),
        Input('mode', 'value'),
        Input('dictionary', 'value'),
        Input('mp-tab-lobby-btn', 'n_clicks'),
        Input('mp-tab-find-btn', 'n_clicks'),
        Input('mp-host-btn', 'n_clicks'),
        Input('mp-create-btn', 'n_clicks'),
        Input('mp-choose-join-btn', 'n_clicks'),
        Input('mp-join-submit', 'n_clicks'),
        Input('join-code-input', 'n_submit'),
        Input('mp-back-choice', 'n_clicks'),
        Input('mp-leave-btn', 'n_clicks'),

        State('session', 'data'),
        State('saved-games-store', 'data'),
        State('auth-store', 'data'),
        State('active-screen', 'data'),
        State('viewed-profile', 'data'),
        State('about-subtab', 'data'),
        State('mp-tab', 'data'),
        State('auth-username', 'value'),
        State('auth-password', 'value'),
        State('player-one', 'value'),
        State('player-two', 'value'),
        State('join-code-input', 'value'),
        State('profile-display-name', 'value'),
        State('profile-avatar-select', 'value'),
        State('profile-current-password', 'value'),
        State('profile-new-password', 'value'),
        State('profile-woogles-input', 'value'),
        State('profile-isc-input', 'value'),
    )
    def update(action, url_search, url_pathname, poll_ticks,
               login_clicks, register_clicks, guest_clicks, logout_clicks, user_submit, pass_submit,
               brand_clicks, nav_play_clicks, nav_lb_clicks, lb_back_clicks,
               nav_about_clicks, footer_about_clicks, menu_about_clicks, about_back_clicks,
               about_tech_clicks, about_why_clicks,
               nav_prof_clicks, prof_back_clicks, prof_save_clicks, prof_pw_clicks,
               prof_woogles_clicks, prof_isc_clicks,
               start_clicks, mode, dictionary,
               tab_lobby_clicks, tab_find_clicks,
               host_clicks, create_clicks, choose_join_clicks,
               join_submit_clicks, join_submit_enter, back_choice_clicks, mp_leave_clicks,
               state, saved_games, auth_store, active_screen, viewed_profile,
               about_subtab, mp_tab,
               auth_user, auth_pass,
               player_one, player_two, join_code,
               prof_display_name, prof_avatar, prof_curr_pw, prof_new_pw,
               prof_woogles_user, prof_isc_user):

        trigger = ctx.triggered_id
        action_data = action if trigger == 'action' else {}
        auth = dict(auth_store or {'role': 'guest', 'username': 'guest', 'display_name': 'Guest', 'avatar': 'A'})
        saved_games = list(saved_games or [])
        screen = active_screen or 'home'
        subtab = about_subtab or 'tech'
        lobby_tab = mp_tab or 'lobby'
        target_profile = viewed_profile
        url_search_out = no_update
        auth_msg = ''
        profile_msg = ''
        woogles_status = ''
        isc_status = ''
        mp_choice_mode = 'choice'
        game_message = 'Drag or click tiles to start building a word.'

        # Update last seen if registered user
        if auth.get('role') == 'user':
            try:
                DEFAULT_AUTH.update_last_seen(auth['username'])
            except Exception:
                pass

        # 1. URL Room Code Detection
        code_from_url = extract_code_from_url(url_search, url_pathname)

        # 2. Authentication Handling
        if trigger in ('auth-login-btn', 'auth-username', 'auth-password') and auth_user and auth_pass:
            try:
                user = DEFAULT_AUTH.login(auth_user, auth_pass)
                auth = {'role': 'user', **user}
                screen = 'home'
            except Exception as e:
                auth_msg = str(e)
        elif trigger == 'auth-register-btn' and auth_user and auth_pass:
            try:
                user = DEFAULT_AUTH.register(auth_user, auth_pass)
                auth = {'role': 'user', **user}
                screen = 'home'
            except Exception as e:
                auth_msg = str(e)
        elif trigger == 'auth-guest-btn':
            auth = {'role': 'guest', 'username': 'guest', 'display_name': 'Guest', 'avatar': 'A'}
            screen = 'home'
        elif trigger == 'auth-logout-btn':
            auth = {'role': 'guest', 'username': 'guest', 'display_name': 'Guest', 'avatar': 'A'}
            screen = 'auth'
            state = None

        # 3. Screen Navigation
        if trigger in ('brand-home-btn', 'nav-play-btn'):
            screen = 'home' if state is None else 'game'
        elif trigger in ('nav-leaderboard-btn', 'leaderboard-back-btn'):
            screen = 'home' if trigger == 'leaderboard-back-btn' else 'leaderboard'
        elif trigger in ('nav-about-btn', 'footer-about-btn', 'menu-about-btn', 'about-back-btn'):
            screen = 'home' if trigger == 'about-back-btn' else 'about'
        elif trigger == 'about-tab-tech-btn':
            subtab = 'tech'
        elif trigger == 'about-tab-why-btn':
            subtab = 'why'
        elif trigger in ('nav-profile-btn', 'profile-back-btn'):
            if trigger == 'profile-back-btn':
                screen = 'home' if state is None else 'game'
            else:
                screen = 'profile'
                target_profile = auth.get('username')

        # 4. Action Store Event Handlers (board, profiles, friends, resume/dismiss)
        if action_data:
            act_type = action_data.get('type')
            if act_type == 'view-profile':
                target_profile = action_data.get('username')
                screen = 'profile'
            elif act_type == 'toggle-friend' and auth.get('role') == 'user':
                f_user = action_data.get('username')
                if f_user:
                    try:
                        DEFAULT_AUTH.toggle_friend(auth['username'], f_user)
                    except Exception:
                        pass
            elif act_type == 'resume-game':
                gid = action_data.get('game_id', '')
                for g in saved_games:
                    if g.get('id') == gid:
                        state = g.get('state')
                        screen = 'game'
                        if g.get('mode') == 'multiplayer':
                            url_search_out = f"?code={g.get('code')}"
                        break
            elif act_type == 'dismiss-game':
                gid = action_data.get('game_id', '')
                saved_games = [g for g in saved_games if g.get('id') != gid]
                if state and (state.get('local_id') == gid or (state.get('mp') or {}).get('code') == gid[3:]):
                    state = None
                    screen = 'home'
            elif act_type == 'mp-join':
                join_c = action_data.get('code')
                if join_c:
                    try:
                        room, token = DEFAULT_HUB.join_room(
                            join_c,
                            joiner_user=auth.get('username') if auth.get('role') == 'user' else None,
                            joiner_name=auth.get('display_name') or 'Player 2',
                            joiner_avatar=auth.get('avatar', 'E')
                        )
                        state = DEFAULT_HUB.get_room_snapshot(join_c, token)['state']
                        state['mp'] = {'code': join_c, 'token': token, 'p_idx': 1, 'connected': True}
                        screen = 'game'
                        url_search_out = f"?code={join_c}"
                    except Exception as e:
                        game_message = str(e)
            elif act_type in ('home', 'leave-room'):
                state = None
                screen = 'home'
                url_search_out = ''
            elif act_type == 'restart' and state:
                if not state.get('mp'):
                    state = new_game(state.get('dictionary', 'en_US'), tuple(state.get('players', ('Player 1', 'Player 2'))), mode=state.get('mode', 'pvp'))
                    game_message = 'A fresh board and new tiles. Your move!'
            elif state:
                # Apply in-game board / rack actions
                try:
                    if state.get('mp'):
                        mp_info = state['mp']
                        c = mp_info.get('code')
                        tok = mp_info.get('token')
                        snap = DEFAULT_HUB.apply_action(c, tok, action_data, blank=action_data.get('blank', 'A'))
                        state = snap['state']
                        state['mp'] = {'code': c, 'token': tok, 'p_idx': snap.get('player_index'), 'connected': snap.get('connected')}
                    else:
                        if state.get('mode') == 'computer' and state['turn'] == 1 and act_type != 'retry':
                            raise ValueError('It is the computer’s turn.')
                        state, game_message = act(state, action_data, action_data.get('blank', 'A'))
                except Exception as e:
                    game_message = str(e)

        # 5. Profile Management
        if trigger == 'profile-save-btn' and auth.get('role') == 'user':
            try:
                DEFAULT_AUTH.update_profile(auth['username'], display_name=prof_display_name, avatar=prof_avatar)
                auth['display_name'] = prof_display_name or auth['username']
                auth['avatar'] = prof_avatar or 'A'
                profile_msg = 'Profile changes saved successfully!'
            except Exception as e:
                profile_msg = str(e)
        elif trigger == 'profile-password-btn' and auth.get('role') == 'user':
            try:
                DEFAULT_AUTH.change_password(auth['username'], prof_curr_pw, prof_new_pw)
                profile_msg = 'Password updated successfully!'
            except Exception as e:
                profile_msg = str(e)
        elif trigger == 'profile-woogles-btn' and auth.get('role') == 'user':
            try:
                DEFAULT_AUTH.link_woogles(auth['username'], prof_woogles_user)
                woogles_status = html.Span(f'Linked Woogles account @{prof_woogles_user}', style={'color': '#52674a', 'fontSize': '11px'})
            except Exception as e:
                woogles_status = html.Span(str(e), style={'color': '#c56a49', 'fontSize': '11px'})
        elif trigger == 'profile-isc-btn' and auth.get('role') == 'user':
            try:
                DEFAULT_AUTH.link_isc(auth['username'], prof_isc_user)
                isc_status = html.Span(f'Linked ISC account @{prof_isc_user}', style={'color': '#52674a', 'fontSize': '11px'})
            except Exception as e:
                isc_status = html.Span(str(e), style={'color': '#c56a49', 'fontSize': '11px'})

        # 6. Multiplayer Lobby Tab and Creation Actions
        if trigger == 'mp-tab-lobby-btn':
            lobby_tab = 'lobby'
        elif trigger == 'mp-tab-find-btn':
            lobby_tab = 'find'
        elif trigger == 'mp-choose-join-btn':
            mp_choice_mode = 'join'
        elif trigger == 'mp-back-choice':
            mp_choice_mode = 'choice'
        elif trigger == 'mp-host-btn':
            try:
                room, token = DEFAULT_HUB.create_room(
                    dictionary=dictionary or 'en_US',
                    host_user=auth.get('username') if auth.get('role') == 'user' else None,
                    host_name=auth.get('display_name') or 'Player 1',
                    host_avatar=auth.get('avatar', 'A'),
                    is_open=True
                )
                state = DEFAULT_HUB.get_room_snapshot(room['code'], token)['state']
                state['mp'] = {'code': room['code'], 'token': token, 'p_idx': 0, 'connected': False}
                screen = 'game'
                url_search_out = f"?code={room['code']}"
            except Exception as e:
                game_message = str(e)
        elif trigger == 'mp-create-btn':
            try:
                room, token = DEFAULT_HUB.create_room(
                    dictionary=dictionary or 'en_US',
                    host_user=auth.get('username') if auth.get('role') == 'user' else None,
                    host_name=auth.get('display_name') or 'Player 1',
                    host_avatar=auth.get('avatar', 'A'),
                    is_open=False
                )
                state = DEFAULT_HUB.get_room_snapshot(room['code'], token)['state']
                state['mp'] = {'code': room['code'], 'token': token, 'p_idx': 0, 'connected': False}
                screen = 'game'
                url_search_out = f"?code={room['code']}"
            except Exception as e:
                game_message = str(e)
        elif trigger in ('mp-join-submit', 'join-code-input') and join_code:
            try:
                c = join_code.strip().upper()
                room, token = DEFAULT_HUB.join_room(
                    c,
                    joiner_user=auth.get('username') if auth.get('role') == 'user' else None,
                    joiner_name=auth.get('display_name') or 'Player 2',
                    joiner_avatar=auth.get('avatar', 'E')
                )
                state = DEFAULT_HUB.get_room_snapshot(c, token)['state']
                state['mp'] = {'code': c, 'token': token, 'p_idx': 1, 'connected': True}
                screen = 'game'
                url_search_out = f"?code={c}"
            except Exception as e:
                game_message = str(e)
        elif trigger == 'mp-leave-btn':
            state = None
            screen = 'home'
            url_search_out = ''

        # 7. URL Joining
        if code_from_url and (state is None or (state.get('mp') or {}).get('code') != code_from_url):
            try:
                # Try getting room snapshot with existing token or join
                existing_g = next((g for g in saved_games if g.get('code') == code_from_url), None)
                if existing_g:
                    snap = DEFAULT_HUB.get_room_snapshot(code_from_url, existing_g.get('token'))
                    if snap:
                        state = snap['state']
                        state['mp'] = {'code': code_from_url, 'token': existing_g.get('token'), 'p_idx': snap.get('player_index'), 'connected': snap.get('connected')}
                        screen = 'game'
                else:
                    room, token = DEFAULT_HUB.join_room(
                        code_from_url,
                        joiner_user=auth.get('username') if auth.get('role') == 'user' else None,
                        joiner_name=auth.get('display_name') or 'Player 2',
                        joiner_avatar=auth.get('avatar', 'E')
                    )
                    state = DEFAULT_HUB.get_room_snapshot(code_from_url, token)['state']
                    state['mp'] = {'code': code_from_url, 'token': token, 'p_idx': 1, 'connected': True}
                    screen = 'game'
            except Exception:
                pass

        # 8. Start Local Game
        if trigger == 'start' and mode in ('pvp', 'computer'):
            try:
                if dictionary not in DICTIONARIES:
                    raise ValueError('Choose a dictionary before starting the game.')
                p1 = player_one or 'Player 1'
                p2 = 'Computer' if mode == 'computer' else (player_two or 'Player 2')
                state = new_game(dictionary, (p1, p2), mode=mode)

                local_id = secrets.token_hex(2).upper()
                state['local_id'] = local_id
                screen = 'game'
            except Exception as e:
                game_message = str(e)

        # 9. Computer Turn Execution
        if state and state.get('mode') == 'computer' and state['turn'] == 1 and not state.get('finished'):
            try:
                state, reply = ScrabbleAI().take_turn(state)
                game_message += ' ' + reply
            except Exception as e:
                game_message = str(e)

        # 10. Polling updates for Multiplayer & Friends
        if state and state.get('mp'):
            mp_info = state['mp']
            c = mp_info.get('code')
            tok = mp_info.get('token')
            if c:
                snap = DEFAULT_HUB.get_room_snapshot(c, tok)
                if snap:
                    state = snap['state']
                    state['mp'] = {'code': c, 'token': tok, 'p_idx': snap.get('player_index'), 'connected': snap.get('connected')}

        # 11. Sync Saved Games Store
        if state:
            if state.get('mp'):
                c = state['mp']['code']
                entry = {
                    'id': f'mp:{c}',
                    'mode': 'multiplayer',
                    'code': c,
                    'token': state['mp']['token'],
                    'p_idx': state['mp']['p_idx'],
                    'turns_count': len(state.get('history', [])),
                    'connected': state['mp']['connected'],
                    'my_turn': (state['mp']['p_idx'] == state['turn']),
                    'finished': state.get('finished', False),
                    'state': state
                }
            else:
                lid = state.get('local_id') or secrets.token_hex(2).upper()
                state['local_id'] = lid
                entry = {
                    'id': f"{state.get('mode')}:{lid}",
                    'mode': state.get('mode'),
                    'local_id': lid,
                    'turns_count': len(state.get('history', [])),
                    'finished': state.get('finished', False),
                    'state': state
                }
            # Upsert
            saved_games = [entry] + [g for g in saved_games if g.get('id') != entry['id']][:11]

        # 12. Render Dynamic Components
        current_active_id = (f"mp:{state['mp']['code']}" if state.get('mp') else f"{state.get('mode')}:{state.get('local_id')}") if state else None
        active_games_html = render_active_games(saved_games, current_active_id)
        active_games_count_str = f"{len(saved_games)} active"

        # Multiplayer Open Games List
        open_rooms = DEFAULT_HUB.list_open_rooms()
        if not open_rooms:
            open_games_html = html.Div('No open games right now. Click "Host game" to start one!',
                                       style={'fontSize': '11.5px', 'color': '#7a827e', 'padding': '12px', 'textAlign': 'center'})
        else:
            open_rows = []
            for r in open_rooms:
                open_rows.append(html.Div([
                    html.Div([
                        html.Strong(f"Room {r['code']} · {r['p1_name']}"),
                        html.Small(f"Dictionary: {r['dictionary'].upper()}", className='muted', style={'fontSize': '10px'}),
                    ], style={'flex': '1'}),
                    html.Button('Join game →', type='button', className='button primary',
                                style={'padding': '5px 10px', 'fontSize': '10px'},
                                **{'data-join-open-game': r['code']}),
                ], style={'display': 'flex', 'alignItems': 'center', 'padding': '8px 10px', 'border': '1px solid #e7e8e2',
                          'borderRadius': '6px', 'background': '#fff', 'marginBottom': '6px'}))
            open_games_html = html.Div(open_rows)

        # Room Status in Lobby
        room_status_style = {'display': 'none'}
        room_status_html = None
        if state and state.get('mp') and screen == 'home':
            room_status_style = {'display': 'block'}
            c = state['mp']['code']
            conn = state['mp']['connected']
            room_status_html = html.Div([
                html.Strong(f"Hosting Room {c}"),
                html.P('Connected! Opponent joined.' if conn else 'Waiting for opponent to join…', style={'fontSize': '11px', 'margin': '4px 0'}),
                html.Button('Resume game →', type='button', className='button primary', **{'data-resume-game': f'mp:{c}'}),
            ], style={'padding': '10px', 'border': '1px solid #d4dfd2', 'borderRadius': '6px', 'background': '#f4f8f2'})

        # Recent completed matches
        recent_matches = DEFAULT_HUB.list_recent_matches(8)
        recent_feed_html = render_recent_games(recent_matches)

        # Friends
        friends_list = DEFAULT_AUTH.get_friends(auth.get('username')) if auth.get('role') == 'user' else []
        online_count = sum(1 for f in friends_list if f.get('is_online'))
        friends_widget_html = render_friends_widget_content(friends_list, auth)
        friends_badge_text = f"{online_count} online" if online_count else "Offline"

        # Leaderboard
        lb_entries = DEFAULT_AUTH.get_leaderboard(50) if screen == 'leaderboard' else []
        lb_html = render_leaderboard_content(lb_entries, auth) if screen == 'leaderboard' else None

        # About
        about_html = render_about_content(subtab) if screen == 'about' else None

        # Profile
        target_u = target_profile or auth.get('username')
        prof_data = DEFAULT_AUTH.get_user(target_u) if screen == 'profile' else None
        is_friend = DEFAULT_AUTH.is_friend(auth.get('username'), target_u) if (auth.get('role') == 'user' and prof_data) else False
        p_disp, p_sub, p_friend_btn, p_stats = render_profile_content(prof_data, auth, is_friend) if prof_data else ('', '', None, None)
        is_my_profile = (auth.get('role') == 'user' and target_u == auth.get('username'))
        prof_settings_style = {'display': 'grid', 'gridTemplateColumns': 'repeat(auto-fit, minmax(320px, 1fr))', 'gap': '24px'} if is_my_profile else {'display': 'none'}

        # Game View HTML
        p_idx = (state.get('mp') or {}).get('p_idx') if state else None
        game_view_html = game_view(state, game_message, player_idx=p_idx) if state else None

        # Styles for screen visibility
        auth_style = {} if screen == 'auth' else {'display': 'none'}
        home_style = {} if screen == 'home' else {'display': 'none'}
        game_style = {} if screen == 'game' else {'display': 'none'}
        lb_style = {} if screen == 'leaderboard' else {'display': 'none'}
        about_style = {} if screen == 'about' else {'display': 'none'}
        profile_style = {} if screen == 'profile' else {'display': 'none'}

        user_menu_style = {'display': 'block'} if auth.get('role') == 'user' else {'display': 'none'}
        nav_play_style = {'display': 'inline-block'} if screen != 'home' else {'display': 'none'}
        nav_lb_style = {'display': 'inline-block'} if screen != 'leaderboard' else {'display': 'none'}

        # Setup sub-views
        mp_panel_style = {} if mode == 'multiplayer' else {'display': 'none'}
        choice_style = {} if mp_choice_mode == 'choice' else {'display': 'none'}
        join_style = {} if mp_choice_mode == 'join' else {'display': 'none'}
        find_style = {} if lobby_tab == 'find' else {'display': 'none'}

        tab_lobby_btn_style = {'background': '#26312f', 'color': '#fff'} if lobby_tab == 'lobby' else {}
        tab_find_btn_style = {'background': '#26312f', 'color': '#fff'} if lobby_tab == 'find' else {}

        start_disabled = (mode == 'multiplayer') or (dictionary not in DICTIONARIES)
        setup_feedback = 'Choose Host or Join above for Multiplayer.' if mode == 'multiplayer' else 'Ready when you are.'
        second_player_style = {'display': 'none'} if mode in ('computer', 'multiplayer') else {}

        return (
            state, saved_games, auth, url_search_out, screen, target_profile, subtab, lobby_tab,
            False,  # mp-poll disabled = False
            auth.get('display_name') or 'Guest',
            auth.get('avatar') or 'A',
            user_menu_style, nav_play_style, nav_lb_style,
            auth_style, auth_msg,
            home_style,
            game_style, game_view_html,
            lb_style, lb_html,
            about_style, about_html,
            'button primary' if subtab == 'tech' else 'button quiet',
            'button primary' if subtab == 'why' else 'button quiet',
            profile_style, profile_msg,
            (prof_data or {}).get('avatar', 'A'),
            p_disp, p_sub, p_friend_btn, p_stats,
            prof_settings_style,
            (auth.get('display_name') or '') if is_my_profile else prof_display_name,
            (auth.get('avatar') or 'A') if is_my_profile else prof_avatar,
            woogles_status, isc_status,
            active_games_count_str, active_games_html,
            recent_feed_html,
            friends_widget_html, friends_badge_text,
            mp_panel_style, choice_style, join_style, find_style, open_games_html,
            room_status_style, room_status_html,
            tab_lobby_btn_style, tab_find_btn_style,
            start_disabled, setup_feedback, second_player_style
        )
