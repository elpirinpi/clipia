@echo off
REM ClipIA - instalador para Windows 10/11
REM Instala Python 3.11 y ffmpeg con winget si faltan, y luego las
REM dependencias de Python. Ejecutar una sola vez (doble clic).
setlocal
cd /d %~dp0

echo ==================================================
echo  ClipIA - instalacion
echo ==================================================
echo.

where python >nul 2>nul
if errorlevel 1 goto :instalar_python
echo [1/3] Python encontrado:
python --version
goto :paso_ffmpeg

:instalar_python
echo [1/3] Python no encontrado. Instalando Python 3.11 con winget...
winget install -e --id Python.Python.3.11 --accept-source-agreements --accept-package-agreements
echo.
echo Si Python se acaba de instalar, cierra esta ventana y vuelve
echo a ejecutar setup.bat para continuar con el paso 2.
pause
exit /b 0

:paso_ffmpeg
where ffmpeg >nul 2>nul
if errorlevel 1 goto :instalar_ffmpeg
echo [2/3] ffmpeg encontrado.
goto :paso_deno

:instalar_ffmpeg
echo.
echo [2/3] ffmpeg no encontrado. Instalando ffmpeg con winget...
winget install -e --id Gyan.FFmpeg --accept-source-agreements --accept-package-agreements
goto :paso_deno

:paso_deno
where deno >nul 2>nul
if errorlevel 1 goto :instalar_deno
echo [2b/3] Deno encontrado.
goto :paso_deps

:instalar_deno
echo.
echo [2b/3] Deno no encontrado. Instalando Deno con winget...
echo        (lo usa yt-dlp para descargar de YouTube sin errores)
winget install -e --id DenoLand.Deno --accept-source-agreements --accept-package-agreements
goto :paso_deps

:paso_deps
echo.
echo [3/3] Instalando dependencias de Python (puede tardar unos minutos)...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
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
pause
exit /b 1
