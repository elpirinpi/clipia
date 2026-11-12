@echo off
REM ClipIA - lanzador (doble clic para abrir la app)
cd /d %~dp0
python main.py
if %errorlevel% neq 0 (
    echo.
    echo La app se cerro con un error. Si es la primera vez, ejecuta
    echo setup.bat para instalar las dependencias.
    pause
)
