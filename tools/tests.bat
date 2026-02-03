@echo off
cd /d %~dp0..
uv run pytest -v
