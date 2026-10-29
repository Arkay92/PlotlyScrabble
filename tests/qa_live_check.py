"""Full in-browser automated QA pass for https://plotly-scrabble.plotly.app/."""
import base64
import json
import os
import struct
import socket
import subprocess
import time
import urllib.request
from urllib.parse import urlparse
from pathlib import Path


class CDPBrowser:
    def __init__(self, edge_exe, url, debugging_port=9222):
        self.edge_exe = edge_exe
        self.url = url
        self.port = debugging_port
        self.proc = None
        self.sock = None
        self.msg_id = 0

    def start(self):
        self.proc = subprocess.Popen([
            self.edge_exe,
            '--headless=new',
            f'--remote-debugging-port={self.port}',
            '--window-size=1440,1080',
            '--disable-gpu',
            '--no-first-run',
            '--no-default-browser-check',
            self.url
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(3)

        with urllib.request.urlopen(f'http://127.0.0.1:{self.port}/json') as r:
            targets = json.loads(r.read().decode())
        page = next(t for t in targets if t.get('type') == 'page')
        ws_url = page['webSocketDebuggerUrl']

        u = urlparse(ws_url)
        self.sock = socket.create_connection((u.hostname, u.port), timeout=10)
        key = base64.b64encode(os.urandom(16)).decode('ascii')
        req = (f'GET {u.path} HTTP/1.1\r\n'
               f'Host: {u.hostname}:{u.port}\r\n'
               f'Upgrade: websocket\r\n'
               f'Connection: Upgrade\r\n'
               f'Sec-WebSocket-Key: {key}\r\n'
               f'Sec-WebSocket-Version: 13\r\n\r\n')
        self.sock.sendall(req.encode('ascii'))
        resp = b''
        while b'\r\n\r\n' not in resp:
            resp += self.sock.recv(1024)

        # Enable runtime, page & console
        self.sock.settimeout(20)
        self.send('Page.enable')
        self.send('Runtime.enable')
        self.send('Console.enable')


    def send(self, method, params=None):
        self.msg_id += 1
        curr_id = self.msg_id
        payload = json.dumps({'id': curr_id, 'method': method, 'params': params or {}}).encode('utf-8')
        length = len(payload)
        header = bytearray([0x81])
        if length <= 125:
            header.append(0x80 | length)
        elif length <= 65535:
            header.append(0x80 | 126)
            header.extend(struct.pack('!H', length))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack('!Q', length))
        mask = os.urandom(4)
        header.extend(mask)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(header + masked)

        # Wait for matching response
        while True:
            buf = self.sock.recv(65536)
            while len(buf) < 2:
                buf += self.sock.recv(65536)
            plen = buf[1] & 0x7F
            idx = 2
            if plen == 126:
                while len(buf) < 4:
                    buf += self.sock.recv(65536)
                plen = struct.unpack('!H', buf[2:4])[0]
                idx = 4
            elif plen == 127:
                while len(buf) < 10:
                    buf += self.sock.recv(65536)
                plen = struct.unpack('!Q', buf[2:10])[0]
                idx = 10
            while len(buf) < idx + plen:
                buf += self.sock.recv(65536)
            data = buf[idx:idx+plen].decode('utf-8', errors='ignore')
            try:
                msg = json.loads(data)
                if msg.get('id') == curr_id:
                    return msg
            except Exception:
                pass


    def evaluate(self, expr):
        res = self.send('Runtime.evaluate', {'expression': expr, 'returnByValue': True, 'awaitPromise': True})
        return res.get('result', {}).get('result', {}).get('value')

    def capture_screenshot(self, out_path):
        res = self.send('Page.captureScreenshot', {'format': 'png'})
        data = res.get('result', {}).get('data')
        if data:
            Path(out_path).parent.mkdir(parents=True, exist_ok=True)
            with open(out_path, 'wb') as f:
                f.write(base64.b64decode(data))
            print(f"  [Screenshot] Saved {out_path}")

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
        if self.proc:
            self.proc.kill()


def run_qa():
    edge_exe = r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
    target_url = 'https://plotly-scrabble.plotly.app/'
    artifacts_dir = Path(r'C:\Users\pc006\Documents\GitHub\EasyTees\PlotlyScrabble\artifacts')
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    browser = CDPBrowser(edge_exe, target_url)
    browser.start()

    results = []

    try:
        # Step 1: Wait for Dash to load
        print("\n--- STEP 1: INITIAL LOAD & CONSOLE CHECK ---")
        time.sleep(2)
        title = browser.evaluate("document.title")
        print(f"Page Title: {title}")
        results.append(("Page Title Load", "PASS" if "Letterroom" in title else "FAIL"))

        # Check for any React / Dash error overlays
        error_count = browser.evaluate("document.querySelectorAll('.dash-error-menu, ._dash-error').length")
        print(f"Dash Error Overlays Count: {error_count}")
        results.append(("Zero Dash Error Overlays", "PASS" if error_count == 0 else "FAIL"))

        # Step 2: Responsive Header & Burger Menu
        print("\n--- STEP 2: RESPONSIVE HEADER & BURGER MENU ---")
        has_burger = browser.evaluate("Boolean(document.getElementById('burger-menu-btn'))")
        has_site_nav = browser.evaluate("Boolean(document.getElementById('site-nav'))")
        print(f"Burger Menu Button present: {has_burger}")
        print(f"Site Nav present: {has_site_nav}")
        results.append(("Burger Menu Button Element", "PASS" if has_burger else "FAIL"))
        results.append(("Site Nav Element", "PASS" if has_site_nav else "FAIL"))

        # Toggle burger menu
        browser.evaluate("document.getElementById('burger-menu-btn').click()")
        nav_open = browser.evaluate("document.getElementById('site-nav').classList.contains('nav-open')")
        print(f"Site Nav opened on click: {nav_open}")
        results.append(("Burger Menu Toggle Open", "PASS" if nav_open else "FAIL"))

        browser.evaluate("document.getElementById('burger-menu-btn').click()")
        nav_closed = browser.evaluate("!document.getElementById('site-nav').classList.contains('nav-open')")
        print(f"Site Nav closed on second click: {nav_closed}")
        results.append(("Burger Menu Toggle Close", "PASS" if nav_closed else "FAIL"))

        # Step 3: Floating Friends Widget
        print("\n--- STEP 3: FLOATING FRIENDS WIDGET ---")
        has_friends_btn = browser.evaluate("Boolean(document.getElementById('friends-toggle-btn'))")
        print(f"Friends toggle button present: {has_friends_btn}")
        results.append(("Friends Toggle Button", "PASS" if has_friends_btn else "FAIL"))

        browser.evaluate("document.getElementById('friends-toggle-btn').click()")
        friends_open = browser.evaluate("document.getElementById('friends-widget').classList.contains('friends-open')")
        print(f"Friends widget opened: {friends_open}")
        results.append(("Friends Widget Open", "PASS" if friends_open else "FAIL"))

        browser.evaluate("document.getElementById('friends-close-btn').click()")
        friends_closed = browser.evaluate("!document.getElementById('friends-widget').classList.contains('friends-open')")
        print(f"Friends widget closed: {friends_closed}")
        results.append(("Friends Widget Close", "PASS" if friends_closed else "FAIL"))

        # Step 4: Navigation to Leaderboard
        print("\n--- STEP 4: LEADERBOARD SCREEN ---")
        browser.evaluate("document.getElementById('nav-leaderboard-btn').click()")
        time.sleep(2)
        lb_visible = browser.evaluate("window.getComputedStyle(document.getElementById('leaderboard-screen')).display !== 'none'")
        print(f"Leaderboard screen visible: {lb_visible}")
        results.append(("Navigate to Leaderboard", "PASS" if lb_visible else "FAIL"))
        browser.capture_screenshot(str(artifacts_dir / "qa_leaderboard.png"))

        # Back from Leaderboard
        browser.evaluate("document.getElementById('leaderboard-back-btn').click()")
        time.sleep(1.5)
        home_visible = browser.evaluate("window.getComputedStyle(document.getElementById('home-screen')).display !== 'none'")
        print(f"Returned to Home from Leaderboard: {home_visible}")
        results.append(("Leaderboard Back Button", "PASS" if home_visible else "FAIL"))

        # Step 5: Navigation to Why Plotly & About Screen
        print("\n--- STEP 5: ABOUT & WHY PLOTLY SCREEN ---")
        browser.evaluate("document.getElementById('nav-about-btn').click()")
        time.sleep(2)
        about_visible = browser.evaluate("window.getComputedStyle(document.getElementById('about-screen')).display !== 'none'")
        print(f"About screen visible: {about_visible}")
        results.append(("Navigate to About Screen", "PASS" if about_visible else "FAIL"))

        # Check tech tab
        has_tech_cards = browser.evaluate("document.querySelectorAll('.feature-card').length >= 4")
        print(f"Technical architecture cards rendered: {has_tech_cards}")
        results.append(("Technical Cards Rendered", "PASS" if has_tech_cards else "FAIL"))

        # Switch to Why Plotly tab
        browser.evaluate("document.getElementById('about-tab-why-btn').click()")
        time.sleep(1.5)
        has_compliance = browser.evaluate("document.querySelectorAll('.compliance-pill').length >= 4")
        print(f"Enterprise compliance pills rendered: {has_compliance}")
        results.append(("Enterprise Compliance Badges", "PASS" if has_compliance else "FAIL"))
        browser.capture_screenshot(str(artifacts_dir / "qa_about_why.png"))

        # Return to Home
        browser.evaluate("document.getElementById('about-back-btn').click()")
        time.sleep(1.5)
        home_visible2 = browser.evaluate("window.getComputedStyle(document.getElementById('home-screen')).display !== 'none'")
        print(f"Returned to Home from About: {home_visible2}")
        results.append(("About Back Button", "PASS" if home_visible2 else "FAIL"))

        # Step 6: Mode Selection & Setup
        print("\n--- STEP 6: MODE SELECTION & MULTIPLAYER SETUP ---")
        # Select Multiplayer mode
        browser.evaluate("""
            const mpRadio = document.querySelector('input[name="mode"][value="multiplayer"]');
            if (mpRadio) { mpRadio.click(); }
        """)
        time.sleep(1.5)
        mp_panel_visible = browser.evaluate("window.getComputedStyle(document.getElementById('multiplayer-panel')).display !== 'none'")
        print(f"Multiplayer Lobby visible when Multiplayer selected: {mp_panel_visible}")
        results.append(("Multiplayer Mode Switch", "PASS" if mp_panel_visible else "FAIL"))

        # Check Host / Join buttons
        has_host_btn = browser.evaluate("Boolean(document.getElementById('mp-host-btn'))")
        has_create_btn = browser.evaluate("Boolean(document.getElementById('mp-create-btn'))")
        has_join_btn = browser.evaluate("Boolean(document.getElementById('mp-choose-join-btn'))")
        print(f"Multiplayer Host/Create/Join buttons: {has_host_btn}, {has_create_btn}, {has_join_btn}")
        results.append(("Multiplayer Action Buttons", "PASS" if (has_host_btn and has_create_btn and has_join_btn) else "FAIL"))

        # Switch to Two players mode
        browser.evaluate("""
            const pvpRadio = document.querySelector('input[name="mode"][value="pvp"]');
            if (pvpRadio) { pvpRadio.click(); }
        """)
        time.sleep(1.5)

        # Step 7: Local Gameplay Interaction
        print("\n--- STEP 7: GAME START & TILE INTERACTION ---")
        browser.evaluate("document.getElementById('start').click()")
        time.sleep(2.5)

        game_layout_visible = browser.evaluate("window.getComputedStyle(document.getElementById('game-view-container')).display !== 'none'")
        board_cells_count = browser.evaluate("document.querySelectorAll('.board-cell').length")
        rack_slots_count = browser.evaluate("document.querySelectorAll('.rack-slot').length")
        print(f"Game Layout visible: {game_layout_visible}")
        print(f"Board Cells count (expected 225): {board_cells_count}")
        print(f"Rack Slots count (expected 7): {rack_slots_count}")
        results.append(("Game Start Transition", "PASS" if game_layout_visible else "FAIL"))
        results.append(("15x15 Board Cells (225)", "PASS" if board_cells_count == 225 else "FAIL"))
        results.append(("7 Rack Tile Slots", "PASS" if rack_slots_count == 7 else "FAIL"))

        # Test selecting a tile from rack
        browser.evaluate("document.getElementById('rack-0')?.click()")
        time.sleep(0.5)
        rack_0_selected = browser.evaluate("document.getElementById('rack-0')?.classList.contains('selected')")
        print(f"Rack Slot 0 selected on click: {rack_0_selected}")
        results.append(("Rack Slot Tap/Select", "PASS" if rack_0_selected else "FAIL"))

        # Tap-to-place onto centre square (square 112)
        browser.evaluate("document.getElementById('cell-112')?.click()")
        time.sleep(1)
        cell_112_has_tile = browser.evaluate("Boolean(document.querySelector('#cell-112 .letter-tile'))")
        print(f"Tile placed on board cell 112 via tap-to-place: {cell_112_has_tile}")
        results.append(("Tap-to-Place Tile on Board", "PASS" if cell_112_has_tile else "FAIL"))

        # Check score preview
        preview_text = browser.evaluate("document.getElementById('preview')?.textContent")
        print(f"Score preview text: {preview_text}")
        results.append(("Score Preview Evaluation", "PASS" if ("points" in preview_text or "not in" in preview_text) else "FAIL"))

        # Test Recall Tiles
        browser.evaluate("document.querySelector('[data-action=\"recall\"]')?.click()")
        time.sleep(1)
        cell_112_empty_again = browser.evaluate("!document.querySelector('#cell-112 .letter-tile')")
        print(f"Board cell 112 cleared after Recall tiles: {cell_112_empty_again}")
        results.append(("Recall Draft Tiles", "PASS" if cell_112_empty_again else "FAIL"))

        # Capture in-game screenshot
        browser.capture_screenshot(str(artifacts_dir / "qa_gameplay.png"))

        # Return to Home
        browser.evaluate("document.getElementById('back-home')?.click()")
        time.sleep(1.5)
        home_after_game = browser.evaluate("window.getComputedStyle(document.getElementById('home-screen')).display !== 'none'")
        print(f"Returned to Home screen from game: {home_after_game}")
        results.append(("Return Home from Game", "PASS" if home_after_game else "FAIL"))

        # Check Active Games drawer
        active_count_text = browser.evaluate("document.getElementById('active-games-count')?.textContent")
        print(f"Active Games Drawer count: {active_count_text}")
        results.append(("Active Games Drawer Populated", "PASS" if "1 active" in active_count_text else "FAIL"))

        print("\n================ QA RESULTS SUMMARY ================")
        all_passed = True
        for name, status in results:
            print(f"  {status.ljust(6)} : {name}")
            if status != "PASS":
                all_passed = False
        print("====================================================")
        print("OVERALL RESULT:", "ALL QA CHECKS PASSED!" if all_passed else "SOME CHECKS FAILED!")

    finally:
        browser.close()


if __name__ == '__main__':
    run_qa()
