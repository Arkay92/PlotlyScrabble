import os
from pathlib import Path
from wordgame.storage import get_persistent_data_dir, resolve_database_path


def test_storage_resolution_local(tmp_path, monkeypatch):
    monkeypatch.delenv("GAMES_DIR", raising=False)
    monkeypatch.delenv("DASH_DATA_DIR", raising=False)
    monkeypatch.setattr(Path, "exists", lambda self: False)

    data_dir = get_persistent_data_dir()
    assert data_dir.is_dir() or data_dir.name == "data"
    db_path = resolve_database_path("test.db")
    assert db_path.name == "test.db"


def test_storage_resolution_cloud_env(tmp_path, monkeypatch):
    fake_games = tmp_path / "Games"
    fake_games.mkdir()
    monkeypatch.setenv("GAMES_DIR", str(fake_games))

    data_dir = get_persistent_data_dir()
    assert data_dir == fake_games
    db_path = resolve_database_path("cloud_test.db")
    assert db_path == fake_games / "cloud_test.db"
