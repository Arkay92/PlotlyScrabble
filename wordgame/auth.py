"""User authentication, persistent SQLite storage, leaderboards, and friends for Scrabble."""
import hashlib
import json
import secrets
import sqlite3
import time
from pathlib import Path
from .storage import resolve_database_path

ONLINE_ACTIVITY_TIMEOUT = 120  # User is considered online if active within last 2 minutes


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    if salt is None:
        salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000)
    return digest.hex(), salt


def verify_password(password: str, password_hash: str, salt: str) -> bool:
    expected, _ = hash_password(password, salt)
    return secrets.compare_digest(expected, password_hash)


def rank_for_rating(rating: int) -> str:
    if rating >= 1900:
        return 'Grandmaster of Words'
    if rating >= 1700:
        return 'Scrabble Champion'
    if rating >= 1500:
        return 'Anagram Master'
    if rating >= 1300:
        return 'Word Tactician'
    if rating >= 1100:
        return 'Lexicon Contender'
    return 'Novice Wordsmith'


class UserStore:
    """Thread-safe SQLite user and friends repository for Scrabble."""

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or resolve_database_path("scrabble_games.db")
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), timeout=15.0)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode = DELETE")
            conn.execute("PRAGMA busy_timeout = 10000")
            conn.execute("PRAGMA synchronous = NORMAL")
        except sqlite3.DatabaseError:
            pass
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    avatar TEXT NOT NULL DEFAULT 'A',
                    rating INTEGER NOT NULL DEFAULT 1000,
                    wins INTEGER NOT NULL DEFAULT 0,
                    losses INTEGER NOT NULL DEFAULT 0,
                    draws INTEGER NOT NULL DEFAULT 0,
                    games INTEGER NOT NULL DEFAULT 0,
                    high_score INTEGER NOT NULL DEFAULT 0,
                    saved_games TEXT NOT NULL DEFAULT '[]',
                    woogles_username TEXT,
                    woogles_rating INTEGER,
                    woogles_wins INTEGER NOT NULL DEFAULT 0,
                    woogles_losses INTEGER NOT NULL DEFAULT 0,
                    isc_username TEXT,
                    isc_rating INTEGER,
                    isc_wins INTEGER NOT NULL DEFAULT 0,
                    isc_losses INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL,
                    last_seen REAL NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS friends (
                    user_id TEXT NOT NULL,
                    friend_id TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    PRIMARY KEY (user_id, friend_id)
                )
            """)

    def register(self, username: str, password: str, display_name: str | None = None, avatar: str = 'A') -> dict:
        u = (username or '').strip().lower()
        if not u or len(u) < 2 or len(u) > 24:
            raise ValueError('Enter a username between 2 and 24 characters.')
        if not all(c.isalnum() or c in '_-' for c in u):
            raise ValueError('Username can only contain letters, numbers, hyphens, and underscores.')
        if not password or len(password) < 4:
            raise ValueError('Password must be at least 4 characters.')

        disp = (display_name or username).strip()[:24] or u
        p_hash, salt = hash_password(password)
        now = time.time()

        with self._get_connection() as conn:
            existing = conn.execute("SELECT username FROM users WHERE username = ?", (u,)).fetchone()
            if existing:
                raise ValueError(f'The username "{u}" is already taken.')

            conn.execute("""
                INSERT INTO users (username, password_hash, salt, display_name, avatar, rating, created_at, last_seen)
                VALUES (?, ?, ?, ?, ?, 1000, ?, ?)
            """, (u, p_hash, salt, disp, avatar, now, now))

        return self.get_user(u)

    def login(self, username: str, password: str) -> dict:
        u = (username or '').strip().lower()
        if not u or not password:
            raise ValueError('Enter both username and password.')

        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM users WHERE username = ?", (u,)).fetchone()
            if not row:
                raise ValueError('Invalid username or password.')
            if not verify_password(password, row['password_hash'], row['salt']):
                raise ValueError('Invalid username or password.')

            now = time.time()
            conn.execute("UPDATE users SET last_seen = ? WHERE username = ?", (now, u))

        return self.get_user(u)

    def guest(self, display_name: str = 'Guest') -> dict:
        return {
            'username': 'guest',
            'display_name': display_name,
            'avatar': 'A',
            'rating': 1000,
            'rank': rank_for_rating(1000),
            'wins': 0,
            'losses': 0,
            'draws': 0,
            'games': 0,
            'high_score': 0,
            'role': 'guest',
            'saved_games': [],
            'woogles': None,
            'isc': None,
            'is_online': True,
        }

    def touch_user_activity(self, username: str):
        if not username or username == 'guest':
            return
        try:
            with self._get_connection() as conn:
                conn.execute("UPDATE users SET last_seen = ? WHERE username = ?", (time.time(), username.strip().lower()))
        except Exception:
            pass

    def get_user(self, username: str) -> dict | None:
        u = (username or '').strip().lower()
        if not u or u == 'guest':
            return None

        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM users WHERE username = ?", (u,)).fetchone()
            if not row:
                return None

            try:
                saved = json.loads(row['saved_games'] or '[]')
            except Exception:
                saved = []

            now = time.time()
            last_seen = row['last_seen'] or 0
            is_online = (now - last_seen) <= ONLINE_ACTIVITY_TIMEOUT

            woogles = None
            if row['woogles_username']:
                woogles = {
                    'username': row['woogles_username'],
                    'rating': row['woogles_rating'] or row['rating'],
                    'wins': row['woogles_wins'] or 0,
                    'losses': row['woogles_losses'] or 0,
                }

            isc = None
            if row['isc_username']:
                isc = {
                    'username': row['isc_username'],
                    'rating': row['isc_rating'] or row['rating'],
                    'wins': row['isc_wins'] or 0,
                    'losses': row['isc_losses'] or 0,
                }

            return {
                'username': row['username'],
                'display_name': row['display_name'],
                'avatar': row['avatar'],
                'rating': row['rating'],
                'rank': rank_for_rating(row['rating']),
                'wins': row['wins'],
                'losses': row['losses'],
                'draws': row['draws'],
                'games': row['games'],
                'high_score': row['high_score'],
                'role': 'user',
                'saved_games': saved,
                'woogles_username': row['woogles_username'],
                'isc_username': row['isc_username'],
                'woogles': woogles,
                'isc': isc,
                'last_seen': last_seen,
                'is_online': is_online,
            }


    def update_profile(self, username: str, display_name: str | None = None, avatar: str | None = None) -> dict:
        u = (username or '').strip().lower()
        user = self.get_user(u)
        if not user:
            raise ValueError('User not found.')

        disp = (display_name or user['display_name']).strip()[:24] or user['username']
        av = avatar or user['avatar']

        with self._get_connection() as conn:
            conn.execute("UPDATE users SET display_name = ?, avatar = ?, last_seen = ? WHERE username = ?",
                         (disp, av, time.time(), u))

        return self.get_user(u)

    def update_password(self, username: str, current_pass: str, new_pass: str):
        u = (username or '').strip().lower()
        if not new_pass or len(new_pass) < 4:
            raise ValueError('New password must be at least 4 characters.')

        with self._get_connection() as conn:
            row = conn.execute("SELECT password_hash, salt FROM users WHERE username = ?", (u,)).fetchone()
            if not row or not verify_password(current_pass, row['password_hash'], row['salt']):
                raise ValueError('Current password is incorrect.')

            new_hash, new_salt = hash_password(new_pass)
            conn.execute("UPDATE users SET password_hash = ?, salt = ?, last_seen = ? WHERE username = ?",
                         (new_hash, new_salt, time.time(), u))

    change_password = update_password
    update_last_seen = touch_user_activity

    def link_woogles(self, username: str, woogles_user: str, rating: int = 1200):
        return self.link_external_account(username, 'woogles', woogles_user, rating)

    def link_isc(self, username: str, isc_user: str, rating: int = 1200):
        return self.link_external_account(username, 'isc', isc_user, rating)

    def toggle_friend(self, username: str, friend_username: str) -> bool:
        if self.is_friend(username, friend_username):
            self.remove_friend(username, friend_username)
            return False
        else:
            self.add_friend(username, friend_username)
            return True


    def link_external_account(self, username: str, platform: str, external_user: str, external_rating: int = 1200):
        u = (username or '').strip().lower()
        ext = (external_user or '').strip()
        field_p = platform.lower()
        if field_p not in ('woogles', 'isc'):
            raise ValueError('Platform must be Woogles or ISC.')

        col_user = f"{field_p}_username"
        col_rating = f"{field_p}_rating"

        with self._get_connection() as conn:
            conn.execute(f"UPDATE users SET {col_user} = ?, {col_rating} = ?, last_seen = ? WHERE username = ?",
                         (ext, external_rating, time.time(), u))

        return self.get_user(u)

    def record_match_result(self, username: str, won: bool, is_draw: bool = False, opponent_rating: int = 1000, match_score: int = 0):
        u = (username or '').strip().lower()
        if not u or u == 'guest':
            return

        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM users WHERE username = ?", (u,)).fetchone()
            if not row:
                return

            current_rating = row['rating']
            expected = 1.0 / (1.0 + 10 ** ((opponent_rating - current_rating) / 400.0))
            k = 32
            actual = 0.5 if is_draw else (1.0 if won else 0.0)
            new_rating = max(400, round(current_rating + k * (actual - expected)))

            wins = row['wins'] + (1 if won and not is_draw else 0)
            losses = row['losses'] + (1 if not won and not is_draw else 0)
            draws = row['draws'] + (1 if is_draw else 0)
            games = row['games'] + 1
            high = max(row['high_score'], match_score)

            conn.execute("""
                UPDATE users
                SET rating = ?, wins = ?, losses = ?, draws = ?, games = ?, high_score = ?, last_seen = ?
                WHERE username = ?
            """, (new_rating, wins, losses, draws, games, high, time.time(), u))

    def get_leaderboard(self, current_user: str | None = None, limit: int = 50) -> list[dict]:
        if isinstance(current_user, int):
            limit = current_user
            current_user = None
        with self._get_connection() as conn:
            rows = conn.execute("""
                SELECT username, display_name, avatar, rating, wins, losses, draws, games, high_score, last_seen
                FROM users
                ORDER BY rating DESC, wins DESC, high_score DESC
                LIMIT ?
            """, (limit,)).fetchall()

        now = time.time()
        results = []
        for rank_idx, row in enumerate(rows, 1):
            results.append({
                'position': rank_idx,
                'rank_num': rank_idx,
                'username': row['username'],
                'display_name': row['display_name'],
                'avatar': row['avatar'],
                'rating': row['rating'],
                'rank': rank_for_rating(row['rating']),
                'wins': row['wins'],
                'losses': row['losses'],
                'draws': row['draws'],
                'games': row['games'],
                'high_score': row['high_score'],
                'is_current': bool(current_user and current_user.strip().lower() == row['username']),
                'is_online': (now - (row['last_seen'] or 0)) <= ONLINE_ACTIVITY_TIMEOUT,
            })
        return results

    # --- Friends System ---

    def add_friend(self, username: str, friend_username: str) -> bool:
        u = (username or '').strip().lower()
        f = (friend_username or '').strip().lower()
        if not u or not f or u == f or u == 'guest' or f == 'guest':
            return False

        with self._get_connection() as conn:
            # Verify friend user exists
            exists = conn.execute("SELECT 1 FROM users WHERE username = ?", (f,)).fetchone()
            if not exists:
                return False

            conn.execute("INSERT OR IGNORE INTO friends (user_id, friend_id, created_at) VALUES (?, ?, ?)",
                         (u, f, time.time()))
        return True

    def remove_friend(self, username: str, friend_username: str) -> bool:
        u = (username or '').strip().lower()
        f = (friend_username or '').strip().lower()
        if not u or not f:
            return False

        with self._get_connection() as conn:
            conn.execute("DELETE FROM friends WHERE user_id = ? AND friend_id = ?", (u, f))
        return True

    def is_friend(self, username: str, friend_username: str) -> bool:
        u = (username or '').strip().lower()
        f = (friend_username or '').strip().lower()
        if not u or not f or u == 'guest' or f == 'guest':
            return False

        with self._get_connection() as conn:
            row = conn.execute("SELECT 1 FROM friends WHERE user_id = ? AND friend_id = ?", (u, f)).fetchone()
            return bool(row)

    def get_friends(self, username: str) -> list[dict]:
        u = (username or '').strip().lower()
        if not u or u == 'guest':
            return []

        now = time.time()
        with self._get_connection() as conn:
            rows = conn.execute("""
                SELECT u.username, u.display_name, u.avatar, u.rating, u.last_seen
                FROM friends f
                JOIN users u ON f.friend_id = u.username
                WHERE f.user_id = ?
                ORDER BY u.last_seen DESC
            """, (u,)).fetchall()

        friends = []
        for r in rows:
            last = r['last_seen'] or 0
            friends.append({
                'username': r['username'],
                'display_name': r['display_name'],
                'avatar': r['avatar'],
                'rating': r['rating'],
                'rank': rank_for_rating(r['rating']),
                'last_seen': last,
                'is_online': (now - last) <= ONLINE_ACTIVITY_TIMEOUT,
            })
        return friends


DEFAULT_AUTH = UserStore()

