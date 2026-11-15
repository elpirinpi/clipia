# -*- coding: utf-8 -*-
"""Configuración común de pytest: la raíz del repo queda en sys.path."""
import os
import subprocess
import sys
import tempfile

import pytest

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def app(tmp_path, monkeypatch):
    """App real con HOME y temp temporales (no toca al usuario).

    Necesita pantalla: en Linux correr con xvfb-run -a."""
    import main as app_mod

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    # tempfile cachea el directorio temporal: forzarlo aquí para que
    # los mkdtemp de la app caigan en tmp_path.
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    aplicacion = app_mod.AppClipIA()
    aplicacion.withdraw()
    aplicacion.carpeta_salida = str(tmp_path / "salida")
    os.makedirs(aplicacion.carpeta_salida, exist_ok=True)
    yield aplicacion
    try:
        aplicacion.destroy()
    except Exception:
        pass


def video_sintetico(ruta, duracion=5.0, audio=True):
    """Genera un video sintético (testsrc + tono de 440 Hz) con ffmpeg."""
    comando = ["ffmpeg", "-y", "-v", "error",
               "-f", "lavfi", "-i",
               "testsrc=duration=%.1f:size=640x360:rate=30" % duracion]
    if audio:
        comando += ["-f", "lavfi", "-i",
                    "sine=frequency=440:duration=%.1f" % duracion]
        comando += ["-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-shortest"]
    else:
        comando += ["-c:v", "libx264", "-pix_fmt", "yuv420p"]
    comando.append(str(ruta))
    subprocess.run(comando, check=True, timeout=120)
    return str(ruta)
