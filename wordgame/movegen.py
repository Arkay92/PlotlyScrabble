"""Bounded trie search: rack-aware words, anchors and perpendicular checks."""
from functools import lru_cache
from .dictionaries import words
from .rules import CENTER, evaluate, neighbours

ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'


@lru_cache(maxsize=4)
def trie(dictionary):
    root = {}
    for word in sorted(words(dictionary)):
        node = root
        for letter in word:
            node = node.setdefault(letter,{})
        node[''] = True
    return root


def advance(cell, dr, dc):
    row,col = divmod(cell,15)
    row,col = row+dr,col+dc
    return row*15+col if 0<=row<15 and 0<=col<15 else None


def generate(state, node_limit=100000, move_limit=3000):
    """Return legal drafts and search stats without modifying the game.

    Never reads the opposing rack or bag contents. Search is bounded for UI
    responsiveness; reaching a limit means the candidate set may be incomplete.
    """
    board = {int(k):v for k,v in state['board'].items()}
    rack = state['racks'][state['turn']]
    lexicon,root = words(state['dictionary']),trie(state['dictionary'])
    anchors = {n for cell in board for n in neighbours(cell) if n not in board} if board else {CENTER}
    pools = {letter:[i for i,tile in enumerate(rack) if tile==letter] for letter in set(rack)}
    candidates,seen = [],set()
    nodes = 0
    truncated = False

    for dr,dc in ((0,1),(1,0)):
        starts = set()
        for anchor in anchors:
            cell,empties = anchor,0
            while cell is not None:
                empties += cell not in board
                if empties>len(rack):
                    break
                previous = advance(cell,-dr,-dc)
                if previous not in board:
                    starts.add(cell)
                cell = previous
        checks = {}
        for cell in range(225):
            if cell in board:
                continue
            before,after = '', ''
            current = advance(cell,-dc,-dr)
            while current in board:
                before = board[current]['letter']+before
                current = advance(current,-dc,-dr)
            current = advance(cell,dc,dr)
            while current in board:
                after += board[current]['letter']
                current = advance(current,dc,dr)
            checks[cell] = set(ALPHABET) if not before and not after else {
                letter for letter in ALPHABET if before+letter+after in lexicon}

        def walk(cell, node, draft, anchored, length):
            nonlocal nodes,truncated
            if nodes>=node_limit or len(candidates)>=move_limit:
                truncated=True
                return
            nodes += 1
            if '' in node and length>=2 and draft and anchored and cell not in board:
                key = tuple(sorted((k,t['letter'],t['blank'],t['rack']) for k,t in draft.items()))
                if key not in seen:
                    seen.add(key)
                    test = {**state,'pending':draft}
                    try:
                        result = evaluate(test,lexicon)
                    except ValueError:
                        pass
                    else:
                        candidates.append({'pending':{k:dict(v) for k,v in draft.items()},**result})
            if cell is None:
                return
            following = advance(cell,dr,dc)
            if cell in board:
                letter = board[cell]['letter']
                if letter in node:
                    walk(following,node[letter],draft,anchored,length+1)
                return
            for letter in sorted(checks[cell].intersection(node).difference({''})):
                for source in (letter,'?'):
                    if not pools.get(source):
                        continue
                    slot = pools[source].pop()
                    draft[str(cell)] = {'letter':letter,'blank':source=='?','rack':slot}
                    walk(following,node[letter],draft,anchored or cell in anchors,length+1)
                    del draft[str(cell)]
                    pools[source].append(slot)
                    if truncated:
                        return

        for start in sorted(starts,key=lambda s:(abs(s//15-7)+abs(s%15-7),s)):
            walk(start,root,{},False,0)
            if truncated:
                break
        if truncated:
            break
    return candidates,{'nodes':nodes,'candidates':len(candidates),'truncated':truncated}
