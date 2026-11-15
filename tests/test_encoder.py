"""Tests del codificador por hardware (Fase 1)."""
import json
import subprocess

import pytest
from conftest import video_sintetico

import clipia_core as core
from clipia import encoder as enc


@pytest.fixture(autouse=True)
def sin_cache():
    enc.limpiar_cache_deteccion()
    yield
    enc.limpiar_cache_deteccion()


def test_opciones_libx264():
    assert enc.opciones_encoder("libx264") == [
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23"]


def test_opciones_nvenc():
    assert enc.opciones_encoder("h264_nvenc") == [
        "-c:v", "h264_nvenc", "-preset", "p4", "-cq", "23"]


def test_opciones_qsv_y_amf():
    assert enc.opciones_encoder("h264_qsv")[:2] == ["-c:v", "h264_qsv"]
    assert enc.opciones_encoder("h264_amf")[:2] == ["-c:v", "h264_amf"]


def test_opciones_desconocido_lanza_error():
    with pytest.raises(ValueError):
        enc.opciones_encoder("h264_inexistente")


def test_descripcion_encoder():
    assert enc.descripcion_encoder("h264_nvenc") == "NVENC (GPU NVIDIA)"
    assert enc.descripcion_encoder("libx264") == "libx264 (CPU)"
    assert enc.descripcion_encoder("otro") == "otro"


def test_detectar_sin_hardware_cae_a_libx264(monkeypatch):
    monkeypatch.setattr(enc, "_probar_encoder", lambda e: False)
    assert enc.detectar_encoder("auto") == "libx264"


def test_detectar_encuentra_nvenc(monkeypatch):
    monkeypatch.setattr(enc, "_probar_encoder",
                        lambda e: e == "h264_nvenc")
    assert enc.detectar_encoder("auto") == "h264_nvenc"


def test_preferencia_que_falla_cae_a_cpu(monkeypatch):
    """Una preferencia manual que no funciona no rompe la exportación:
    se cae a libx264."""
    monkeypatch.setattr(enc, "_probar_encoder", lambda e: False)
    assert enc.detectar_encoder("h264_nvenc") == "libx264"


def test_preferencia_respetada_si_funciona(monkeypatch):
    """Si el usuario eligió QSV y funciona, se usa QSV aunque NVENC
    también esté disponible."""
    monkeypatch.setattr(enc, "_probar_encoder", lambda e: True)
    assert enc.detectar_encoder("h264_qsv") == "h264_qsv"


def test_detectar_cachea_el_resultado(monkeypatch):
    llamadas = []
    monkeypatch.setattr(enc, "_probar_encoder",
                        lambda e: llamadas.append(e) or False)
    assert enc.detectar_encoder("auto") == "libx264"
    assert enc.detectar_encoder("auto") == "libx264"
    assert len(llamadas) == 3, "debió probar 3 codificadores una sola vez"


def test_probar_libx264_real():
    """La prueba de 1 s con libx264 funciona de verdad (ffmpeg real)."""
    assert enc._probar_encoder("libx264") is True


def test_probar_inexistente_es_falso():
    assert enc._probar_encoder("h264_inexistente") is False


def flujos(ruta):
    resultado = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "stream=codec_type,codec_name", "-of", "json", ruta],
        capture_output=True, text=True, check=True, timeout=60)
    return [(s["codec_type"], s["codec_name"])
            for s in json.loads(resultado.stdout)["streams"]]


def test_exportar_con_encoder_explicito(tmp_path):
    video = video_sintetico(tmp_path / "video.mp4", duracion=5.0)
    salida = str(tmp_path / "clip.mp4")
    core.exportar_clip(video, 0, 5, None, salida, con_subtitulos=False,
                       encoder="libx264")
    assert ("video", "h264") in flujos(salida)
    assert ("audio", "aac") in flujos(salida)


def test_exportar_auto_en_este_servidor_usa_cpu(tmp_path):
    """Sin GPU, la autodetección cae a libx264 y el clip sale válido."""
    assert enc.detectar_encoder("auto") == "libx264"
    video = video_sintetico(tmp_path / "video.mp4", duracion=5.0)
    salida = str(tmp_path / "clip.mp4")
    core.exportar_clip(video, 0, 5, None, salida, con_subtitulos=False)
    assert ("video", "h264") in flujos(salida)
