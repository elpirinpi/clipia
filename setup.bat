@echo off
REM ClipIA - instalador para Windows 10/11
REM Instala Python 3.12 (python.org) con winget si falta, ffmpeg y Deno,
REM crea el entorno virtual .venv y luego las dependencias de Python
REM dentro de el. Ejecutar una sola vez (doble clic).
REM Usa el launcher py cuando existe, para no depender del PATH
REM (un python de MSYS2 no trae pip).
setlocal
cd /d %~dp0

echo ==================================================
echo  ClipIA - instalacion
echo ==================================================
echo.

set PY=python
py --version >nul 2>nul
if not errorlevel 1 set PY=py
py -3.12 --version >nul 2>nul
if not errorlevel 1 set PY=py -3.12
py -3.12 --version >nul 2>nul
if errorlevel 1 goto :instalar_python
echo [1/4] Python 3.12 encontrado:
py -3.12 --version
goto :paso_ffmpeg

:instalar_python
echo [1/4] Python 3.12 (python.org) no encontrado. Instalando con winget...
winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
if errorlevel 1 goto :error_python
echo.
echo Python 3.12 instalado. Windows necesita refrescar el PATH,
echo asi que cierra esta ventana y vuelve a ejecutar setup.bat
echo para terminar la instalacion.
pause
exit /b 0

:error_python
echo.
echo ERROR: no se pudo instalar Python 3.12.
echo Instalalo desde python.org marcando "Add Python to PATH"
echo y vuelve a ejecutar setup.bat.
pause
exit /b 1

:paso_ffmpeg
where ffmpeg >nul 2>nul
if errorlevel 1 goto :instalar_ffmpeg
echo [2/4] ffmpeg encontrado.
goto :paso_deno

:instalar_ffmpeg
echo.
echo [2/4] ffmpeg no encontrado. Instalando ffmpeg con winget...
winget install -e --id Gyan.FFmpeg --accept-source-agreements --accept-package-agreements
if errorlevel 1 goto :error_ffmpeg
goto :paso_deno

:error_ffmpeg
echo.
echo ERROR: no se pudo instalar ffmpeg con winget.
echo Instalalo a mano con: winget install Gyan.FFmpeg
echo y vuelve a ejecutar setup.bat.
pause
exit /b 1

:paso_deno
where deno >nul 2>nul
if errorlevel 1 goto :instalar_deno
echo [2b/4] Deno encontrado.
goto :paso_venv

:instalar_deno
echo.
echo [2b/4] Deno no encontrado. Instalando Deno con winget...
echo        (lo usa yt-dlp para descargar de YouTube sin errores)
winget install -e --id DenoLand.Deno --accept-source-agreements --accept-package-agreements
if errorlevel 1 goto :error_deno
goto :paso_venv

:error_deno
echo.
echo ERROR: no se pudo instalar Deno con winget.
echo Instalalo a mano con: winget install DenoLand.Deno
echo y vuelve a ejecutar setup.bat.
pause
exit /b 1

:paso_venv
echo.
echo [3/4] Creando el entorno virtual (.venv)...
if exist ".venv\Scripts\python.exe" goto :paso_deps
%PY% -m venv .venv
if errorlevel 1 goto :error_venv
goto :paso_deps

:error_venv
echo.
echo ERROR: no se pudo crear el entorno virtual .venv.
echo Si la carpeta .venv existe, borrala y vuelve a ejecutar setup.bat.
pause
exit /b 1

:paso_deps
echo.
echo [4/4] Instalando dependencias de Python en .venv (puede tardar unos minutos)...
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto :error_deps
echo.
echo ==================================================
echo  Listo. Ejecuta run.bat para abrir ClipIA.
echo  La primera vez que analices un video, la app descarga
echo  el modelo de transcripcion (unos 150 MB).
echo ==================================================
pause
goto :eof

:error_deps
echo.
echo ERROR: no se pudieron instalar las dependencias.
echo Revisa tu conexion a internet e intentalo de nuevo.
echo Si el problema persiste, borra la carpeta .venv
echo y vuelve a ejecutar setup.bat.
pause
exit /b 1
