@echo off
REM ClipIA - lanzador (doble clic para abrir la app)
REM Si faltan las dependencias, las instala solo antes de abrir la app.
cd /d %~dp0
python -c "import customtkinter" >nul 2>nul
if %errorlevel% neq 0 (
    echo Faltan las dependencias de ClipIA. Instalando (solo la primera vez)...
    python -m pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo.
        echo ERROR: no se pudieron instalar las dependencias.
        echo Revisa tu conexion a internet e intentalo de nuevo,
        echo o ejecuta setup.bat para instalar todo paso a paso.
        pause
        exit /b 1
    )
)
python main.py
if %errorlevel% neq 0 (
    echo.
    echo La app se cerro con un error. Si es la primera vez, ejecuta
    echo setup.bat para instalar las dependencias.
    pause
)
