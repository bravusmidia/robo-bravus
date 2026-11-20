@echo off
cd /d "%~dp0"
where pyw >nul 2>nul
if not errorlevel 1 (
  start "" pyw -3 "%~dp0robo_bravus.pyw"
) else (
  start "" pythonw "%~dp0robo_bravus.pyw"
)
