@echo off
setlocal
rem ---------------------------------------------------------------------------
rem  SWATprep installer for Windows. Double-click to install or update to the
rem  latest release. To install a given release:  install.bat v0.3.0
rem  Needs internet. No Docker, no admin rights.
rem ---------------------------------------------------------------------------
set "REPO=wosonday/swat-preprocessing"
if not defined SWATPREP_RELEASES_API set "SWATPREP_RELEASES_API=https://api.github.com/repos/%REPO%/releases/latest"

set "VERSION=%~1"
if defined VERSION goto :have_version
echo Looking up the latest release...
for /f "usebackq delims=" %%T in (`powershell -NoProfile -Command "[Net.ServicePointManager]::SecurityProtocol = 'Tls12'; Invoke-RestMethod -Uri '%SWATPREP_RELEASES_API%' | Select-Object -ExpandProperty tag_name"`) do set "VERSION=%%T"
if not defined VERSION goto :noversion
:have_version
if not defined SWATPREP_SOURCE set "SWATPREP_SOURCE=swatprep[geo,app] @ https://github.com/%REPO%/archive/refs/tags/%VERSION%.zip"
if defined SWATPREP_DRY_RUN (
    echo Would install %VERSION% from: %SWATPREP_SOURCE%
    exit /b 0
)

where uv >nul 2>nul
if errorlevel 1 (
    echo Installing uv...
    powershell -NoProfile -ExecutionPolicy ByPass -Command "irm https://astral.sh/uv/install.ps1 | iex" || goto :fail
    set "PATH=%USERPROFILE%\.local\bin;%PATH%"
)

echo Installing SWATprep %VERSION%. This can take a few minutes the first time...
uv tool install --python 3.12 --force "%SWATPREP_SOURCE%" || goto :fail

for /f "usebackq delims=" %%B in (`uv tool dir --bin`) do set "BIN=%%B"
for /f "usebackq delims=" %%T in (`uv tool dir`) do set "TOOLS=%%T"
powershell -NoProfile -Command "$s = (New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop') + '\SWATprep.lnk'); $s.TargetPath = '%BIN%\swatprep-ui.exe'; $s.WorkingDirectory = $env:USERPROFILE; $s.Description = 'SWATprep web app'; $ico = '%TOOLS%\swatprep\Lib\site-packages\app\assets\icon.ico'; if (Test-Path $ico) { $s.IconLocation = $ico }; $s.Save()" || goto :fail

echo.
echo Done: SWATprep %VERSION%. Double-click "SWATprep" on your Desktop to start.
echo Closing the black window stops the app.
pause
exit /b 0

:noversion
echo.
echo Could not find the latest release (no internet, or GitHub is busy).
echo Try again later, or run:  install.bat v0.3.0
pause
exit /b 1

:fail
echo.
echo Installation failed. Send a screenshot of this window to the SWATprep maintainer.
pause
exit /b 1
