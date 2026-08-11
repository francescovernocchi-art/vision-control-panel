@echo off
cd /d "C:\Users\vertigo\EniUltra\vis-ion"
echo Avvio VIS•ION...
".venv\Scripts\pythonw.exe" app.py
if errorlevel 1 (
  echo Fallback console...
  ".venv\Scripts\python.exe" app.py
  echo EXIT=%ERRORLEVEL%
  pause
)
