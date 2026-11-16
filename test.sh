#!/bin/sh
# this_file: test.sh
set -eu
cd "$(dirname "$0")"
uv run --extra test python -m pytest -q
