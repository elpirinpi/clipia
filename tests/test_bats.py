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
    i_install = next(i for i, linea in enumerate(ls)
                     if "winget install" in linea
                     and "Python.Python.3.12" in linea)
    i_error = next(i for i, linea in enumerate(ls)
                   if linea.strip() == ":error_python")
    tramo = ls[i_install:i_error]
    assert any("exit /b 0" in linea for linea in tramo), \
        "setup.bat no se detiene tras instalar Python"
    assert any("vuelve a ejecutar setup.bat" in linea for linea in tramo), \
        "falta el mensaje de volver a ejecutar setup.bat"
    assert not any("goto :paso_ffmpeg" in linea for linea in tramo), \
        "setup.bat sigue al paso ffmpeg tras instalar Python"


def test_setup_comprueba_errorlevel_de_ffmpeg_y_deno():
    """B4: las instalaciones de ffmpeg y Deno comprueban errorlevel
    (antes fallaban en silencio y el error aparecía después como
    un falso problema de internet)."""
    ls = lineas("setup.bat")

    def siguiente_errorlevel(marca, etiqueta):
        i = next(i for i, linea in enumerate(ls) if marca in linea)
        cercanas = ls[i:i + 3]
        assert any("if errorlevel 1 goto %s" % etiqueta in linea
                   for linea in cercanas), \
            "falta el chequeo de errorlevel tras %s" % marca
        assert any(linea.strip() == etiqueta for linea in ls), \
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
    i_check = next(i for i, linea in enumerate(ls)
                   if "import customtkinter" in linea
                   and "faster_whisper" in linea)
    assert any("if errorlevel 1 goto :instalar_deps" in linea
               for linea in ls[i_check:i_check + 2]), \
        "el chequeo de dependencias no lleva a :instalar_deps"


def test_diagnostico_usa_el_mismo_interprete_que_run():
    """B6: diagnostico.bat resuelve el intérprete igual que run.bat
    (py -3.12 preferido) y usa %PY% en los chequeos, no `python` a secas
    (que puede ser el de MSYS2, sin pip)."""
    contenido = leer_bat("diagnostico.bat").decode("ascii")
    assert "set PY=py -3.12" in contenido
    assert '%PY% -c "import customtkinter' in contenido
    assert '%PY% -c "import faster_whisper' in contenido
    # Ningún chequeo de módulo con `python` a secas.
    for linea in lineas("diagnostico.bat"):
        if linea.startswith("python -c"):
            raise AssertionError(
                "diagnostico.bat usa `python` a secas: %r" % linea)


def test_diagnostico_comprueba_cv2_pil_numpy_ctranslate2_ffprobe_deno():
    """B6: diagnostico.bat comprueba cv2, PIL, numpy, ctranslate2,
    ffprobe y deno."""
    contenido = leer_bat("diagnostico.bat").decode("ascii")
    for marca in ("import cv2", "import PIL", "import numpy",
                  "import ctranslate2", "where ffprobe", "where deno"):
        assert marca in contenido, "diagnostico.bat no comprueba %s" % marca


def test_diagnostico_vuelca_a_log():
    """B6: diagnostico.bat vuelca todo a diagnostico.log además de
    mostrarlo en consola."""
    contenido = leer_bat("diagnostico.bat").decode("ascii")
    assert "diagnostico.log" in contenido
    assert 'call "%~f0" --log' in contenido
    assert 'type "%~dp0diagnostico.log"' in contenido


def test_setup_crea_venv_e_instala_dentro():
    """Fase 0 (venv): setup.bat crea .venv con `py -m venv` y las
    dependencias se instalan con el pip del venv, no el global."""
    contenido = leer_bat("setup.bat").decode("ascii")
    assert "%PY% -m venv .venv" in contenido
    assert ".venv\\Scripts\\python.exe -m pip install -r requirements.txt" \
        in contenido
    # El paso del venv va antes que el de dependencias.
    assert contenido.index(":paso_venv") < contenido.index(":paso_deps")
    # La creación del venv comprueba errorlevel y tiene su etiqueta.
    ls = lineas("setup.bat")
    i_venv = next(i for i, linea in enumerate(ls)
                  if "%PY% -m venv .venv" in linea)
    assert any("if errorlevel 1 goto :error_venv" in linea
               for linea in ls[i_venv:i_venv + 2])
    assert any(linea.strip() == ":error_venv" for linea in ls)


def test_run_prefiere_venv():
    """Fase 0 (venv): run.bat usa .venv si existe y solo si no existe
    cae al Python global."""
    contenido = leer_bat("run.bat").decode("ascii")
    assert 'if exist ".venv\\Scripts\\python.exe" goto :usar_venv' \
        in contenido
    assert "set PY=.venv\\Scripts\\python.exe" in contenido
    # La comprobación del venv va antes que la resolución global.
    assert contenido.index('if exist ".venv') < contenido.index(
        "set PY=python")


def test_diagnostico_prefiere_venv():
    """Fase 0 (venv): diagnostico.bat usa el mismo intérprete que
    run.bat: el venv si existe."""
    contenido = leer_bat("diagnostico.bat").decode("ascii")
    assert 'if exist ".venv\\Scripts\\python.exe" goto :usar_venv' \
        in contenido
    assert "set PY=.venv\\Scripts\\python.exe" in contenido
    assert ".venv" in contenido.split("--- venv propio")[1]
