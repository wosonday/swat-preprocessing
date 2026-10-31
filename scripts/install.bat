@echo off
setlocal
rem ---------------------------------------------------------------------------
rem  SWATprep installer for Windows. Double-click to install; run again to update.
rem  Needs internet the first time. No Docker, no admin rights.
rem ---------------------------------------------------------------------------
set "VERSION=v0.3.0"
if not defined SWATPREP_SOURCE set "SWATPREP_SOURCE=swatprep[geo,app] @ https://github.com/wosonday/swat-preprocessing/archive/refs/tags/%VERSION%.zip"

where uv >nul 2>nul
if errorlevel 1 (
    echo Installing uv...
    powershell -NoProfile -ExecutionPolicy ByPass -Command "irm https://astral.sh/uv/install.ps1 | iex" || goto :fail
    set "PATH=%USERPROFILE%\.local\bin;%PATH%"
)

echo Installing SWATprep %VERSION%. This can take a few minutes the first time...
uv tool install --python 3.12 --force "%SWATPREP_SOURCE%" || goto :fail

for /f "usebackq delims=" %%B in (`uv tool dir --bin`) do set "BIN=%%B"
powershell -NoProfile -Command "$s = (New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop') + '\SWATprep.lnk'); $s.TargetPath = '%BIN%\swatprep-ui.exe'; $s.WorkingDirectory = $env:USERPROFILE; $s.Description = 'SWATprep web app'; $s.Save()" || goto :fail

echo.
echo Done. Double-click "SWATprep" on your Desktop to start.
echo Closing the black window stops the app.
pause
exit /b 0

:fail
echo.
echo Installation failed. Send a screenshot of this window to the SWATprep maintainer.
pause
exit /b 1
