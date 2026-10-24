"""Local and Plotly Cloud entry point."""
from pathlib import Path
from dash import Dash
from wordgame.ui import configure_app

app = Dash(__name__, assets_folder=str(Path(__file__).resolve().parent/'assets'))
configure_app(app)
server = app.server

if __name__ == '__main__':
    app.run(debug=False, port=8051)
