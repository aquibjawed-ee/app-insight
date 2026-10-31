"""Makes the analysis engine importable. The engine (engine/scripts) uses flat imports, so its folder goes on sys.path."""
import os
import sys

ENGINE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "engine", "scripts")
if ENGINE not in sys.path:
    sys.path.insert(0, ENGINE)
