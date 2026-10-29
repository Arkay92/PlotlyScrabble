import pytest
from wordgame.auth import UserStore
from wordgame.multiplayer import ScrabbleMultiplayerHub


def test_multiplayer_room_flow(tmp_path):
    db_file = tmp_path / "test_mp.db"
    auth_db = tmp_path / "test_mp_auth.db"
    auth = UserStore(db_path=auth_db)
    auth.register("player1", "pass1", "Player One", avatar="A")
    auth.register("player2", "pass2", "Player Two", avatar="B")

    hub = ScrabbleMultiplayerHub(db_path=db_file, auth_store=auth)

    # 1. Create open room
    room, p1_token = hub.create_room(dictionary="en_US", host_user="player1", host_name="Player One", host_avatar="A", is_open=True)
    code = room['code']
    assert len(code) == 6
    assert room['is_open'] is True

    # Check open rooms
    open_rooms = hub.list_open_rooms()
    assert any(r['code'] == code for r in open_rooms)

    # 2. Join room
    room_joined, p2_token = hub.join_room(code, joiner_user="player2", joiner_name="Player Two", joiner_avatar="B")
    assert room_joined['is_open'] is False
    assert len(hub.list_open_rooms()) == 0

    # 3. Snapshot with private rack secrecy
    snap_p1 = hub.get_room_snapshot(code, p1_token)
    assert snap_p1['player_index'] == 0
    assert snap_p1['connected'] is True
    # P1 can see their own rack (7 letters), but P2 rack is masked
    p1_rack = snap_p1['state']['racks'][0]
    p2_masked_rack = snap_p1['state']['racks'][1]
    assert len(p1_rack) == 7
    assert all(c != '?' for c in p1_rack) or '?' in p1_rack
    assert p2_masked_rack == ['?'] * 7

    snap_p2 = hub.get_room_snapshot(code, p2_token)
    assert snap_p2['player_index'] == 1
    # P2 can see their own rack (7 letters), but P1 rack is masked
    assert snap_p2['state']['racks'][0] == ['?'] * 7
    assert len(snap_p2['state']['racks'][1]) == 7

    # 4. Turn authority
    # P1 is turn 0, so P2 cannot play out of turn
    with pytest.raises(ValueError, match="Wait for"):
        hub.apply_action(code, p2_token, {'type': 'pass'})

    # P1 passes
    snap_after_pass = hub.apply_action(code, p1_token, {'type': 'pass'})
    assert snap_after_pass['state']['turn'] == 1
    assert len(snap_after_pass['state']['history']) == 1

    # Now P2 passes
    snap_after_p2 = hub.apply_action(code, p2_token, {'type': 'pass'})
    assert snap_after_p2['state']['turn'] == 0
    assert len(snap_after_p2['state']['history']) == 2
