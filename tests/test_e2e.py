"""Prueba e2e con un video sintético de ffmpeg: transcribir, detectar
momentos, generar subtítulos y exportar un clip vertical."""
import json
import os
import subprocess

from conftest import video_sintetico

from clipia_core import (
    detectar_momentos,
    exportar_clip,
    generar_subtitulos_ass,
    transcribir,
)


def _palabras_falsas(duracion, paso=0.5):
    """Palabras sintéticas cubriendo todo el video (el tono de prueba
    no tiene habla, así que los momentos se detectan sobre estas)."""
    palabras = []
    i = 0
    while i * paso < duracion:
        palabras.append({"word": " palabra",
                         "start": i * paso, "end": i * paso + 0.4})
        i += 1
    return palabras


def _info_video(ruta):
    salida = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format",
         "-of", "json", ruta],
        capture_output=True, text=True, timeout=60, check=True).stdout
    return json.loads(salida)


def test_pipeline_completo_video_sintetico(tmp_path):
    video = video_sintetico(tmp_path / "origen.mp4", duracion=30.0)

    # 1. Transcribir: el tono puro no tiene habla, pero la llamada
    # debe completarse y devolver una lista.
    segmentos_reales = transcribir(video)
    assert isinstance(segmentos_reales, list)

    # 2. Momentos sobre segmentos sintéticos con palabras.
    palabras = _palabras_falsas(30.0)
    segmentos = [{"start": 0.0, "end": 30.0,
                 "text": " ".join(p["word"] for p in palabras),
                 "words": palabras}]
    candidatos = detectar_momentos(segmentos, 30.0)
    assert candidatos, "no se detectó ningún momento"
    clip = candidatos[0]
    assert 0.0 <= clip["start"] < clip["end"] <= 30.0

    # 3. Subtítulos y exportación del clip.
    ruta_ass = str(tmp_path / "clip.ass")
    assert generar_subtitulos_ass(segmentos, clip["start"], clip["end"],
                                  ruta_ass) == ruta_ass
    with open(ruta_ass, encoding="utf-8") as f:
        assert "Dialogue:" in f.read()
    salida = tmp_path / "clip.mp4"
    assert exportar_clip(video, clip["start"], clip["end"],
                         ruta_ass, str(salida)) == str(salida)
    assert os.path.exists(salida)

    # 4. Verificación del clip exportado.
    info = _info_video(str(salida))
    duracion = float(info["format"]["duration"])
    pedida = clip["end"] - clip["start"]
    assert abs(duracion - pedida) <= 0.5, \
        "duración real %.2f s, pedida %.2f s" % (duracion, pedida)
    flujos = {f["codec_type"]: f for f in info["streams"]}
    assert flujos["video"]["width"] == 1080
    assert flujos["video"]["height"] == 1920
    assert flujos["audio"]["codec_name"] == "aac"
