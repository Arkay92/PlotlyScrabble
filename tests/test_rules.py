from collections import Counter
from copy import deepcopy
import random

import pytest
from wordgame import rules as r
from wordgame.dictionaries import contains, words


def game(rack='CATER?S'):
    state = r.new_game('en_US',('Alice','Bob'),random.Random(42))
    state['racks'][0] = list(rack)
    return state


def draft(state, cells, letters, blank_slots=()):
    state = deepcopy(state)
    state['pending'] = {str(cell):{'letter':letter,'blank':i in blank_slots,'rack':i}
                        for i,(cell,letter) in enumerate(zip(cells,letters))}
    return state


def test_deal_and_tile_conservation():
    state = r.new_game('en_GB',rng=random.Random(1))
    assert len(state['bag'])==86
    assert len(state['racks'][0])==len(state['racks'][1])==7
    assert Counter(state['bag']+state['racks'][0]+state['racks'][1])==Counter(r.DISTRIBUTION)
    with pytest.raises(ValueError):
        r.new_game(None)


def test_dictionaries_are_real_region_specific_lists():
    assert len(words('en_US'))>70000
    assert contains('color','en_US') and not contains('colour','en_US')
    assert contains('colour','en_GB') and not contains('color','en_GB')
    assert not contains('London','en_US')


def test_center_word_score_refill_and_handoff():
    state = draft(game('CATERSX'),[111,112,113],'CAT')
    assert r.evaluate(state)['score']==10
    original = deepcopy(state)
    played,message = r.act(state,{'type':'play'})
    assert played['scores']==[10,0]
    assert played['turn']==1 and played['handoff']
    assert len(played['board'])==3 and not played['pending']
    assert len(played['racks'][0])==7
    assert state==original
    with pytest.raises(ValueError):
        r.act(played,{'type':'rack','slot':0})
    ready,_ = r.act(played,{'type':'ready'})
    assert not ready['handoff']


@pytest.mark.parametrize('cells,error',[
    ([0,1,2],'centre'),([112,114,115],'gaps'),([111,112,128],'one row'),
])
def test_first_word_geometry(cells,error):
    with pytest.raises(ValueError,match=error):
        r.evaluate(draft(game('CATERSX'),cells,'CAT'))


def test_dictionary_rejection_keeps_draft_and_score():
    state = draft(game('XYZABCD'),[111,112,113],'XYZ')
    before = deepcopy(state)
    with pytest.raises(ValueError,match='selected US'):
        r.act(state,{'type':'play'})
    assert state==before


def test_single_tile_extends_word_and_old_premium_not_reused():
    state = game('SEATXYZ')
    state['board'] = {str(s):{'letter':l,'blank':False} for s,l in zip([111,112,113],'CAT')}
    state = draft(state,[114],'S')
    assert r.evaluate(state)['words']==[{'word':'CATS','score':6}]
    state['pending'] = {'0':{'letter':'S','blank':False,'rack':0}}
    with pytest.raises(ValueError,match='Connect'):
        r.evaluate(state)


def test_all_crosswords_validated_and_premium_counts_in_each():
    state = game('TAAAAAA')
    state['board'] = {'81':{'letter':'A','blank':False},'95':{'letter':'A','blank':False}}
    state = draft(state,[96],'T')  # Double letter at G7; forms AT both ways.
    assert r.evaluate(state,{'AT'})['score']==6
    state['board']['81']['letter']='Z'
    with pytest.raises(ValueError,match='ZT'):
        r.evaluate(state,{'AT'})


def test_blank_zero_score_and_permanent_letter():
    state = draft(game('?ATERSX'),[111,112,113],'CAT',(0,))
    assert r.evaluate(state)['score']==4
    played,_ = r.act(state,{'type':'play'})
    assert played['board']['111']=={'letter':'C','blank':True}
    assert r.value(played['board']['111'])==0


def test_bingo_bonus_and_multiple_word_multipliers():
    state = draft(game('RETAINS'),list(range(109,116)),'RETAINS')
    assert r.evaluate(state)['bonus']==50
    assert r.evaluate(state)['score']==64
    state = game('CTAAAAA')
    state['board'] = {str(i):{'letter':'A','blank':False} for i in range(1,14)}
    state = draft(state,[0,14],'CT')
    assert r.evaluate(state,{'C'+'A'*13+'T'})['score']==153


def test_click_drag_recall_move_and_duplicate_tile_rejection():
    state = game('CATERSX')
    selected,_ = r.act(state,{'type':'rack','slot':0})
    placed,_ = r.act(selected,{'type':'cell','cell':112})
    assert placed['pending']['112']['letter']=='C'
    with pytest.raises(ValueError,match='already'):
        r.act(placed,{'type':'drop','source':'rack:0','cell':113})
    moved,_ = r.act(placed,{'type':'drop','source':'cell:112','cell':113})
    assert '112' not in moved['pending']
    recalled,_ = r.act(moved,{'type':'return','cell':113})
    assert not recalled['pending']


def test_blank_assignment_and_committed_tile_immutability():
    state = game('?ATERSX')
    placed,_ = r.act(state,{'type':'drop','source':'rack:0','cell':112},blank='Z')
    assert placed['pending']['112']['letter']=='Z'
    selected,_ = r.act(state,{'type':'rack','slot':0},blank='Z')
    assert selected['blank_choice']=='Z'
    clicked,_ = r.act(selected,{'type':'cell','cell':112},blank=selected['blank_choice'])
    assert clicked['pending']['112']['letter']=='Z'
    with pytest.raises(ValueError,match='blank'):
        r.act(state,{'type':'drop','source':'rack:0','cell':112},blank='ZZ')
    state['board'] = {'112':{'letter':'X','blank':False}}
    with pytest.raises(ValueError,match='already'):
        r.act(state,{'type':'drop','source':'rack:0','cell':112})


def test_exchange_requires_seven_and_preserves_tiles():
    state = r.new_game('en_US',rng=random.Random(10))
    expected = Counter(state['bag']+sum(state['racks'],[]))
    state,_ = r.act(state,{'type':'exchange'})
    state,_ = r.act(state,{'type':'rack','slot':0})
    state,_ = r.act(state,{'type':'rack','slot':1})
    state,_ = r.act(state,{'type':'exchange-confirm'},rng=random.Random(1))
    assert state['handoff'] and state['history'][-1]['count']==2
    assert Counter(state['bag']+sum(state['racks'],[]))==expected
    state['bag']=state['bag'][:6]
    state['handoff']=False
    with pytest.raises(ValueError,match='seven'):
        r.act(state,{'type':'exchange'})


def test_six_scoreless_turns_end_game_and_deduct_racks():
    state = game('AAAAAAA')
    state['racks'][1] = list('BBBBBBB')
    state['scores'] = [30,40]
    for _ in range(6):
        if state['handoff']:
            state,_ = r.act(state,{'type':'ready'})
        state,_ = r.act(state,{'type':'pass'})
    assert state['finished']
    assert state['scores']==[23,19]
    with pytest.raises(ValueError,match='finished'):
        r.act(state,{'type':'pass'})


def test_playing_out_transfers_other_rack_value():
    state = game('CAT')
    state['racks'][1] = ['Q']
    state['bag']=[]
    state = draft(state,[111,112,113],'CAT')
    played,_ = r.act(state,{'type':'play'})
    assert played['finished']
    assert played['scores']==[20,-10]


def test_dictionary_is_locked_in_game_state():
    uk = draft(r.new_game('en_GB',rng=random.Random(1)),range(110,116),'COLOUR')
    uk['racks'][0]=list('COLOURA')
    assert r.evaluate(uk)['score']>0
    us = deepcopy(uk)
    us['dictionary']='en_US'
    with pytest.raises(ValueError,match='COLOUR'):
        r.evaluate(us)
