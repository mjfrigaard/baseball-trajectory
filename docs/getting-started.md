# Getting started

## Prerequisites

- Python 3.10 or newer.
- An internet connection (the first search downloads a season roster
  from the MLB Stats API).

## Install

Clone the repository and install in editable mode with the development
extras:

```bash
pip install -e ".[dev]"
```

## Run

Start the Shiny server:

```bash
baseball-trajectory
```

The app binds to `127.0.0.1:8000`. Open <http://127.0.0.1:8000> in a
browser.

## Your first trajectory

1. Leave **Player type** on *Batter*.
2. Type `Trout` in the **Player name** box. The dropdown populates
   with matches.
3. Pick **Mike Trout** in the dropdown.
4. Click **Search**. The plot, summary table, and season log fill in.
5. Try changing **Metric** from `OPS` to `HR` to see his home-run arc.

## Stopping the server

Press `Ctrl-C` in the terminal where `baseball-trajectory` is running.

## Next

- Read the [User guide](user-guide.md) for the full sidebar walkthrough,
  including how to look up older retired players.
- See the [Deployment](deployment.md) page if you want to host the app
  yourself (Posit Connect Cloud, Docker, etc.).
