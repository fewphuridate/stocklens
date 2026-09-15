@echo off
rem StockLens - daily data update (about 3-5 minutes).
rem Add --ai to summarize news with Claude (requires ANTHROPIC_API_KEY).
rem Log file: logs\update.log
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
if not exist logs mkdir logs
echo [%date% %time%] start >> "logs\update.log"
python -m pipeline.build %* >> "logs\update.log" 2>&1
if errorlevel 1 (
  echo Update FAILED - see logs\update.log
  exit /b 1
)
echo Update finished OK.
