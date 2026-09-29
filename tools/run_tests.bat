@echo off
cd /d %~dp0..
uv run pytest tests -v --ignore=tests/integration
exit /b %ERRORLEVEL%
