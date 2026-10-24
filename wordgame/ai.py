"""Legal Scrabble candidates ranked by conditional probabilistic specialists."""
from collections import Counter
from copy import deepcopy
from functools import lru_cache
import os
from pathlib import Path
import numpy as np

from .movegen import generate
from .npc import CircuitRouter
from .rules import POINTS,PREMIUMS,act,neighbours,play

DEFAULT_MODEL = Path(__file__).resolve().parents[1]/'models'/'scrabble-npc.npz'


def leave_quality(letters):
    if not letters:
        return 4
    counts = Counter(letters)
    vowels = sum(counts[l] for l in 'AEIOU')
    imbalance = abs(vowels/len(letters)-.42)
    duplicates = sum(max(0,n-1) for n in counts.values())
    quality = 4-4*imbalance-.45*duplicates-.35*sum(counts[l] for l in 'QJXZ')+counts['?']
    return int(np.clip(round(quality),0,4))


def concepts(state,candidate):
    used = {t['rack'] for t in candidate['pending'].values()}
    leave = [t for i,t in enumerate(state['racks'][state['turn']]) if i not in used]
    occupied = set(state['board'])|set(candidate['pending'])
    exposed = {str(n) for key in candidate['pending'] for n in neighbours(int(key))
               if str(n) not in occupied and PREMIUMS.get(str(n)) in ('TW','DW')}
    # Only bag SIZE and the player's own leave; hidden draws/opponent rack ignored.
    return [min(8,candidate['score']//8),leave_quality(leave),len(used),
            sum(t['blank'] for t in candidate['pending'].values()),min(4,len(exposed)),
            0 if len(state['bag'])>20 else 1 if state['bag'] else 2]


@lru_cache(maxsize=4)
def load_router(path):
    return CircuitRouter.load(path)


class ScrabbleAI:
    def __init__(self,model_path=None,node_limit=100000,move_limit=3000):
        path = Path(model_path or os.environ.get('SCRABBLE_NPC_MODEL') or DEFAULT_MODEL).resolve()
        self.router = load_router(str(path))
        self.node_limit,self.move_limit = node_limit,move_limit

    def choose(self,state):
        if state['finished']:
            raise ValueError('The game has finished.')
        candidates,stats = generate(state,self.node_limit,self.move_limit)
        if not candidates:
            # Exchange all tiles rather than pass if there are enough unseen tiles.
            return {'kind':'exchange' if len(state['bag'])>=7 else 'pass','search':stats}
        x = np.asarray([concepts(state,c) for c in candidates])
        posterior,weights = self.router.predict(x)
        # The model is a bounded strategic term, preserving the value of points.
        utility = np.array([c['score'] for c in candidates],dtype=float) + 10*(posterior[:,2]-posterior[:,0])
        utility += 1.5*x[:,1]-.8*x[:,4]
        # Deterministic ties keep behaviour reproducible.
        index = int(np.argmax(utility))
        return {'kind':'play',**candidates[index],'weights':weights[index].tolist(),
                'quality':posterior[index].tolist(),'search':stats,'utility':float(utility[index])}

    def take_turn(self,original):
        """One atomic computer turn, committed through exactly the human rules."""
        state = deepcopy(original)
        state.update(handoff=False,pending={},selected=None,exchange=False,exchange_tiles=[])
        decision = self.choose(state)
        if decision['kind']=='play':
            state['pending'] = decision['pending']
            state = play(state)
            explanation = ', '.join(w['word'] for w in decision['words'])+f" for {decision['score']} points"
        elif decision['kind']=='exchange':
            state,_ = act(state,{'type':'exchange'})
            for i in range(len(state['racks'][state['turn']])):
                state,_ = act(state,{'type':'rack','slot':i})
            state,_ = act(state,{'type':'exchange-confirm'})
            explanation = 'exchanged its tiles'
        else:
            state,_ = act(state,{'type':'pass'})
            explanation = 'passed'
        # Never return the computer rack to the UI for a reveal step.
        state['handoff'] = False
        state['history'][-1]['ai'] = {k:decision[k] for k in ('weights','quality','search') if k in decision}
        state['ai_message'] = f'Computer played {explanation}.' if decision['kind']=='play' else f'Computer {explanation}.'
        return state,state['ai_message']
