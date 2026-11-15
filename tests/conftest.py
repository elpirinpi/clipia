# -*- coding: utf-8 -*-
"""Configuración común de pytest: la raíz del repo queda en sys.path."""
import os
import subprocess
import sys

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


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
