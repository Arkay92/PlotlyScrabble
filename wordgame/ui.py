"""Dash layout and a single callback coordinating a session-local game."""
from dash import Input, Output, State, ctx, dcc, html
from .dictionaries import DICTIONARIES
from .rules import CENTER, POINTS, PREMIUMS, act, evaluate, new_game
from .ai import ScrabbleAI


def tile(letter, blank=False):
    return html.Span([html.Span(letter,className='tile-letter'),
                      html.Sub('0' if blank else str(POINTS[letter]),className='tile-points')],
                     className='letter-tile blank-tile' if blank else 'letter-tile')


def control(label, action, class_name='button secondary', disabled=False, **extra):
    return html.Button(label, type='button',className=class_name,disabled=disabled,
                       **{'data-action':action,**extra})


def board_view(state):
    cells = []
    for square in range(225):
        key = str(square)
        draft = state['pending'].get(key)
        placed = draft or state['board'].get(key)
        premium = PREMIUMS.get(key,'')
        classes = ['board-cell',premium.lower() or 'plain']
        label = f'{chr(65+square%15)}{square//15+1}'
        if placed:
            children = tile(placed['letter'],placed['blank'])
            label += f', {placed["letter"]}' + (', blank tile' if placed['blank'] else '')
            classes.append('draft' if draft else 'committed')
        else:
            children = html.Span('★' if square==CENTER else premium,className='premium-label')
            label += f', {premium or "empty"}'
        if key in state['last']:
            classes.append('last-play')
        if state['selected']==f'cell:{key}':
            classes.append('selected')
        cells.append(html.Button(children,id=f'cell-{square}',type='button',className=' '.join(classes),
            title=label,**{'aria-label':label,'data-cell':key,'data-action':'cell',
                          'data-source':f'cell:{key}' if draft else '',
                          'data-draggable':str(bool(draft and not state['handoff'] and not state['finished'])).lower()}))
    return html.Div([
        html.Div([html.Span(chr(65+i)) for i in range(15)],className='column-labels'),
        html.Div([html.Div([html.Span(str(i+1)) for i in range(15)],className='row-labels'),
                  html.Div(cells,className='scrabble-grid',role='group',**{'aria-label':'15 by 15 word board'})],className='board-with-ranks'),
    ],className='board-frame')


def rack_view(state):
    player = state['turn']
    if state.get('mode')=='computer' and player==1 and not state['finished']:
        return html.Div([html.H3('Computer turn'),html.P('The computer’s rack stays hidden.'),
                         control('Retry computer move','retry','button secondary')],className='handoff')
    if state['handoff'] and not state['finished']:
        return html.Div([html.Div('YOUR TURN',className='eyebrow'),
            html.H3(f"Pass the device to {state['players'][player]}"),
            html.P('Keep your letters to yourself. Reveal your rack when you are ready.'),
            control('Reveal my tiles →','ready','button primary')],className='handoff')
    if state['finished']:
        top = max(state['scores'])
        leaders = [state['players'][i] for i,score in enumerate(state['scores']) if score==top]
        return html.Div([html.Div('FINAL SCORE',className='eyebrow'),
                         html.H3('A well-played draw.' if len(leaders)>1 else f'{leaders[0]} wins!'),
                         html.P(state['end_reason']),control('Play another game','restart','button primary')],className='handoff')
    used = {t['rack'] for t in state['pending'].values()}
    slots = []
    for index,letter in enumerate(state['racks'][player]):
        classes = ['rack-slot']
        if index in used:
            classes.append('used')
        if state['selected']==f'rack:{index}' or index in state['exchange_tiles']:
            classes.append('selected')
        slots.append(html.Button(tile(letter) if index not in used else html.Span('·'),
            id=f'rack-{index}',className=' '.join(classes),type='button',
            **{'aria-label':f'Rack tile {index+1}: {"blank" if letter=="?" else letter}',
               'aria-pressed':str('selected' in classes).lower(),'data-action':'rack','data-slot':str(index),
               'data-source':f'rack:{index}','data-draggable':str(index not in used and not state['exchange']).lower()}))
    return html.Div([
        html.Div([html.Div([html.Span('YOUR LETTERS',className='eyebrow'),html.Strong(state['players'][player])]),
                  control('↻  Shuffle','shuffle','text-button',bool(used) or state['exchange'])],className='rack-heading'),
        html.Div(slots,className='rack',role='group',**{'aria-label':'Your tile rack','data-rack-target':'true'}),
        html.Div([html.Span('Blank tile represents'),html.Select([html.Option(chr(i),value=chr(i),selected=chr(i)==state.get('blank_choice','A')) for i in range(65,91)],
                    id='blank-letter',**{'aria-label':'Letter represented by blank tiles'}),
                  html.Span('Choose before placing a blank.',className='blank-help')],className='blank-picker'),
    ],className='rack-panel')


def game_view(state, message):
    active = not state['handoff'] and not state['finished'] and not (state.get('mode')=='computer' and state['turn']==1)
    scorecards = [html.Div([html.Div([html.Span('0'+str(i+1),className='player-avatar'),
                          html.Div([html.Strong(name),html.Small('Your turn' if i==state['turn'] and not state['finished'] else 'Player '+str(i+1))])],className='player-info'),
                          html.Span(str(state['scores'][i]),className='score')],
                          className='player-card active' if i==state['turn'] and not state['finished'] else 'player-card')
                  for i,name in enumerate(state['players'])]
    preview,valid = 'Place tiles to build your word.',False
    if state['pending']:
        try:
            result = evaluate(state)
            preview = ' + '.join(f"{w['word']} ({w['score']})" for w in result['words'])
            if result['bonus']:
                preview += ' + 50 bingo'
            preview += f" = {result['score']} points"
            valid = True
        except ValueError as error:
            preview = str(error)
    history = [html.Div([html.Span(str(index+1).zfill(2),className='move-number'),
                         html.Div([html.Strong(', '.join(w['word'] for w in event['words']) if event['kind']=='play' else
                                               'Passed' if event['kind']=='pass' else f"Exchanged {event['count']} tiles"),
                                   html.Small(state['players'][event['player']])]),
                         html.Span(f"+{event['score']}",className='history-score')],className='history-row')
               for index,event in reversed(list(enumerate(state['history'])))]
    return html.Div([
        html.Div([html.Div([html.P('MAKE EVERY LETTER COUNT',className='eyebrow'),html.H1('A little room for a big word.')]),
                  html.Div([
                      html.Div([html.Span('●',className='online-dot'),DICTIONARIES[state['dictionary']][0]],className='dictionary-badge'),
                      control('New game','restart','button secondary',id='new-game'),
                      control('Back to home','home','button quiet',id='back-home'),
                  ],className='page-tools')],className='page-intro'),
        html.Div([
            html.Section([html.Div([html.Span(f"{state['players'][state['turn']]} to play" if not state['finished'] else 'Game complete'),
                                   html.Span(f"{len(state['bag'])} tiles in the bag",id='bag-count')],className='board-caption'),
                          html.Div(board_view(state),className='board-shell'),
                          html.Div('Drag a tile onto the board, or click a tile and a square. Draft tiles can be moved or recalled.',className='board-help'),
                          rack_view(state)],className='play-area'),
            html.Aside([
                html.Section([html.Div([html.H2('Your game'),html.Span('VS COMPUTER' if state.get('mode')=='computer' else 'TWO PLAYERS',className='small-badge')],className='card-heading'),
                    *scorecards,html.Div(message,id='feedback',className='feedback',role='status',**{'aria-live':'polite'}),
                    html.Div(preview,id='preview',className='score-preview valid' if valid else 'score-preview'),
                    control('Play word →','play','button primary full',not active or not valid,id='play-word'),
                    html.Div([control('Recall tiles','recall','button secondary',not active or not state['pending']),
                              control('Pass turn','pass','button quiet',not active)],className='game-actions'),
                    control('Cancel exchange' if state['exchange'] else 'Exchange tiles','exchange','text-button full',not active or len(state['bag'])<7),
                    control(f"Exchange {len(state['exchange_tiles'])} selected tiles",'exchange-confirm','button primary full',
                            not state['exchange_tiles']) if state['exchange'] else None,
                ],className='panel'),
                html.Section([html.Div([html.H2('Word history'),html.Span(str(len(history))+' turns',id='turn-count',className='muted')],className='card-heading'),
                              html.Div(history or [html.P('Your next idea starts here.',className='history-empty')],className='history-list')],className='panel history-panel'),
                html.Details([html.Summary('A quick guide'),html.P('First word: cover the centre star. After that, connect to the board. Every word you form must be in the selected dictionary.'),
                    html.P('Use all seven tiles for a 50-point bonus. Blanks score zero and keep their chosen letter.'),
                    html.P('Exchange needs at least seven tiles in the bag. Six scoreless turns end the game, with remaining tile values deducted.'),
                    html.P('To remove one draft tile, drag it back to the rack.'),
                    html.P('US / UK / CA / AU lists are ESDB casual dictionaries, not official NWL or Collins tournament lists.')],className='panel guide'),
                html.Div('NPC conditional expert routing',className='npc-badge') if state.get('mode')=='computer' else None,
                html.Details([html.Summary('Computer decision'),
                    html.P(state.get('ai_message','The computer will respond after your turn.')),
                    html.P('Score, rack balance and defence specialists. Bootstrap model trained on synthetic heuristic concepts; not win probabilities.'),
                    *[html.P('Expert weights: '+', '.join(f'{w:.0%}' for w in event['ai']['weights']))
                      for event in state['history'][-1:] if 'weights' in event.get('ai',{})]],className='panel guide')
                    if state.get('mode')=='computer' else None,
            ],className='game-sidebar'),
        ],className='game-layout'),
        html.Div([html.Span([html.I(className='legend dw'),'Double word']),html.Span([html.I(className='legend tw'),'Triple word']),
                  html.Span([html.I(className='legend dl'),'Double letter']),html.Span([html.I(className='legend tl'),'Triple letter'])],className='board-legend'),
    ],className='current-game')


def configure_app(app):
    app.title = 'Letterroom · A word worth playing'
    app.layout = html.Main([
        dcc.Store(id='session',storage_type='session'),dcc.Store(id='action'),
        html.Header([html.Button([html.Span(['L',html.Sub('1')],className='brand-tile'),html.Span(['letter',html.Strong('room')])],
                                type='button',className='brand',title='Back to home',**{'data-action':'home','aria-label':'Letterroom home'}),
                     html.Span('A word worth playing.',className='brand-note'),html.Span('Play your way.',className='ready-label')],className='site-header'),
        html.Div([
            html.Section([html.P('SAME TABLE. DIFFERENT POSSIBILITIES.',className='eyebrow'),
                html.H1(['Good company.',html.Br(),'Even better words.']),
                html.P('Make a little space for a classic. Build words, find the perfect square, and make every letter count.',className='setup-description'),
                html.Div([tile(letter) for letter in 'PLAY'],className='hero-tiles',**{'aria-hidden':'true'}),
                html.Div([html.Span('15 × 15 board'),html.Span('100 tiles'),html.Span('Endless possibilities')],className='setup-facts'),
            ],className='setup-intro'),
            html.Section([html.Div([html.H2('Make it your game'),html.Span('01 / SET UP',className='small-badge')],className='card-heading'),
                html.Label('CHOOSE YOUR OPPONENT',className='field-label'),
                dcc.RadioItems(id='mode',options=[{'label':'Player vs player','value':'pvp'},
                                               {'label':'Player vs computer','value':'computer'}],value='pvp',className='mode-options'),
                html.Label('CHOOSE YOUR DICTIONARY',className='field-label'),
                dcc.RadioItems(id='dictionary',options=[{'label':html.Div([html.Span(key[-2:],className='region-code'),
                                      html.Span([html.Strong(label),html.Small(description)])]),'value':key}
                                      for key,(label,description) in DICTIONARIES.items()],value=None,className='dictionary-options'),
                html.P('Regional ESDB word lists for casual play. Not official tournament dictionaries.',className='dictionary-note'),
                html.Div([html.Div([html.Label('PLAYER ONE',htmlFor='player-one',className='field-label'),
                                    dcc.Input(id='player-one',value='Player 1',maxLength=24)]),
                          html.Div([html.Label('PLAYER TWO',htmlFor='player-two',className='field-label'),
                                    dcc.Input(id='player-two',value='Player 2',maxLength=24)],id='second-player-field')],className='name-fields'),
                html.Button('Let’s play →',id='start',className='button primary full',disabled=True),
                html.Div('Choose a dictionary to start.',id='setup-feedback',className='setup-feedback',role='status'),
                html.Small('Two players: pass-and-play. Computer: NPC-powered replies after your turn.',className='privacy-note'),
            ],className='panel setup-panel'),
        ],id='setup',className='setup-layout'),
        html.Div(id='game-view',style={'display':'none'}),
        html.Div('Updating your game…',id='thinking',className='thinking',
                 style={'display':'none'},role='status'),
        html.Footer([html.Span('Less distraction. More wordplay.'),html.Span('A Scrabble-style game · Made with Python.')]),
    ],className='app-container')

    @app.callback(Output('session','data'),Output('game-view','children'),Output('game-view','style'),
                  Output('setup','style'),Output('start','disabled'),Output('setup-feedback','children'),
                  Output('second-player-field','style'),
                  Input('action','data'),Input('start','n_clicks'),Input('dictionary','value'),Input('mode','value'),
                  State('player-one','value'),State('player-two','value'),State('session','data'),
                  running=[(Output('game-view','data-busy'),'true','false'),
                           (Output('thinking','style'),{}, {'display':'none'})])
    def update(action, start, dictionary, mode, first, second, state):
        message = 'Drag or click tiles to start building a word.'
        setup_message = 'Choose a dictionary to start.' if not dictionary else 'Dictionary selected. Ready when you are.'
        try:
            if ctx.triggered_id=='start':
                if state is None:
                    if mode=='computer':
                        ScrabbleAI()  # Fail visibly before dealing if configured model is invalid.
                    state = new_game(dictionary,(first,second),mode=mode)
            elif ctx.triggered_id=='action' and action:
                if action.get('type') in ('home','new'):
                    state = None
                elif action.get('type')=='restart' and state:
                    state = new_game(state['dictionary'],tuple(state['players']),mode=state.get('mode','pvp'))
                    message = 'A fresh board and new tiles. Your move!'
                elif state:
                    if state.get('mode')=='computer' and state['turn']==1:
                        if action.get('type')!='retry':
                            raise ValueError('It is the computer’s turn.')
                    else:
                        state,message = act(state,action,action.get('blank','A'))
            # Also resume a pending computer turn after a refresh/interruption.
            if state and state.get('mode')=='computer' and state['turn']==1 and not state['finished']:
                state,reply = ScrabbleAI().take_turn(state)
                message += ' '+reply
        except (ValueError,KeyError,TypeError,IndexError,OSError) as error:
            message = str(error) if isinstance(error,ValueError) else 'That action is unavailable. Please try again.'
            if state is None:
                setup_message = message
        if state is None:
            return None,None,{'display':'none'},{},dictionary not in DICTIONARIES,setup_message,{'display':'none'} if mode=='computer' else {}
        return state,game_view(state,message),{}, {'display':'none'},dictionary not in DICTIONARIES,setup_message,{'display':'none'} if mode=='computer' else {}
