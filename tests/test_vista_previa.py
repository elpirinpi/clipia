"""Tests de la vista previa CON subtítulos (Fase 3).

La previa reutiliza la ruta de exportación a 540x960 con el mismo
recorte y el mismo .ass del clip final (libass escala el PlayRes
1080x1920 al marco de 540x960). La verificación es diferencial: el
fotograma de la previa con subtítulos tiene muchos más píxeles
blancos en la banda inferior que el mismo fotograma sin subtítulos.
"""
import subprocess
from unittest import mock

import numpy as np
from conftest import video_sintetico
from PIL import Image

import main as app_mod
from clipia_core import generar_subtitulos_ass, generar_vista_previa


def _palabras_falsas(duracion, paso=0.5):
    palabras = []
    i = 0
    while i * paso < duracion:
        palabras.append({"word": " palabra",
                         "start": i * paso, "end": i * paso + 0.4})
        i += 1
    return palabras


SEGMENTOS = [{"start": 0.0, "end": 10.0,
              "text": " ".join(p["word"] for p in
                               _palabras_falsas(10.0)),
              "words": _palabras_falsas(10.0)}]


def _extraer_fotograma(ruta_video, segundo, ruta_salida):
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-ss", "%.2f" % segundo,
         "-i", ruta_video, "-frames:v", "1", ruta_salida],
        check=True, timeout=60)
    return ruta_salida


def _pixeles_blancos_banda(ruta_fotograma):
    imagen = np.asarray(Image.open(ruta_fotograma).convert("RGB"))
    alto = imagen.shape[0]
    banda = imagen[int(alto * 0.75):int(alto * 0.95)]
    blancos = (banda[:, :, 0] > 240) & (banda[:, :, 1] > 240) \
        & (banda[:, :, 2] > 240)
    return int(blancos.sum())


def _info_video(ruta):
    salida = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "stream=width,height", "-show_entries", "format=duration",
         "-of", "csv=p=0", ruta],
        capture_output=True, text=True, timeout=60, check=True).stdout
    lineas = [ln for ln in salida.strip().splitlines() if ln]
    ancho, alto = lineas[0].split(",")
    return int(ancho), int(alto), float(lineas[1])


def test_vista_previa_con_subtitulos_los_quema(tmp_path):
    """El fotograma de la previa con ASS tiene cientos de píxeles
    blancos más en la banda inferior que la misma previa sin ASS."""
    video = video_sintetico(tmp_path / "origen.mp4", duracion=10.0)
    ruta_ass = str(tmp_path / "clip.ass")
    generar_subtitulos_ass(SEGMENTOS, 2.0, 8.0, ruta_ass)
    con = str(tmp_path / "con.mp4")
    sin = str(tmp_path / "sin.mp4")
    generar_vista_previa(video, 2.0, 8.0, con, ruta_ass=ruta_ass)
    generar_vista_previa(video, 2.0, 8.0, sin)
    ancho, alto, duracion = _info_video(con)
    assert (ancho, alto) == (540, 960)
    assert abs(duracion - 6.0) < 0.5
    foto_con = _extraer_fotograma(con, 3.0, str(tmp_path / "con.png"))
    foto_sin = _extraer_fotograma(sin, 3.0, str(tmp_path / "sin.png"))
    diferencia = (_pixeles_blancos_banda(foto_con)
                  - _pixeles_blancos_banda(foto_sin))
    assert diferencia >= 300, \
        "píxeles blancos extra: %d (se esperaban ≥300)" % diferencia


def test_vista_previa_sin_ass_sigue_funcionando(tmp_path):
    """Compatibilidad: sin ruta_ass la previa sale como antes."""
    video = video_sintetico(tmp_path / "origen.mp4", duracion=10.0)
    salida = str(tmp_path / "previa.mp4")
    assert generar_vista_previa(video, 2.0, 8.0, salida) == salida
    ancho, alto, duracion = _info_video(salida)
    assert (ancho, alto) == (540, 960)
    assert abs(duracion - 6.0) < 0.5


def test_hilo_vista_previa_pasa_el_ass(app, tmp_path):
    """La GUI genera el .ass del clip (con su estilo y margen) y se
    lo pasa a generar_vista_previa."""
    clip = {"start": 2.0, "end": 8.0, "score": 1.0, "text": "clip",
            "video": "video.mp4"}
    capturado = {}

    def falso_generar(ruta_video, inicio, fin, ruta_salida, **kwargs):
        ruta_ass = kwargs.get("ruta_ass")
        capturado["ruta_ass"] = ruta_ass
        if ruta_ass:
            with open(ruta_ass, encoding="utf-8") as archivo:
                capturado["ass"] = archivo.read()
        with open(ruta_salida, "wb") as archivo:
            archivo.write(b"fake")
        return ruta_salida

    with mock.patch.object(app_mod.core, "generar_vista_previa",
                           side_effect=falso_generar), \
            mock.patch.object(app_mod, "detectar_rostros_con_limite",
                              return_value=[]), \
            mock.patch.object(app, "_abrir_archivo"):
        app._hilo_vista_previa(clip, "video.mp4", False, SEGMENTOS)
        app._procesar_cola()
    assert capturado["ruta_ass"], "no se pasó ruta_ass a la previa"
    assert capturado["ruta_ass"].endswith(".ass")
    assert "Dialogue:" in capturado["ass"]
    assert "palabra" in capturado["ass"]
