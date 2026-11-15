"""Tests de exportar_clip (B9): -map, ASS en cwd temporal, sin audio."""
import json
import os
import subprocess
import threading
import time
import wave

import numpy as np
import pytest
from conftest import video_sintetico

import clipia_core as core

VIDEO_PRUEBA = os.path.expanduser(
    "~/workspace/clipia-test/video_prueba.mp4")


def _ffmpeg_corriendo():
    """Número de procesos ffmpeg en curso (solo Linux vía /proc;
    None si no se puede contar)."""
    if not os.path.isdir("/proc"):
        return None
    total = 0
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            with open("/proc/%s/cmdline" % pid, "rb") as archivo:
                if b"ffmpeg" in archivo.read().split(b"\0")[0]:
                    total += 1
        except OSError:
            pass
    return total


def flujos(ruta):
    """Lista de (tipo, codec) de un archivo con ffprobe."""
    resultado = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "stream=codec_type,codec_name", "-of", "json", ruta],
        capture_output=True, text=True, check=True, timeout=60)
    return [(s["codec_type"], s["codec_name"])
            for s in json.loads(resultado.stdout)["streams"]]


def frecuencia_dominante(ruta_video):
    """Frecuencia dominante (Hz) del audio de un video, vía FFT."""
    ruta_wav = ruta_video + ".wav"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", ruta_video,
         "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", ruta_wav],
        check=True, timeout=60)
    with wave.open(ruta_wav, "rb") as archivo:
        datos = archivo.readframes(archivo.getnframes())
    muestras = np.frombuffer(datos, dtype=np.int16).astype(np.float32)
    espectro = np.abs(np.fft.rfft(muestras * np.hanning(len(muestras))))
    frecuencias = np.fft.rfftfreq(len(muestras), d=1.0 / 16000)
    return float(frecuencias[int(np.argmax(espectro))])


def video_dos_audios(ruta, duracion=5.0):
    """Video con 2 pistas de audio: la 1ª mono 440 Hz, la 2ª estéreo
    880 Hz marcada como pista por defecto. Sin -map, ffmpeg elige la
    2ª (por la disposición default); con -map 0:a:0? se exporta la 1ª."""
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "lavfi", "-i",
         "testsrc=duration=%.1f:size=640x360:rate=30" % duracion,
         "-f", "lavfi", "-i", "sine=frequency=440:duration=%.1f" % duracion,
         "-f", "lavfi", "-i", "sine=frequency=880:duration=%.1f" % duracion,
         "-map", "0:v", "-map", "1:a", "-map", "2:a",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
         "-ac:1", "1", "-ac:2", "2",
         "-disposition:a:0", "0", "-disposition:a:1", "default",
         "-shortest", str(ruta)],
        check=True, timeout=120)
    return str(ruta)


SEGMENTOS = [{"start": 0.0, "end": 5.0, "text": "hola mundo de prueba",
              "words": []}]


def test_exportar_con_ass_en_ruta_con_comas_y_corchetes(tmp_path):
    """B9: el ASS vive en un cwd temporal con nombre simple, así que
    una ruta real con comas, corchetes o espacios ya no rompe el
    filtro subtitles (el escapado era frágil)."""
    video = video_sintetico(tmp_path / "video.mp4", duracion=5.0)
    carpeta_rara = tmp_path / "dir, con [corchetes] y espacios"
    carpeta_rara.mkdir()
    ruta_ass = carpeta_rara / "clip_tmp.ass"
    core.generar_subtitulos_ass(SEGMENTOS, 0, 5, str(ruta_ass))
    salida = str(tmp_path / "clip.mp4")
    core.exportar_clip(video, 0, 5, str(ruta_ass), salida)
    assert ("video", "h264") in flujos(salida)
    assert ("audio", "aac") in flujos(salida)


def test_exportar_multipista_usa_el_primer_audio(tmp_path):
    """B9: con -map 0:a:0? se exporta la PRIMERA pista de audio (440 Hz
    mono), no la "mejor" según ffmpeg (880 Hz estéreo)."""
    video = video_dos_audios(tmp_path / "dos_audios.mp4", duracion=5.0)
    assert len([f for f in flujos(video) if f[0] == "audio"]) == 2
    salida = str(tmp_path / "clip.mp4")
    core.exportar_clip(video, 0, 5, None, salida, con_subtitulos=False)
    audios = [f for f in flujos(salida) if f[0] == "audio"]
    assert audios == [("audio", "aac")]
    freq = frecuencia_dominante(salida)
    assert 400 < freq < 480, "el audio exportado no es el de 440 Hz: %s" % freq


def test_exportar_video_sin_audio_no_falla(tmp_path):
    """B9: -map 0:a:0? hace el audio opcional: un video sin pista de
    audio exporta solo video, sin error."""
    video = video_sintetico(tmp_path / "sin_audio.mp4", duracion=5.0,
                            audio=False)
    salida = str(tmp_path / "clip.mp4")
    core.exportar_clip(video, 0, 5, None, salida, con_subtitulos=False)
    assert flujos(salida) == [("video", "h264")]


def test_exportar_clip_cancelar_mata_ffmpeg_y_borra_parcial(tmp_path):
    """Fase 1: cancelar a mitad mata el ffmpeg en menos de 2 s, borra
    el parcial y no deja el proceso huérfano."""
    if not os.path.isfile(VIDEO_PRUEBA):
        pytest.skip("solo local: necesita el video de prueba")
    salida = str(tmp_path / "clip.mp4")
    cancelar = threading.Event()
    momento = {}

    def marcar():
        momento["t"] = time.time()
        cancelar.set()

    antes = _ffmpeg_corriendo()
    threading.Timer(2.0, marcar).start()
    t0 = time.time()
    with pytest.raises(core.ExportacionCancelada):
        core.exportar_clip(VIDEO_PRUEBA, 0, 30, None, salida,
                           con_subtitulos=False, cancelar=cancelar)
    t_fin = time.time()
    # La cancelación llegó a los 2 s; el proceso debió morir en <2 s
    # desde ese momento (un export de 30 s tardaría ~25 s).
    assert t_fin - momento["t"] < 2.0, "el ffmpeg tardó en morir"
    assert t_fin - t0 < 10.0
    assert not os.path.exists(salida), "el parcial no se borró"
    despues = _ffmpeg_corriendo()
    if antes is not None and despues is not None:
        assert despues <= antes, "quedó un ffmpeg huérfano"
