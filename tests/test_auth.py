import time
import pytest
from wordgame.auth import UserStore, hash_password, verify_password, rank_for_rating


def test_password_hashing():
    p_hash, salt = hash_password("secret_pass123")
    assert verify_password("secret_pass123", p_hash, salt)
    assert not verify_password("wrong_password", p_hash, salt)


def test_rank_for_rating():
    assert rank_for_rating(900) == 'Novice Wordsmith'
    assert rank_for_rating(1150) == 'Lexicon Contender'
    assert rank_for_rating(1350) == 'Word Tactician'
    assert rank_for_rating(1550) == 'Anagram Master'
    assert rank_for_rating(1750) == 'Scrabble Champion'
    assert rank_for_rating(2000) == 'Grandmaster of Words'


def test_user_store_lifecycle(tmp_path):
    db_file = tmp_path / "test_auth.db"
    store = UserStore(db_path=db_file)

    # Register
    user = store.register("alice", "pass1234", display_name="Alice Smith", avatar="Q")
    assert user['username'] == 'alice'
    assert user['display_name'] == 'Alice Smith'
    assert user['avatar'] == 'Q'
    assert user['rating'] == 1000

    # Duplicate registration should raise ValueError
    with pytest.raises(ValueError, match="already taken"):
        store.register("alice", "another_pass")

    # Login
    logged_in = store.login("alice", "pass1234")
    assert logged_in['username'] == 'alice'

    # Bad login
    with pytest.raises(ValueError, match="Invalid"):
        store.login("alice", "wrongpass")

    # Update profile
    store.update_profile("alice", display_name="Alice Grandmaster", avatar="Z")
    updated = store.get_user("alice")
    assert updated['display_name'] == 'Alice Grandmaster'
    assert updated['avatar'] == 'Z'

    # Change password
    store.change_password("alice", "pass1234", "new_secure_pass")
    assert store.login("alice", "new_secure_pass")['username'] == 'alice'
    with pytest.raises(ValueError):
        store.login("alice", "pass1234")

    # Record match result
    store.record_match_result("alice", won=True, is_draw=False, opponent_rating=1100, match_score=380)
    user_after_win = store.get_user("alice")
    assert user_after_win['wins'] == 1
    assert user_after_win['games'] == 1
    assert user_after_win['rating'] > 1000
    assert user_after_win['high_score'] == 380

    # External platforms
    store.link_woogles("alice", "alice_woogles")
    user_woogles = store.get_user("alice")
    assert user_woogles['woogles_username'] == 'alice_woogles'

    store.link_isc("alice", "alice_isc")
    user_isc = store.get_user("alice")
    assert user_isc['isc_username'] == 'alice_isc'

    # Register bob and friend system
    store.register("bob", "bobpass", display_name="Bob Jones", avatar="B")
    assert not store.is_friend("alice", "bob")
    store.toggle_friend("alice", "bob")
    assert store.is_friend("alice", "bob")

    friends = store.get_friends("alice")
    assert len(friends) == 1
    assert friends[0]['username'] == 'bob'
    assert friends[0]['is_online'] is True

    # Untoggle
    store.toggle_friend("alice", "bob")
    assert not store.is_friend("alice", "bob")
    assert len(store.get_friends("alice")) == 0

    # Leaderboard
    lb = store.get_leaderboard()
    assert len(lb) == 2
    assert lb[0]['username'] == 'alice'
    assert lb[0]['rank_num'] == 1
