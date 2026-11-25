#!/bin/sh
cd "$(dirname "$0")"
python3 -m pip install -q -r requirements.txt
[ -f static/index.html ] || python3 make_static.py
python3 app.py
