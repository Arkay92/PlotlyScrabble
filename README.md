# Letterroom — a Scrabble-style game

A standalone Python/Dash project using the chess game's warm neutral design,
responsive board, pointer capture and keyboard mechanics. This project lives independently in the PlotlyScrabble repository.

## Run

From this folder, with Python 3.10 or newer:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
.\.venv\Scripts\python app.py
```

Open **http://127.0.0.1:8051**. The different port lets chess run independently.
The repository is self-contained. It does not import chess code, models, datasets or assets from PlotlyChess.

## Before the first word

Choose **Player vs player** or **Player vs computer**, then choose a dictionary.
Enter two names for local play, or just your name against the computer.
**Start remains disabled until
a dictionary is selected.** The selected dictionary governs every main word
and cross-word and cannot change during a game. Use **Back to home** to return
to setup and choose another mode or dictionary. **New game** starts a fresh board
with newly dealt tiles, preserving the current dictionary, mode and player names.
Both buttons sit above the board and also work during handoffs and after game
completion. The Letterroom logo returns to home too. Leaving clears the current
game from browser session storage.

The included dictionaries are ESDB release `2026.02.25` regional lists:

| Dictionary | Playable entries | Example |
| --- | ---: | --- |
| US English | 78,812 | COLOR accepted; COLOUR rejected |
| UK English, traditional -ise | 78,812 | COLOUR accepted; COLOR rejected |
| Canadian English | 78,814 | Canadian regional list |
| Australian English | 79,072 | Australian regional list |

These are **casual-play dictionaries, not official NASPA/NWL or Collins/CSW
tournament lexicons**. Rare tournament words and two-letter plays may differ.
No list is silently presented as an official Scrabble dictionary.

Lists are bundled for offline play; no network requests are made for validation.
Only lowercase ASCII alphabetic entries of 2–15 letters are used. Proper names,
possessives, compounds and accented entries are excluded by that filter. The
selected list is the source of truth; there is no challenge/adjudication step.

See [dictionary provenance](data/dictionaries/README.md) and the bundled
[copyright and permission notice](data/dictionaries/Copyright).

## Play

- Two-player mode uses the same device with hidden-rack handoffs. Computer
  mode automatically replies after your committed word, pass or exchange,
  then returns directly to your rack. You play first.
- Drag a rack tile to an empty square, or click a rack tile and a square.
- Draft tiles can be dragged between squares or back to the rack. **Recall
  tiles** returns the whole draft. Committed tiles cannot be moved.
- Select the letter in **Blank tile represents** before placing a `?` blank.
  Blanks remain that letter and score zero, including in later words.
- First word: cover the centre star. Subsequent plays must touch the board,
  use one row or column, and have no gaps. All formed words are validated.
- Live preview lists the words and score, or explains the invalid placement.
  **Play word** commits only valid plays.
- Letter and word premiums apply only when a tile first covers the square.
  All cross-words score, and using seven tiles adds 50 points.
- **Exchange tiles** enters selection mode. Click the tiles to exchange and
  confirm. At least seven tiles must be in the bag; new tiles are drawn before
  the exchanged tiles are returned.
- Passing or exchanging consumes a turn. Six consecutive scoreless turns end
  the game. A player emptying their rack with an empty bag also ends the game.
- At the end, remaining rack values are deducted. When one player goes out,
  the other rack's value is also added to that player's score. Equal final
  scores are treated as a draw in this implementation.

After each turn, the next rack is hidden behind a **Reveal my tiles** handoff.
This handoff applies only to two-player mode; the computer rack is never rendered.
This is a courtesy privacy screen on a shared device, not a security boundary:
the session data contains both racks and the bag.

Keyboard: Tab between controls, arrow keys between board squares, and
Enter/Space to select tiles and squares. Escape cancels an active drag.
Dragging near the page edge scrolls to help reach distant rows. Mouse, pen
and touch share the pointer-event implementation.

Game state, drafts, bag order and dictionary persist in browser session storage
through refreshes. There are no accounts, remote matches or durable server
records. Submitted actions are checked in Python, but a competitive service
would need authoritative server-side sessions and hidden information.

## Structure

```text
app.py                  Explicit Dash entry point, also usable by Plotly Cloud
wordgame/rules.py       Pure tile distribution, staging, scoring and turn logic
wordgame/dictionaries.py Cached offline regional dictionaries
wordgame/movegen.py     Bounded trie search with anchor and cross-word checks
wordgame/npc.py         Categorical circuit experts and neural routing gate
wordgame/ai.py          Scrabble concepts, candidate ranking and computer turns
wordgame/train_ai.py    Bootstrap or labelled-data NPC training
wordgame/ui.py          Setup screen, board/rack rendering and Dash callback
assets/board.js         Pointer gestures, keyboard handling and scroll support
assets/styles.css       Responsive visual system
data/dictionaries/      Four source lists, permissions, manifest and provenance
tests/                  Rules, dictionary and HTTP callback tests
scripts/prepare_cloud.py Deployment-folder generator
models/                 Bundled Scrabble NPC artifact and training report
```

## Tests

```powershell
.\.venv\Scripts\python -m pytest tests -q
node --check assets/board.js
```

The optional real-browser check requires Playwright in the Python environment
running it and installed Microsoft Edge. With the app running on port 8051:

```powershell
python tests/browser_check.py
```

It tests both modes, automatic computer replies, mandatory dictionary choice,
regional persistence, click/drag, keyboard placement, recall, scoring, hidden-rack
handoff, blanks, exchange and touch.
Screenshots are stored in ignored `artifacts/`.

## Plotly Cloud

```powershell
.\.venv\Scripts\python scripts/prepare_cloud.py
```

Upload the contents of `deploy/plotly-cloud/`, keeping `wordgame/`, `assets/`
and `data/` as folders. Select **app.py** as the main file and Python 3.11.
The root entry point explicitly constructs `app = Dash(...)` for discovery.
The dictionary files and their copyright notice must travel with the app.
Cloud hosting itself has not been verified here.

## NPC computer opponent

The computer adapts the chess project's categorical probabilistic circuits and
conditional neural routing; it does not import chess code or chess weights.
Three experts specialise in scoring, rack balance and defence. A tanh neural
gate combines their posteriors using entropy, margin, strong/weak quality mass
and disagreement, following the same pattern as the chess adaptation.

Move generation is independent of that model. A cached dictionary trie searches
horizontal and vertical words through existing tiles, accounts for blank-letter
assignments, and checks perpendicular words. Candidates are scored by the same
`rules.evaluate` function as human plays. The chosen move is committed using
the same turn/refill/end-game rules. If no candidate is found, the computer
exchanges its rack when permitted, otherwise passes.

The default search is bounded to 100,000 trie nodes or 3,000 legal candidates
for responsiveness. It can stop before discovering every possible move; a
no-candidate result is not a proof that no legal play exists. Computer decisions
use only its own rack, board, dictionary and bag size, never the opponent's rack
or the bag's contents/order. A busy indicator is shown while the callback runs.

Six categorical concepts describe each move: score bucket, retained rack quality,
tiles used, blanks used, nearby exposed word-premium squares and bag phase.
The final ranking includes actual score, a bounded NPC quality term, rack quality
and a board-exposure penalty. The UI's **Computer decision** section reports the
latest move and routing weights. It does not report probabilities of winning.

### Bundled bootstrap model and retraining

`models/scrabble-npc.npz` is ready to use. It was fitted on 12,000 unique synthetic
concept combinations labelled by an explicit score/rack/defence heuristic.
This is a working bootstrap, **not a model trained on expert Scrabble games or
measured wins**. Some sampled concept combinations may not correspond to reachable
board positions. No competitive playing-strength improvement has been established.

Training splits unique concept groups 60/20/20 between experts, gate and evaluation.
The default report records seed 42 and 300 epochs. On its held-out synthetic
examples, gated NLL was about 0.419 versus uniform averaging at 0.421; these numbers
measure imitation of the heuristic, not chess or Scrabble playing strength.
The complete report is in `models/scrabble-npc.json`.

To reproduce or change the bootstrap model:

```powershell
.\.venv\Scripts\python -m wordgame.train_ai --samples 12000 --epochs 300
```

To train from labelled candidate-quality judgments instead, supply JSONL:

```json
{"concepts": [4, 3, 5, 0, 1, 0], "quality": 2}
```

Concept categories have sizes `[9, 5, 8, 3, 5, 3]` in the order listed above.
Quality labels are `0` (weak), `1` (balanced), `2` (strong). Supply at least 30
distinct concept vectors, ideally a large and independently judged dataset.
Identical vectors are kept in the same data partition.

```powershell
.\.venv\Scripts\python -m wordgame.train_ai --data candidate-quality.jsonl --output models/custom.npz
$env:SCRABBLE_NPC_MODEL = 'models/custom.npz'
.\.venv\Scripts\python app.py
```

Restart the app after replacing a model; loaded artifacts are cached. Model
loading rejects incompatible schemas, shapes and probability tables and uses
`allow_pickle=False`. Selecting computer mode surfaces model-loading errors;
it does not silently fall back to an unrelated engine. NumPy is now a runtime
dependency, so run `python -m pip install -r requirements-dev.txt` after updating.
The Cloud preparation script includes the bundled model and report automatically.

This is an independent Scrabble-style implementation, not an official Hasbro,
Mattel, NASPA or Collins product. It intentionally omits game clocks, tournament
challenges and online multiplayer.
