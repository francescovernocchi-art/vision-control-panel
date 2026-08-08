@echo off
REM Build EXE con PyInstaller — VIS-eniSpace-Utility.exe
REM Prerequisiti: .venv + requirements + pyinstaller

setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Ambiente virtuale non trovato. Creare prima .venv e installare i requirements.
  echo   python -m venv .venv
  echo   .venv\Scripts\activate
  echo   pip install -r requirements.txt
  echo   pip install pyinstaller
  exit /b 1
)

call .venv\Scripts\activate.bat

echo Installazione PyInstaller se necessario...
pip install pyinstaller --quiet

echo.
echo Compilazione VIS-eniSpace-Utility.exe (onefile, windowed)...
pyinstaller --noconfirm --clean ^
  --name "VIS-eniSpace-Utility" ^
  --windowed ^
  --onefile ^
  --paths "." ^
  --hidden-import=customtkinter ^
  --hidden-import=keyring.backends.Windows ^
  --hidden-import=win32timezone ^
  --hidden-import=playwright ^
  --hidden-import=playwright.sync_api ^
  --collect-all customtkinter ^
  --collect-all playwright ^
  app.py

if errorlevel 1 (
  echo Build fallita.
  exit /b 1
)

echo.
echo Build completata.
echo Eseguibile: "%~dp0dist\VIS-eniSpace-Utility.exe"
echo.
echo NOTA Playwright: l'EXE usa Google Chrome installato sul PC (channel=chrome).
echo Non serve "playwright install chromium". Serve Chrome sul sistema.
echo Database e log vengono creati accanto all'EXE (cartelle data\ e logs\).
endlocal
