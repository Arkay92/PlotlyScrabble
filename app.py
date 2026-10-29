"""Local and Plotly Cloud entry point."""
from pathlib import Path
from dash import Dash
from wordgame.ui import configure_app
from wordgame.multiplayer import DEFAULT_HUB, attach_websocket

app = Dash(__name__, assets_folder=str(Path(__file__).resolve().parent / 'assets'))
configure_app(app)
server = app.server
attach_websocket(server, DEFAULT_HUB)

import os

if __name__ == '__main__':
    app.run(debug=False, port=int(os.environ.get('PORT', 8051)))
