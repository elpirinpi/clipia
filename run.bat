@echo off
REM ClipIA - lanzador (doble clic para abrir la app)
REM Si faltan las dependencias, las instala solo antes de abrir la app.
cd /d %~dp0
echo Iniciando ClipIA...
where python >nul 2>nul
if errorlevel 1 goto :sin_python
python -c "import customtkinter" >nul 2>nul
if errorlevel 1 goto :instalar_deps
goto :abrir
:instalar_deps
echo Faltan las dependencias de ClipIA. Instalando, por favor espera...
python -m pip install -r requirements.txt
if errorlevel 1 goto :error_deps
goto :abrir
:sin_python
echo.
echo ERROR: no se encontro Python. Ejecuta setup.bat para instalarlo.
pause
exit /b 1
:error_deps
echo.
echo ERROR: no se pudieron instalar las dependencias.
echo Revisa tu conexion a internet e intentalo de nuevo,
echo o ejecuta setup.bat para instalar todo paso a paso.
pause
exit /b 1
:abrir
echo Abriendo ClipIA...
python main.py
if errorlevel 1 goto :error_app
goto :eof
:error_app
echo.
echo La app se cerro con un error. Si es la primera vez, ejecuta
echo setup.bat para instalar las dependencias.
pause
