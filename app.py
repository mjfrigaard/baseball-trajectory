"""Deployment entry point for Posit Connect Cloud.

Connect Cloud installs only what's in ``requirements.txt`` and then imports
the file you designate as the *primary file*; it does not run
``pip install -e .`` against ``pyproject.toml``. Point Connect Cloud at
this file as the primary file. It adds ``src/`` to ``sys.path`` so the
``baseball_trajectory`` package is importable, then re-exports the Shiny
``app`` object that Connect picks up.

For local development, prefer the console script (``baseball-trajectory``)
or run ``shiny run src/baseball_trajectory/app.py``.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from baseball_trajectory.app import app  # noqa: E402, F401
