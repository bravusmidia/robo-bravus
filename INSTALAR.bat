@echo off
title Instalador - Robo Bravus (Bravus Midia)
cd /d "%~dp0"
echo.
echo  ==============================================
echo     ROBO BRAVUS - Assistente da Bravus Midia
echo  ==============================================
echo.

set "PY="
where py >nul 2>nul
if not errorlevel 1 set "PY=py -3"
if not defined PY (
  where python >nul 2>nul
  if not errorlevel 1 set "PY=python"
)
if not defined PY goto nopython
%PY% -c "import sys; sys.exit(0 if sys.version_info>=(3,9) else 1)" >nul 2>nul
if errorlevel 1 goto nopython

echo  [1/3] Instalando componentes (pode levar alguns minutos)...
%PY% -m pip install --upgrade pip --quiet
%PY% -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo  ERRO ao instalar os componentes. Verifique sua internet e rode de novo.
  pause
  exit /b 1
)

echo.
echo  [2/3] Configurando...
choice /c SN /m "  Deseja que o robo inicie junto com o Windows"
if errorlevel 2 (set "AUTO=") else (set "AUTO=--autostart")

echo.
echo  [3/3] Criando atalho e iniciando o robo...
%PY% "%~dp0robo_bravus.pyw" --instalar %AUTO%

echo.
echo  PRONTO! O Robo Bravus esta na sua tela.
echo  Atalhos na Area de Trabalho: "Ligar Robo Bravus" e "Desligar Robo Bravus"
echo  Teclado: Ctrl+Alt+B ativa/desativa  -  Ctrl+Alt+F falar  -  Ctrl+Alt+M mudo
echo.
pause
exit /b 0

:nopython
echo  O Python nao foi encontrado neste computador.
echo  Vou tentar instalar automaticamente...
winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
if errorlevel 1 (
  echo.
  echo  Nao consegui instalar sozinho. Vou abrir o site do Python.
  echo  Baixe, instale e MARQUE a opcao "Add python.exe to PATH".
  start https://www.python.org/downloads/
)
echo.
echo  Depois que o Python terminar de instalar, FECHE esta janela
echo  e de dois cliques no INSTALAR.bat de novo.
pause
exit /b 1
