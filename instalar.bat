@echo off
cd /d "%~dp0"
if not exist "venv\Scripts\python.exe" (
  echo Creando entorno virtual...
  py -3.12 -m venv venv 2>nul || python -m venv venv
)
"venv\Scripts\python.exe" -m pip install --upgrade pip
"venv\Scripts\python.exe" -m pip install -r requirements.txt
echo.
echo Listo. Para abrir la app: iniciar.bat
pause
