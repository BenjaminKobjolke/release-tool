@echo off
cd /d %~dp0..
uv run python -m release_tool check-ftp %*
exit /b %ERRORLEVEL%
