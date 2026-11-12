@echo off
REM ClipIA - diagnostico: muestra que tiene instalado el PC.
REM Si la app no abre, ejecuta este archivo y manda una foto de lo que dice.
cd /d %~dp0
echo ==================================================
echo  ClipIA - diagnostico
echo ==================================================
echo.
echo --- Python ---
python --version
echo.
echo --- py launcher (python.org) ---
py --version
py -3.12 --version
echo.
echo --- customtkinter ---
python -c "import customtkinter; print('customtkinter OK')"
echo.
echo --- tkinter ---
python -c "import tkinter; print('tkinter OK')"
echo.
echo --- faster-whisper ---
python -c "import faster_whisper; print('faster-whisper OK')"
echo.
echo --- yt-dlp ---
python -c "import yt_dlp; print('yt-dlp OK')"
echo.
echo --- ffmpeg ---
where ffmpeg
echo.
echo --- carpeta actual ---
cd
dir
echo.
echo Manda una foto de esta ventana si la app no abre.
pause
