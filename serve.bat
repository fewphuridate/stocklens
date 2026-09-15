@echo off
rem StockLens - open the website at http://localhost:8000
rem To open from a phone on the same Wi-Fi: serve.bat --lan
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
start "" http://localhost:8000
python serve.py 8000 %*
