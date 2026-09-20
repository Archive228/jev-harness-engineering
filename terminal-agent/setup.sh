#!/bin/sh
set -eu
JEV_SETUP_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$JEV_SETUP_ROOT"
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
printf '%s\n' 'Готово. ./jev откроет пустой чат; --doctor покажет готовность окружения.'
