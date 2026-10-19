@echo off
rem Instala o Ditado local: cria um Python isolado nesta pasta e baixa as bibliotecas.
rem O modelo de voz (~1,6 GB) baixa sozinho na primeira vez que o app abrir.
title Instalando o Ditado local
cd /d "%~dp0"

py -3.12 --version >nul 2>&1
if errorlevel 1 (
  echo Precisa do Python 3.12. Baixe em https://www.python.org/downloads/release/python-3126/
  echo Na instalacao, marque "Add python.exe to PATH" e deixe o "py launcher" ligado.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Criando o ambiente Python...
  py -3.12 -m venv .venv || goto erro
)
".venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
echo Instalando as bibliotecas...
".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto erro

where nvidia-smi >nul 2>&1
if not errorlevel 1 (
  echo Placa NVIDIA encontrada: instalando o CUDA, para transcrever rapido...
  ".venv\Scripts\python.exe" -m pip install -r requirements-nvidia.txt || goto erro
) else (
  echo Sem placa NVIDIA: o app vai transcrever no processador, que e mais lento.
)

echo.
echo Pronto. Agora e so abrir o iniciar.bat.
pause
exit /b 0

:erro
echo.
echo A instalacao falhou. Veja a mensagem acima.
pause
exit /b 1
