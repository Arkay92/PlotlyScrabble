from collections import Counter
from copy import deepcopy
import random

import numpy as np
import pytest

from wordgame.ai import ScrabbleAI,concepts,DEFAULT_MODEL
from wordgame.movegen import generate
from wordgame.npc import CircuitRouter,CARDINALITIES
from wordgame.rules import new_game,act,evaluate
from wordgame.train_ai import synthetic,fit_model,load_records


def fixture_game(dictionary='en_US'):
    state = new_game(dictionary,rng=random.Random(42),mode='computer')
    state['racks'][0]=list('CATERS?')
    return state


def test_computer_candidates_are_legal_and_do_not_mutate_input():
    state = fixture_game()
    before = deepcopy(state)
    moves,stats = generate(state,move_limit=200)
    assert moves and stats['nodes']>0
    for candidate in moves:
        result = evaluate({**state,'pending':candidate['pending']})
        assert result['score']==candidate['score']
        assert all(0<=v<k for v,k in zip(concepts(state,candidate),CARDINALITIES))
    assert state==before


def test_npc_selects_legal_move_without_hidden_information():
    state = fixture_game()
    ai = ScrabbleAI(move_limit=250)
    chosen = ai.choose(state)
    assert chosen['kind']=='play'
    assert sum(chosen['weights'])==pytest.approx(1)
    assert sum(chosen['quality'])==pytest.approx(1)
    assert evaluate({**state,'pending':chosen['pending']})['score']==chosen['score']
    hidden = deepcopy(state)
    hidden['racks'][1]=list('ZZZZZZZ')
    hidden['bag']=list(reversed(state['bag']))
    again = ai.choose(hidden)
    assert again['pending']==chosen['pending']
    assert again['weights']==chosen['weights']


def test_computer_turn_preserves_tiles_and_does_not_need_reveal():
    state = new_game('en_US',rng=random.Random(42),mode='computer')
    original = Counter(state['bag']+sum(state['racks'],[]))
    updated,message = ScrabbleAI(move_limit=300).take_turn(state)
    assert not updated['handoff']
    assert len(updated['history'])==1
    actual = Counter(updated['bag']+sum(updated['racks'],[])+
                     [('?' if tile['blank'] else tile['letter']) for tile in updated['board'].values()])
    assert actual==original
    assert 'Computer' in message
    assert 'ai' in updated['history'][-1]
    assert not state['board']


def test_no_word_exchanges_or_passes_as_bag_allows():
    state = fixture_game()
    state['racks'][0]=list('QQQQQQQ')
    ai = ScrabbleAI()
    assert ai.choose(state)['kind']=='exchange'
    exchanged,_ = ai.take_turn(state)
    assert exchanged['history'][-1]['kind']=='exchange'
    state['bag']=[]
    assert ai.choose(state)['kind']=='pass'
    passed,_ = ai.take_turn(state)
    assert passed['history'][-1]['kind']=='pass'


def test_midgame_search_respects_crosswords_and_blank_values():
    state = fixture_game()
    state['board'] = {str(k):{'letter':l,'blank':i==0} for i,(k,l) in enumerate(zip((111,112,113),'CAT'))}
    state['racks'][0]=list('STARE?X')
    candidates,_ = generate(state,move_limit=200)
    assert candidates
    for candidate in candidates:
        assert evaluate({**state,'pending':candidate['pending']})['score']==candidate['score']
        assert not set(candidate['pending'])&set(state['board'])


def test_dictionary_changes_computer_candidates():
    uk = fixture_game('en_GB')
    uk['racks'][0]=list('COLOURA')
    moves,_ = generate(uk)
    assert any(any(w['word']=='COLOUR' for w in m['words']) for m in moves)
    uk['dictionary']='en_US'
    moves,_ = generate(uk)
    assert not any(any(w['word']=='COLOUR' for w in m['words']) for m in moves)


def test_model_training_roundtrip_and_domain_validation(tmp_path):
    x,y = synthetic(300,3)
    model,report = fit_model(x,y,tmp_path/'model.npz',epochs=10)
    p,w = model.predict(x[:5])
    np.testing.assert_allclose(p.sum(1),1)
    np.testing.assert_allclose(w.sum(1),1)
    loaded = CircuitRouter.load(tmp_path/'model.npz')
    np.testing.assert_allclose(loaded.predict(x[:5])[0],p)
    assert report['routing_regret']>=-1e-10
    np.savez(tmp_path/'wrong.npz',schema='chess')
    with pytest.raises(ValueError,match='compatible Scrabble'):
        CircuitRouter.load(tmp_path/'wrong.npz')
    with pytest.raises(ValueError,match='concept'):
        loaded.predict([[999]*6])


def test_modes_preserve_human_handoff():
    pvp = new_game('en_US',rng=random.Random(1))
    pvp,_ = act(pvp,{'type':'pass'})
    assert pvp['handoff'] and pvp['mode']=='pvp'
    computer = new_game('en_US',('Alice','Bob'),rng=random.Random(1),mode='computer')
    assert computer['players']==['Alice','Computer']
    with pytest.raises(ValueError,match='Choose'):
        new_game('en_US',mode='unknown')
