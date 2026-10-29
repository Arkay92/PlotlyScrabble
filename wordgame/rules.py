"""Pure rules and scoring. Draft tiles never modify committed board squares."""
from copy import deepcopy
import random
from .dictionaries import DICTIONARIES, words

SIZE = 15
CENTER = 112
DISTRIBUTION = {'A':9,'B':2,'C':2,'D':4,'E':12,'F':2,'G':3,'H':2,'I':9,'J':1,
                'K':1,'L':4,'M':2,'N':6,'O':8,'P':2,'Q':1,'R':6,'S':4,'T':6,
                'U':4,'V':2,'W':2,'X':1,'Y':2,'Z':1,'?':2}
POINTS = {**dict.fromkeys('AEILNORSTU',1),**dict.fromkeys('DG',2),
          **dict.fromkeys('BCMP',3),**dict.fromkeys('FHVWY',4),'K':5,'J':8,'X':8,'Q':10,'Z':10,'?':0}


def premiums():
    result = {}
    for row,col in [(0,0),(0,7),(0,14),(7,0),(7,14),(14,0),(14,7),(14,14)]:
        result[str(row*15+col)] = 'TW'
    for i in range(1,5):
        for row,col in [(i,i),(i,14-i),(14-i,i),(14-i,14-i)]:
            result[str(row*15+col)] = 'DW'
    result[str(CENTER)] = 'DW'
    for row,col in [(1,5),(1,9),(5,1),(5,5),(5,9),(5,13),(9,1),(9,5),(9,9),(9,13),(13,5),(13,9)]:
        result[str(row*15+col)] = 'TL'
    for row,col in [(0,3),(0,11),(2,6),(2,8),(3,0),(3,7),(3,14),(6,2),(6,6),(6,8),(6,12),
                    (7,3),(7,11),(8,2),(8,6),(8,8),(8,12),(11,0),(11,7),(11,14),(12,6),(12,8),(14,3),(14,11)]:
        result[str(row*15+col)] = 'DL'
    return result


PREMIUMS = premiums()


def new_game(dictionary, players=('Player 1','Player 2'), rng=None, mode='pvp'):
    if mode not in ('pvp','computer'):
        raise ValueError('Choose two players or player vs computer.')
    words(dictionary)  # Validate and load before dealing any tiles.
    rng = rng or random.SystemRandom()
    bag = [letter for letter,count in DISTRIBUTION.items() for _ in range(count)]
    rng.shuffle(bag)
    racks = [[bag.pop() for _ in range(7)] for _ in range(2)]
    if mode=='computer':
        players = (players[0],'Computer')
    return {'dictionary':dictionary,'mode':mode,'players':[(name or f'Player {i+1}').strip()[:24] or f'Player {i+1}' for i,name in enumerate(players)],
            'board':{},'bag':bag,'racks':racks,'scores':[0,0],'turn':0,'pending':{},'selected':None,
            'history':[],'scoreless':0,'finished':False,'handoff':False,'exchange':False,'exchange_tiles':[],
            'last':[],'end_reason':'','blank_choice':'A'}


def value(tile):
    return 0 if tile.get('blank') else POINTS[tile['letter']]


def neighbours(square):
    row,col = divmod(int(square),15)
    return [r*15+c for r,c in ((row-1,col),(row+1,col),(row,col-1),(row,col+1)) if 0<=r<15 and 0<=c<15]


def word_line(board, square, dr, dc):
    row,col = divmod(int(square),15)
    while 0<=row-dr<15 and 0<=col-dc<15 and str((row-dr)*15+col-dc) in board:
        row,col = row-dr,col-dc
    line = []
    while 0<=row<15 and 0<=col<15 and str(row*15+col) in board:
        line.append(str(row*15+col))
        row,col = row+dr,col+dc
    return line


def evaluate(state, lexicon=None):
    """Validate every formed word; premiums apply to draft tiles only."""
    draft, fixed = state['pending'],state['board']
    if not draft:
        raise ValueError('Place a word on the board first.')
    used = set()
    for key,tile in draft.items():
        slot = tile['rack']
        if key in fixed or not 0<=int(key)<225 or slot in used or not 0<=slot<len(state['racks'][state['turn']]):
            raise ValueError('Invalid tile placement. Recall your tiles and try again.')
        source = state['racks'][state['turn']][slot]
        if (tile['blank'] and source != '?') or (not tile['blank'] and source != tile['letter']):
            raise ValueError('A placed tile does not match your rack.')
        if tile['letter'] not in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ' or len(tile['letter']) != 1:
            raise ValueError('Choose A–Z for the blank tile.')
        used.add(slot)
    squares = [int(key) for key in draft]
    rows,cols = {s//15 for s in squares},{s%15 for s in squares}
    if len(rows)>1 and len(cols)>1:
        raise ValueError('Place your tiles in one row or one column.')
    board = {**fixed,**draft}
    if not fixed and str(CENTER) not in draft:
        raise ValueError('Your first word must cover the centre star.')
    if fixed and not any(str(n) in fixed for s in squares for n in neighbours(s)):
        raise ValueError('Connect your word to a tile already on the board.')
    if len(squares)>1:
        step = 1 if len(rows)==1 else 15
        if any(str(s) not in board for s in range(min(squares),max(squares)+1,step)):
            raise ValueError('Words cannot have gaps between tiles.')
    lines = set()
    for square in squares:
        for direction in ((0,1),(1,0)):
            line = tuple(word_line(board,square,*direction))
            if len(line)>1:
                lines.add(line)
    if not lines:
        raise ValueError('A word needs at least two letters.')
    lexicon = words(state['dictionary']) if lexicon is None else lexicon
    formed = []
    for line in sorted(lines):
        word = ''.join(board[key]['letter'] for key in line)
        if word not in lexicon:
            label = DICTIONARIES[state['dictionary']][0]
            raise ValueError(f'{word} is not in the selected {label} dictionary.')
        subtotal,multiplier = 0,1
        for key in line:
            points = value(board[key])
            if key in draft:
                premium = PREMIUMS.get(key,'')
                if premium in ('DL','TL'):
                    points *= 2 if premium=='DL' else 3
                elif premium in ('DW','TW'):
                    multiplier *= 2 if premium=='DW' else 3
            subtotal += points
        formed.append({'word':word,'score':subtotal*multiplier})
    bonus = 50 if len(draft)==7 else 0
    return {'words':formed,'bonus':bonus,'score':sum(w['score'] for w in formed)+bonus}


def finish_turn(state, event, score=0, out=False):
    player = state['turn']
    state['history'].append({'player':player,**event,'score':score})
    state['scores'][player] += score
    state['scoreless'] = 0 if score else state['scoreless']+1
    state['pending'],state['selected'],state['exchange_tiles'],state['exchange'] = {},None,[],False
    if out or state['scoreless']>=6:
        leftovers = [sum(POINTS[t] for t in rack) for rack in state['racks']]
        for i in range(2):
            state['scores'][i] -= leftovers[i]
        if out:
            state['scores'][player] += leftovers[1-player]
        state['finished'] = True
        state['end_reason'] = 'The bag is empty and a player used their last tile.' if out else 'Six consecutive scoreless turns.'
    else:
        state['turn'] = 1-player
        state['handoff'] = True
    return state


def play(state):
    result = evaluate(state)
    state = deepcopy(state)
    used = {tile['rack'] for tile in state['pending'].values()}
    state['last'] = list(state['pending'])
    state['board'].update({key:{'letter':tile['letter'],'blank':tile['blank']} for key,tile in state['pending'].items()})
    rack = [tile for index,tile in enumerate(state['racks'][state['turn']]) if index not in used]
    while len(rack)<7 and state['bag']:
        rack.append(state['bag'].pop())
    state['racks'][state['turn']] = rack
    return finish_turn(state,{'kind':'play','words':result['words'],'bonus':result['bonus']},result['score'],not rack and not state['bag'])


def act(original, action, blank='A', rng=None):
    """Apply one UI action transactionally; failure leaves original unchanged."""
    state = deepcopy(original)
    if len(str(blank))==1 and str(blank).upper() in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
        state['blank_choice'] = str(blank).upper()
    kind = action.get('type')
    if state['finished']:
        raise ValueError('This game has finished. Start a new game to play again.')
    if state['handoff']:
        if kind=='ready':
            state['handoff'] = False
            return state,'Your rack is ready. Find your next word.'
        raise ValueError('Pass the device to the next player, then reveal their rack.')
    if kind=='play':
        updated = play(state)
        return updated,f"Scored {updated['history'][-1]['score']} points."
    if kind=='pass':
        return finish_turn(state,{'kind':'pass'}),'Turn passed.'
    if kind=='recall':
        state.update(pending={},selected=None,exchange=False,exchange_tiles=[])
        return state,'All draft tiles returned to your rack.'
    if kind=='shuffle':
        player_idx = action.get('player_index')
        turn = player_idx if (player_idx is not None and 0 <= player_idx < len(state['racks'])) else state['turn']
        used_slots = {t['rack'] for t in state.get('pending', {}).values()} if turn == state['turn'] else set()
        rack = state['racks'][turn]
        free_indices = [i for i in range(len(rack)) if i not in used_slots]
        if len(free_indices) > 1:
            free_letters = [rack[i] for i in free_indices]
            (rng or random.SystemRandom()).shuffle(free_letters)
            for i, letter in zip(free_indices, free_letters):
                rack[i] = letter
        state['selected'] = None
        return state, 'Rack shuffled.'
    if kind=='exchange':
        if len(state['bag'])<7:
            raise ValueError('You need at least seven tiles in the bag to exchange.')
        if state['pending']:
            raise ValueError('Recall your draft tiles before exchanging.')
        state['exchange'] = not state['exchange']
        state['exchange_tiles'],state['selected'] = [],None
        return state,'Select rack tiles, then confirm exchange.' if state['exchange'] else 'Exchange cancelled.'
    if kind=='exchange-confirm':
        slots = state['exchange_tiles']
        if not state['exchange'] or not slots or len(state['bag'])<7:
            raise ValueError('Select at least one tile to exchange; seven tiles must remain in the bag.')
        rack = state['racks'][state['turn']]
        returned = [rack[i] for i in slots]
        replacements = [state['bag'].pop() for _ in slots]
        for index,tile in zip(slots,replacements):
            rack[index] = tile
        state['bag'].extend(returned)
        (rng or random.SystemRandom()).shuffle(state['bag'])
        return finish_turn(state,{'kind':'exchange','count':len(slots)}),'Tiles exchanged.'
    if kind=='return':
        state['pending'].pop(str(action['cell']),None)
        state['selected'] = None
        return state,'Tile returned to your rack.'
    if kind=='rack':
        if (state.get('selected') or '').startswith('cell:'):
            c_key = state['selected'].split(':')[1]
            state['pending'].pop(c_key, None)
            state['selected'] = None
            return state, 'Tile returned to your rack.'
        slot = int(action['slot'])
        if not 0<=slot<len(state['racks'][state['turn']]):
            raise ValueError('Choose a tile in your rack.')
        if state['exchange']:
            if slot in state['exchange_tiles']:
                state['exchange_tiles'].remove(slot)
            else:
                state['exchange_tiles'].append(slot)
        elif slot not in {t['rack'] for t in state['pending'].values()}:
            state['selected'] = None if state['selected']==f'rack:{slot}' else f'rack:{slot}'
        return state,'Select a board square for your tile.'
    if kind not in ('cell','drop'):
        raise ValueError('Unknown action.')
    if state['exchange']:
        raise ValueError('Finish or cancel the exchange before placing tiles.')
    target = str(int(action['cell']))
    if not 0<=int(target)<225:
        raise ValueError('Place your tile on the board.')
    source = action.get('source') if kind=='drop' else state['selected']
    if target in state['pending']:
        # Clicking or dropping on a draft tile recalls it back to the rack
        state['pending'].pop(target, None)
        state['selected'] = None
        return state, 'Tile returned to your rack.'
    if not source:
        return state,'Choose a tile from your rack first.'
    if target in state['board']:
        raise ValueError('That square already has a tile.')
    source_kind,index = source.split(':')
    if source_kind=='cell':
        tile = state['pending'].pop(str(int(index)))
    elif source_kind=='rack':
        slot = int(index)
        if not 0<=slot<len(state['racks'][state['turn']]) or slot in {t['rack'] for t in state['pending'].values()}:
            raise ValueError('That tile is already on the board.')
        letter = state['racks'][state['turn']][slot]
        blank = str(blank).upper()
        if letter=='?' and (len(blank)!=1 or blank not in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'):
            raise ValueError('Choose a letter for the blank tile.')
        tile = {'letter':blank if letter=='?' else letter,'blank':letter=='?','rack':slot}
    else:
        raise ValueError('Choose a rack tile or a draft tile.')
    state['pending'][target] = tile
    state['selected'] = None
    return state,'Draft placed. Play your word when you are ready.'
