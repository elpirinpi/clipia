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
if %errorlevel% neq 0 (
    echo [1/3] Python no encontrado. Instalando Python 3.11 con winget...
    winget install -e --id Python.Python.3.11 --accept-source-agreements --accept-package-agreements
    echo.
    echo Si Python se acaba de instalar, cierra esta ventana y vuelve
    echo a ejecutar setup.bat para continuar con el paso 2.
    pause
    exit /b 0
) else (
    echo [1/3] Python encontrado:
    python --version
)

where ffmpeg >nul 2>nul
if %errorlevel% neq 0 (
    echo.
    echo [2/3] ffmpeg no encontrado. Instalando ffmpeg con winget...
    winget install -e --id Gyan.FFmpeg --accept-source-agreements --accept-package-agreements
) else (
    echo [2/3] ffmpeg encontrado.
)

where deno >nul 2>nul
if %errorlevel% neq 0 (
    echo.
    echo [2b/3] Deno no encontrado. Instalando Deno con winget...
    echo        (lo usa yt-dlp para descargar de YouTube sin errores)
    winget install -e --id DenoLand.Deno --accept-source-agreements --accept-package-agreements
) else (
    echo [2b/3] Deno encontrado.
)

echo.
echo [3/3] Instalando dependencias de Python (puede tardar unos minutos)...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo.
    echo ERROR: no se pudieron instalar las dependencias.
    echo Revisa tu conexion a internet e intentalo de nuevo.
    pause
    exit /b 1
)

echo.
echo ==================================================
echo  Listo. Ejecuta run.bat para abrir ClipIA.
echo  La primera vez que analices un video, la app descarga
echo  el modelo de transcripcion (unos 150 MB).
echo ==================================================
pause
