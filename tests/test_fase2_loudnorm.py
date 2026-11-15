"""Fase 2: audio normalizado a -14 LUFS en export (una pasada)."""
import json
import subprocess

import pytest
from conftest import video_sintetico

from clipia.exportacion import FILTRO_LOUDNORM, exportar_clip
from clipia.utilidades import tiene_audio


def _video_con_audio_bajo(ruta, duracion=5.0, volumen=0.1):
    """Video sintético con un tono bajo (mide ~-42 LUFS)."""
    comando = ["ffmpeg", "-y", "-v", "error",
               "-f", "lavfi", "-i",
               "testsrc=duration=%.1f:size=640x360:rate=30" % duracion,
               "-f", "lavfi", "-i",
               "sine=frequency=440:duration=%.1f" % duracion,
               "-af", "volume=%.2f" % volumen,
               "-c:v", "libx264", "-pix_fmt", "yuv420p",
               "-c:a", "aac", "-shortest", str(ruta)]
    subprocess.run(comando, check=True, timeout=120)
    return str(ruta)


def _medir_lufs(ruta):
    """Volumen integrado (LUFS) de un archivo, con loudnorm en modo
    medida."""
    resultado = subprocess.run(
        ["ffmpeg", "-i", ruta, "-vn", "-af",
         "loudnorm=print_format=json", "-f", "null", "-"],
        capture_output=True, text=True, timeout=120)
    texto = resultado.stderr
    inicio = texto.find("{")
    fin = texto.rfind("}")
    assert inicio >= 0 and fin > inicio, "loudnorm no imprimió el JSON"
    return float(json.loads(texto[inicio:fin + 1])["input_i"])


def test_filtro_loudnorm_es_una_pasada_a_menos_14():
    assert "I=-14" in FILTRO_LOUDNORM
    assert "linear=true" in FILTRO_LOUDNORM


def test_tiene_audio(tmp_path):
    video = _video_con_audio_bajo(tmp_path / "bajo.mp4")
    assert tiene_audio(video) is True


def test_tiene_audio_sin_audio(tmp_path):
    video = video_sintetico(tmp_path / "sin_audio.mp4", duracion=5.0,
                            audio=False)
    assert tiene_audio(video) is False


def test_export_normaliza_a_menos_14_lufs(tmp_path):
    video = _video_con_audio_bajo(tmp_path / "bajo.mp4")
    assert _medir_lufs(video) < -30  # la entrada es muy baja
    salida = str(tmp_path / "clip.mp4")
    exportar_clip(video, 0.0, 5.0, None, salida, con_subtitulos=False)
    medido = _medir_lufs(salida)
    assert medido == pytest.approx(-14.0, abs=1.5)


def test_export_sin_audio_no_falla(tmp_path):
    video = video_sintetico(tmp_path / "sin_audio.mp4", duracion=5.0,
                            audio=False)
    salida = str(tmp_path / "clip.mp4")
    exportar_clip(video, 0.0, 5.0, None, salida, con_subtitulos=False)
    resultado = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a",
         "-show_entries", "stream=index", "-of", "csv=p=0", salida],
        capture_output=True, text=True, timeout=60)
    assert resultado.stdout.strip() == ""


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
