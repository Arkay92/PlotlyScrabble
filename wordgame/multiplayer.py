"""Server-authoritative multiplayer rooms and RFC 6455 WebSocket transport for Scrabble."""
import base64
import hashlib
import json
import secrets
import sqlite3
import struct
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs
from .rules import new_game, act, evaluate
from .storage import resolve_database_path

_WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


class WebSocketClient:
    """Minimal RFC 6455 WebSocket connection wrapper over a raw WSGI socket."""

    def __init__(self, sock):
        self.sock = sock
        self._lock = threading.Lock()
        self.closed = False

    def send_text(self, payload: str):
        if self.closed:
            return
        data = payload.encode("utf-8")
        length = len(data)
        header = bytearray([0x81])
        if length <= 125:
            header.append(length)
        elif length <= 65535:
            header.append(126)
            header.extend(struct.pack("!H", length))
        else:
            header.append(127)
            header.extend(struct.pack("!Q", length))

        with self._lock:
            try:
                self.sock.sendall(header + data)
            except Exception:
                self.closed = True
                raise ConnectionError("WebSocket send failed")

    def close(self):
        self.closed = True
        try:
            with self._lock:
                self.sock.sendall(b"\x88\x00")
        except Exception:
            pass
        try:
            self.sock.close()
        except Exception:
            pass


class ScrabbleMultiplayerHub:
    """Multiplayer room registry with WebSocket pub/sub and SQLite persistence."""

    def __init__(self, db_path: Path | None = None, auth_store=None):
        self.db_path = db_path or resolve_database_path("scrabble_games.db")
        self.auth_store = auth_store
        self._lock = threading.Lock()
        self._rooms: dict[str, dict] = {}
        self._subscribers: dict[str, set[WebSocketClient]] = {}
        self._init_db()
        self._load_active_rooms()

    def _get_conn(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), timeout=15.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        return conn

    def _init_db(self):
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS scrabble_multiplayer_rooms (
                    code TEXT PRIMARY KEY,
                    dictionary TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    p1_user TEXT,
                    p2_user TEXT,
                    p1_name TEXT,
                    p2_name TEXT,
                    p1_avatar TEXT NOT NULL DEFAULT 'A',
                    p2_avatar TEXT NOT NULL DEFAULT 'E',
                    p1_token TEXT NOT NULL,
                    p2_token TEXT,
                    is_open INTEGER NOT NULL DEFAULT 1,
                    is_completed INTEGER NOT NULL DEFAULT 0,
                    version INTEGER NOT NULL DEFAULT 1,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS scrabble_completed_games (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT NOT NULL,
                    dictionary TEXT NOT NULL,
                    p1_user TEXT,
                    p2_user TEXT,
                    p1_name TEXT,
                    p2_name TEXT,
                    p1_avatar TEXT,
                    p2_avatar TEXT,
                    p1_score INTEGER NOT NULL,
                    p2_score INTEGER NOT NULL,
                    winner_name TEXT,
                    turns_count INTEGER NOT NULL,
                    completed_at REAL NOT NULL
                )
            """)

    def _load_active_rooms(self):
        with self._get_conn() as conn:
            rows = conn.execute("""
                SELECT * FROM scrabble_multiplayer_rooms
                WHERE is_completed = 0 AND updated_at > ?
            """, (time.time() - 86400 * 3,)).fetchall()

            for r in rows:
                code = r['code']
                try:
                    game_state = json.loads(r['state_json'])
                except Exception:
                    continue
                self._rooms[code] = {
                    'code': code,
                    'dictionary': r['dictionary'],
                    'state': game_state,
                    'p1_user': r['p1_user'],
                    'p2_user': r['p2_user'],
                    'p1_name': r['p1_name'],
                    'p2_name': r['p2_name'],
                    'p1_avatar': r['p1_avatar'],
                    'p2_avatar': r['p2_avatar'],
                    'tokens': {r['p1_token']: 0, **({r['p2_token']: 1} if r['p2_token'] else {})},
                    'is_open': bool(r['is_open']),
                    'is_completed': bool(r['is_completed']),
                    'version': r['version'],
                    'created_at': r['created_at'],
                    'updated_at': r['updated_at'],
                }

    def _save_room(self, room: dict):
        p1_token = [tok for tok, player in room['tokens'].items() if player == 0]
        p2_token = [tok for tok, player in room['tokens'].items() if player == 1]
        t1 = p1_token[0] if p1_token else ''
        t2 = p2_token[0] if p2_token else None

        with self._get_conn() as conn:
            conn.execute("""
                INSERT INTO scrabble_multiplayer_rooms (
                    code, dictionary, state_json, p1_user, p2_user, p1_name, p2_name,
                    p1_avatar, p2_avatar, p1_token, p2_token, is_open, is_completed, version, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(code) DO UPDATE SET
                    state_json = excluded.state_json,
                    p2_user = excluded.p2_user,
                    p2_name = excluded.p2_name,
                    p2_avatar = excluded.p2_avatar,
                    p2_token = excluded.p2_token,
                    is_open = excluded.is_open,
                    is_completed = excluded.is_completed,
                    version = excluded.version,
                    updated_at = excluded.updated_at
            """, (
                room['code'], room['dictionary'], json.dumps(room['state']),
                room['p1_user'], room['p2_user'], room['p1_name'], room['p2_name'],
                room['p1_avatar'], room['p2_avatar'], t1, t2,
                1 if room['is_open'] else 0,
                1 if room['is_completed'] else 0,
                room['version'], room['created_at'], room['updated_at']
            ))

    def create_room(self, dictionary: str = 'en_US', host_user: str | None = None, host_name: str = 'Host', host_avatar: str = 'A', is_open: bool = True) -> tuple[dict, str]:
        code = ''.join(secrets.choice('BCDFGHJKLMNPQRSTVWXYZ23456789') for _ in range(6))
        token = secrets.token_hex(16)
        now = time.time()

        game_state = new_game(dictionary, (host_name, 'Waiting for player...'), mode='pvp')
        game_state['handoff'] = False


        room = {
            'code': code,
            'dictionary': dictionary,
            'state': game_state,
            'p1_user': host_user,
            'p2_user': None,
            'p1_name': host_name,
            'p2_name': None,
            'p1_avatar': host_avatar,
            'p2_avatar': 'E',
            'tokens': {token: 0},
            'is_open': is_open,
            'is_completed': False,
            'version': 1,
            'created_at': now,
            'updated_at': now,
        }

        with self._lock:
            self._rooms[code] = room
            self._save_room(room)

        return room, token

    def join_room(self, code: str, joiner_user: str | None = None, joiner_name: str = 'Player 2', joiner_avatar: str = 'E') -> tuple[dict, str]:
        c = (code or '').strip().upper()
        with self._lock:
            room = self._rooms.get(c)
            if not room:
                raise ValueError(f'Room "{c}" does not exist or has expired.')
            if room['p2_name'] and room['p2_user']:
                raise ValueError(f'Room "{c}" is already full.')

            token = secrets.token_hex(16)
            room['tokens'][token] = 1
            room['p2_user'] = joiner_user
            room['p2_name'] = joiner_name
            room['p2_avatar'] = joiner_avatar
            room['is_open'] = False
            room['state']['players'] = [room['p1_name'], joiner_name]
            room['version'] += 1
            room['updated_at'] = time.time()
            self._save_room(room)
            self._broadcast(c)

        return room, token

    def get_room_snapshot(self, code: str, player_token: str | None = None) -> dict | None:
        c = (code or '').strip().upper()
        with self._lock:
            room = self._rooms.get(c)
            if not room:
                # Check DB directly in case another worker handled creation
                with self._get_conn() as conn:
                    row = conn.execute("SELECT * FROM scrabble_multiplayer_rooms WHERE code = ?", (c,)).fetchone()
                    if row:
                        try:
                            g_state = json.loads(row['state_json'])
                        except Exception:
                            return None
                        room = {
                            'code': row['code'],
                            'dictionary': row['dictionary'],
                            'state': g_state,
                            'p1_user': row['p1_user'],
                            'p2_user': row['p2_user'],
                            'p1_name': row['p1_name'],
                            'p2_name': row['p2_name'],
                            'p1_avatar': row['p1_avatar'],
                            'p2_avatar': row['p2_avatar'],
                            'tokens': {row['p1_token']: 0, **({row['p2_token']: 1} if row['p2_token'] else {})},
                            'is_open': bool(row['is_open']),
                            'is_completed': bool(row['is_completed']),
                            'version': row['version'],
                            'created_at': row['created_at'],
                            'updated_at': row['updated_at'],
                        }
                        self._rooms[c] = room
                    else:
                        return None

            player_idx = room['tokens'].get(player_token)
            connected = bool(room['p2_name'] or len(room['tokens']) >= 2)

            # Deep copy state and protect the other player's private rack
            import copy
            sanitized_state = copy.deepcopy(room['state'])
            sanitized_state['handoff'] = False  # No handoff screen in live online play!

            # Obfuscate opponent's rack
            if player_idx == 0:
                if len(sanitized_state['racks']) > 1:
                    sanitized_state['racks'][1] = ['?'] * len(sanitized_state['racks'][1])
            elif player_idx == 1:
                if len(sanitized_state['racks']) > 0:
                    sanitized_state['racks'][0] = ['?'] * len(sanitized_state['racks'][0])
            else:
                # Spectator / neutral: hide both
                sanitized_state['racks'] = [['?'] * len(r) for r in sanitized_state['racks']]

            return {
                'code': room['code'],
                'dictionary': room['dictionary'],
                'state': sanitized_state,
                'p1_user': room['p1_user'],
                'p2_user': room['p2_user'],
                'p1_name': room['p1_name'],
                'p2_name': room['p2_name'],
                'p1_avatar': room['p1_avatar'],
                'p2_avatar': room['p2_avatar'],
                'connected': connected,
                'player_index': player_idx,
                'my_player_idx': player_idx,
                'is_my_turn': (player_idx is not None and player_idx == sanitized_state['turn'] and not sanitized_state['finished']),
                'version': room['version'],
                'is_completed': room['is_completed'],
            }

    def play_action(self, code: str, player_token: str, action: dict, blank: str = 'A') -> dict:
        c = (code or '').strip().upper()
        with self._lock:
            room = self._rooms.get(c)
            if not room:
                raise ValueError('Room not found.')
            player_idx = room['tokens'].get(player_token)
            if player_idx is None:
                raise ValueError('You are not authorized to make moves in this room.')
            if not (room['p2_name'] or len(room['tokens']) >= 2):
                raise ValueError('Waiting for your opponent to join before moves can be played.')
            if room['state']['finished']:
                raise ValueError('This game has already finished.')
            if player_idx != room['state']['turn']:
                current_player_name = room['state']['players'][room['state']['turn']]
                raise ValueError(f"Wait for {current_player_name} to complete their turn.")

            # Execute move using pure rules
            new_state, msg = act(room['state'], action, blank=blank)
            new_state['handoff'] = False
            room['state'] = new_state

            room['version'] += 1
            room['updated_at'] = time.time()

            if new_state['finished']:
                room['is_completed'] = True
                self._record_completed_game(room)

            self._save_room(room)
            self._broadcast(c)

        return self.get_room_snapshot(c, player_token)

    def _record_completed_game(self, room: dict):
        state = room['state']
        p1_score = state['scores'][0]
        p2_score = state['scores'][1]
        p1_name = room['p1_name'] or 'Player 1'
        p2_name = room['p2_name'] or 'Player 2'

        if p1_score > p2_score:
            winner = p1_name
        elif p2_score > p1_score:
            winner = p2_name
        else:
            winner = 'Draw'

        with self._get_conn() as conn:
            conn.execute("""
                INSERT INTO scrabble_completed_games (
                    code, dictionary, p1_user, p2_user, p1_name, p2_name,
                    p1_avatar, p2_avatar, p1_score, p2_score, winner_name,
                    turns_count, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                room['code'], room['dictionary'],
                room['p1_user'], room['p2_user'],
                p1_name, p2_name,
                room['p1_avatar'], room['p2_avatar'],
                p1_score, p2_score, winner,
                len(state['history']), time.time()
            ))

        if self.auth_store:
            # Update player stats
            if room['p1_user']:
                self.auth_store.record_match_result(
                    room['p1_user'],
                    won=(p1_score > p2_score),
                    is_draw=(p1_score == p2_score),
                    opponent_rating=1000,
                    match_score=p1_score
                )
            if room['p2_user']:
                self.auth_store.record_match_result(
                    room['p2_user'],
                    won=(p2_score > p1_score),
                    is_draw=(p1_score == p2_score),
                    opponent_rating=1000,
                    match_score=p2_score
                )

    def get_open_rooms(self, limit: int = 10) -> list[dict]:
        with self._get_conn() as conn:
            rows = conn.execute("""
                SELECT code, dictionary, p1_user, p1_name, p1_avatar, created_at
                FROM scrabble_multiplayer_rooms
                WHERE is_open = 1 AND is_completed = 0 AND updated_at > ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (time.time() - 3600 * 4, limit)).fetchall()

        return [dict(r) for r in rows]

    def get_recent_completed_games(self, limit: int = 6) -> list[dict]:
        with self._get_conn() as conn:
            rows = conn.execute("""
                SELECT * FROM scrabble_completed_games
                ORDER BY completed_at DESC
                LIMIT ?
            """, (limit,)).fetchall()

        return [dict(r) for r in rows]

    # --- WebSocket Pub/Sub ---

    def register_subscriber(self, code: str, client: WebSocketClient):
        c = code.strip().upper()
        with self._lock:
            if c not in self._subscribers:
                self._subscribers[c] = set()
            self._subscribers[c].add(client)

    def unregister_subscriber(self, code: str, client: WebSocketClient):
        c = code.strip().upper()
        with self._lock:
            if c in self._subscribers:
                self._subscribers[c].discard(client)

    def _broadcast(self, code: str):
        c = code.strip().upper()
        room = self._rooms.get(c)
        if not room:
            return
        version = room['version']
        connected = bool(room['p2_name'] or len(room['tokens']) >= 2)
        payload = json.dumps({'type': 'sync', 'code': c, 'version': version, 'connected': connected})

        subscribers = list(self._subscribers.get(c, []))
        dead = []
        for s in subscribers:
            try:
                s.send_text(payload)
            except Exception:
                dead.append(s)

        if dead:
            with self._lock:
                for d in dead:
                    self._subscribers.get(c, set()).discard(d)


    # Aliases for flexibility across components
    apply_action = play_action
    list_open_rooms = get_open_rooms
    list_recent_matches = get_recent_completed_games


def attach_websocket(server, hub: ScrabbleMultiplayerHub):

    """Attach WSGI WebSocket upgrade handler (/ws?code=...) with HTTP polling fallback."""
    inner_app = server.wsgi_app

    def wsgi_app(environ, start_response):
        if environ.get("PATH_INFO") != "/ws":
            return inner_app(environ, start_response)

        query = {k: v[0] for k, v in parse_qs(environ.get("QUERY_STRING", "")).items()}
        code = (query.get("code") or "").strip().upper()
        token = query.get("token") or ""

        # HTTP JSON polling fallback for cloud proxies
        if query.get("poll"):
            snap = hub.get_room_snapshot(code, token) if code else None
            body = json.dumps(snap or {}).encode("utf-8")
            start_response("200 OK", [
                ("Content-Type", "application/json"),
                ("Cache-Control", "no-cache, no-store, must-revalidate"),
                ("Access-Control-Allow-Origin", "*"),
            ])
            return [body]

        upgrade = environ.get("HTTP_UPGRADE", "").lower()
        sec_key = environ.get("HTTP_SEC_WEBSOCKET_KEY", "")
        raw_sock = environ.get("gunicorn.socket") or environ.get("wsgi.input", {}).fileno() if hasattr(environ.get("wsgi.input"), "fileno") else None

        if upgrade != "websocket" or not sec_key:
            start_response("400 Bad Request", [("Content-Type", "text/plain")])
            return [b"WebSocket upgrade required."]

        accept = base64.b64encode(hashlib.sha1((sec_key.strip() + _WS_GUID).encode("ascii")).digest()).decode("ascii")
        headers = [
            ("Upgrade", "websocket"),
            ("Connection", "Upgrade"),
            ("Sec-WebSocket-Accept", accept),
        ]
        start_response("101 Switching Protocols", headers)

        # In gunicorn / WSGI sync workers, complete handoff if raw socket is accessible
        if hasattr(raw_sock, 'sendall'):
            client = WebSocketClient(raw_sock)
            hub.register_subscriber(code, client)
            try:
                # Keep socket alive listening for ping/pong
                while not client.closed:
                    time.sleep(1)
            finally:
                hub.unregister_subscriber(code, client)
                client.close()

        return [b""]

    server.wsgi_app = wsgi_app


from .auth import DEFAULT_AUTH
DEFAULT_HUB = ScrabbleMultiplayerHub(auth_store=DEFAULT_AUTH)

