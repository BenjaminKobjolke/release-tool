@echo off
setlocal
REM One-command release launcher. Lives in a project's tools\ folder next to
REM release_create.ini. cd into the release-tool repo so `uv run` resolves its
REM venv (release-tool is not on PATH), then point create back at this project.
REM %* passes --internal / --dry-run straight through.
cd /d D:\GIT\BenjaminKobjolke\release-tool
call uv run python -m release_tool create "%~dp0release_create.ini" --project-root "%~dp0.." %*
set "RELEASE_EXIT_CODE=%ERRORLEVEL%"
cd /d "%~dp0"
endlocal & exit /b %RELEASE_EXIT_CODE%
