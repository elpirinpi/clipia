@echo off
REM ClipIA - diagnostico: muestra que tiene instalado el PC.
REM Si la app no abre, ejecuta este archivo y manda una foto de lo que dice
REM (o el archivo diagnostico.log que se genera junto a la app).
cd /d %~dp0
REM B6: mismo interprete que run.bat (py -3.12 preferido).
set PY=python
py --version >nul 2>nul
if not errorlevel 1 set PY=py
py -3.12 --version >nul 2>nul
if not errorlevel 1 set PY=py -3.12
if "%~1"=="--log" goto :diagnostico
echo Generando diagnostico... (el resultado queda en diagnostico.log)
call "%~f0" --log > "%~dp0diagnostico.log" 2>&1
type "%~dp0diagnostico.log"
echo.
echo Manda una foto de esta ventana (o el archivo diagnostico.log) si la app no abre.
pause
goto :eof

:diagnostico
echo ==================================================
echo  ClipIA - diagnostico
echo ==================================================
echo.
echo --- Interprete Python usado ---
echo %PY%
%PY% --version
echo.
echo --- py launcher (python.org) ---
py --version
py -3.12 --version
echo.
echo --- customtkinter ---
%PY% -c "import customtkinter; print('customtkinter OK')"
echo.
echo --- tkinter ---
%PY% -c "import tkinter; print('tkinter OK')"
echo.
echo --- faster-whisper ---
%PY% -c "import faster_whisper; print('faster-whisper OK')"
echo.
echo --- yt-dlp ---
%PY% -c "import yt_dlp; print('yt-dlp OK')"
echo.
echo --- cv2 (OpenCV) ---
%PY% -c "import cv2; print('cv2 OK', cv2.__version__)"
echo.
echo --- PIL ---
%PY% -c "import PIL; print('PIL OK', PIL.__version__)"
echo.
echo --- numpy ---
%PY% -c "import numpy; print('numpy OK', numpy.__version__)"
echo.
echo --- ctranslate2 ---
%PY% -c "import ctranslate2; print('ctranslate2 OK', ctranslate2.__version__)"
echo.
echo --- ffmpeg ---
where ffmpeg
ffmpeg -version 2>nul | findstr /C:"ffmpeg version"
echo.
echo --- ffprobe ---
where ffprobe
echo.
echo --- deno ---
where deno
deno --version 2>nul
echo.
echo --- carpeta actual ---
cd
dir
goto :eof
