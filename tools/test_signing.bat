@echo off
rem Signs a copy of examples\dummy.exe with a signing profile to test the signing setup.
rem Usage: tools\test_signing.bat "<profile name>" [--verbose]
if "%~1"=="" (
    echo Usage: tools\test_signing.bat "^<profile name from signing_profiles.ini^>" [--verbose]
    exit /b 2
)
pushd "%~dp0.."
set "TEST_EXE=%TEMP%\release-tool-signing-test.exe"
copy /y examples\dummy.exe "%TEST_EXE%" >nul || (popd & exit /b 1)
uv run python -m release_tool sign "%TEST_EXE%" %*
set "RESULT=%ERRORLEVEL%"
popd
exit /b %RESULT%
