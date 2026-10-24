# Scrabble NPC bootstrap artifact

`scrabble-npc.npz` contains categorical sum/product circuit parameters and a
trained neural conditional gate. It is independent of the chess artifact.
`scrabble-npc.json` records provenance, seed, epochs, split and held-out metrics.

Reproduce from the repository root:

```powershell
.\.venv\Scripts\python -m wordgame.train_ai --samples 12000 --epochs 300
```

The training labels are synthetic heuristic quality judgments, not real games
or measured wins. See the main README for concepts, ranking, limits and the
optional labelled-JSONL training path. Keep the NPZ and report together when
distributing the bundled model. This artifact is intentionally tracked so
computer play works without a separate training step.
