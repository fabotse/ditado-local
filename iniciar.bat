@echo off
rem Ditado local: segure o Alt da direita, fale e solte. Feche esta janela para sair.
title Ditado local
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Primeiro rode o instalar.bat.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" "%~dp0app\main.py" %*
if errorlevel 1 pause
