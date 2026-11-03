#!/bin/sh
# Run the Ontos slice-1 demo end to end.
# Uses the project venv when present; otherwise the `ontos` on PATH.
set -e
cd "$(dirname "$0")/.."
if [ -x .venv/bin/ontos ]; then
  exec .venv/bin/ontos demo "$@"
fi
exec ontos demo "$@"
