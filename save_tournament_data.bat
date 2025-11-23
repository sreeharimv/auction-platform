@echo off
REM Helper script to save tournament data to git
REM Run this after making changes to preserve data across deployments

echo.
echo Saving tournament data to git...
echo.

REM Add database and config
git add players.db config.json

REM Check if there are changes
git diff --staged --quiet
if %errorlevel% equ 0 (
    echo No changes to save - data is already up to date
    goto :end
)

echo Changes detected:
git diff --staged --name-only
echo.

REM Prompt for commit message
set /p message="Enter commit message (or press Enter for default): "

if "%message%"=="" (
    for /f "tokens=1-3 delims=/ " %%a in ('date /t') do set mydate=%%c-%%a-%%b
    for /f "tokens=1-2 delims=: " %%a in ('time /t') do set mytime=%%a:%%b
    set message=Update tournament data - %mydate% %mytime%
)

REM Commit
git commit -m "%message%"

echo.
set /p push_confirm="Push to remote? (y/n): "

if /i "%push_confirm%"=="y" (
    git push
    echo.
    echo Tournament data saved and pushed!
    echo Your next deployment will use this data
) else (
    echo.
    echo Tournament data committed locally
    echo Remember to run 'git push' to deploy changes
)

:end
echo.
echo Tip: Run this script after:
echo    - Adding/editing players
echo    - Changing tournament settings
echo    - Completing an auction
echo.
pause
