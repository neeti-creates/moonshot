#!/bin/bash
# Daily discussion poster — runs discussion_seed.py with the project venv.
cd /Users/neetipatel/moonshothunt
exec env -u PYTHONPATH DATA_DIR=data /Users/neetipatel/moonshothunt/.venv/bin/python /Users/neetipatel/moonshothunt/discussion_seed.py
