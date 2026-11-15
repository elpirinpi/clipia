# -*- coding: utf-8 -*-
"""Tests estáticos de los .bat (B4, B5, B6).

Los .bat no se pueden ejecutar en este Linux: se verifica su contenido
(marcas clave, finales CRLF y estructura goto + if errorlevel).
"""
import os

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def leer_bat(nombre):
    with open(os.path.join(RAIZ, nombre), "rb") as f:
        return f.read()


def lineas(nombre):
    return leer_bat(nombre).decode("ascii").split("\r\n")


def test_todos_los_bat_son_crlf():
    """Los .bat deben tener finales CRLF (cmd se rompe con LF solo)."""
    for nombre in ("setup.bat", "run.bat", "diagnostico.bat"):
        contenido = leer_bat(nombre)
        sin_crlf = contenido.replace(b"\r\n", b"")
        assert b"\n" not in sin_crlf, "%s tiene LF sin CR" % nombre
        assert b"\r" not in sin_crlf, "%s tiene CR sin LF" % nombre


def test_setup_se_detiene_tras_instalar_python():
    """B4: tras instalar Python con winget, setup.bat NO sigue en la
    misma sesión (PATH sin refrescar); corta diciendo que se vuelva a
    ejecutar setup.bat."""
    ls = lineas("setup.bat")
    i_install = next(i for i, l in enumerate(ls)
                     if "winget install" in l and "Python.Python.3.12" in l)
    i_error = next(i for i, l in enumerate(ls)
                   if l.strip() == ":error_python")
    tramo = ls[i_install:i_error]
    assert any("exit /b 0" in l for l in tramo), \
        "setup.bat no se detiene tras instalar Python"
    assert any("vuelve a ejecutar setup.bat" in l for l in tramo), \
        "falta el mensaje de volver a ejecutar setup.bat"
    assert not any("goto :paso_ffmpeg" in l for l in tramo), \
        "setup.bat sigue al paso ffmpeg tras instalar Python"


def test_setup_comprueba_errorlevel_de_ffmpeg_y_deno():
    """B4: las instalaciones de ffmpeg y Deno comprueban errorlevel
    (antes fallaban en silencio y el error aparecía después como
    un falso problema de internet)."""
    ls = lineas("setup.bat")

    def siguiente_errorlevel(marca, etiqueta):
        i = next(i for i, l in enumerate(ls) if marca in l)
        cercanas = ls[i:i + 3]
        assert any("if errorlevel 1 goto %s" % etiqueta in l
                   for l in cercanas), \
            "falta el chequeo de errorlevel tras %s" % marca
        assert any(l.strip() == etiqueta for l in ls), \
            "falta la etiqueta %s" % etiqueta

    siguiente_errorlevel("Gyan.FFmpeg", ":error_ffmpeg")
    siguiente_errorlevel("DenoLand.Deno", ":error_deno")


def test_run_verifica_todas_las_dependencias():
    """B5: run.bat verifica customtkinter, faster_whisper, cv2, PIL,
    numpy y yt_dlp (antes solo customtkinter y la app se cerraba
    después al faltar otra)."""
    contenido = leer_bat("run.bat").decode("ascii")
    for modulo in ("customtkinter", "faster_whisper", "cv2", "PIL",
                   "numpy", "yt_dlp"):
        assert modulo in contenido, \
            "run.bat no verifica %s" % modulo
    # El chequeo debe ir a instalar las dependencias si falta alguna.
    ls = lineas("run.bat")
    i_check = next(i for i, l in enumerate(ls)
                   if "import customtkinter" in l and "faster_whisper" in l)
    assert any("if errorlevel 1 goto :instalar_deps" in l
               for l in ls[i_check:i_check + 2]), \
        "el chequeo de dependencias no lleva a :instalar_deps"
