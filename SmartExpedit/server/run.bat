@echo off
cd /d "%~dp0"
echo Installing what SmartExpedit needs (first time only)...
py -m pip install --disable-pip-version-check -q -r requirements.txt
if not exist static\index.html py make_static.py
echo.
echo Open http://localhost:8080 in your browser. Keep this window open while SmartExpedit is in use.
py app.py
pause
