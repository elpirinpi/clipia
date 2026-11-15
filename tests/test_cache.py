"""Tests de la caché en disco (Fase 1)."""
import os
import time

import pytest
from conftest import video_sintetico
from test_transcripcion import FakePipeline, _preparar_fake

from clipia import cache
from clipia import transcripcion as tr
from clipia.rostros import detectar_rostros

VIDEO_CON_CARA = os.path.expanduser(
    "~/workspace/clipia-test/video_rostro.mp4")


@pytest.fixture
def cache_tmp(tmp_path, monkeypatch):
    """Caché aislada en tmp_path."""
    carpeta = tmp_path / "cache"
    monkeypatch.setattr(cache, "carpeta_cache", lambda: str(carpeta))
    return carpeta


@pytest.fixture(autouse=True)
def limpiar_fake():
    FakePipeline.llamadas = []
    FakePipeline.fallar_primer_intento = False
    FakePipeline._intentos = 0
    yield
    FakePipeline.llamadas = []


def test_clave_estable_y_sensible(tmp_path):
    archivo = tmp_path / "video.mp4"
    archivo.write_bytes(b"contenido falso")
    a = cache.clave_archivo(str(archivo), modelo="base")
    b = cache.clave_archivo(str(archivo), modelo="base")
    assert a == b
    assert cache.clave_archivo(str(archivo), modelo="tiny") != a
    # Tocar la fecha de modificación invalida la clave.
    os.utime(archivo, (time.time() + 100, time.time() + 100))
    assert cache.clave_archivo(str(archivo), modelo="base") != a


def test_clave_archivo_inexistente_lanza_error(tmp_path):
    with pytest.raises(OSError):
        cache.clave_archivo(str(tmp_path / "no_existe.mp4"))


def test_leer_escribir_redondo(cache_tmp):
    assert cache.leer_cache("prueba", "abc") is None
    cache.escribir_cache("prueba", "abc", {"x": [1, 2, 3]})
    assert cache.leer_cache("prueba", "abc") == {"x": [1, 2, 3]}
    # No quedan archivos .tmp tras la escritura atómica.
    assert not list(cache_tmp.rglob("*.tmp"))


def test_leer_cache_corrupta_devuelve_none(cache_tmp):
    carpeta = cache_tmp / "prueba"
    carpeta.mkdir(parents=True)
    (carpeta / "abc.json").write_text("{esto no es json", encoding="utf-8")
    assert cache.leer_cache("prueba", "abc") is None


def test_podar_borra_las_mas_antiguas(cache_tmp):
    carpeta = cache_tmp / "prueba"
    carpeta.mkdir(parents=True)
    for i, tamano in enumerate((1000, 1000, 1000)):
        ruta = carpeta / ("f%d.json" % i)
        ruta.write_bytes(b"x" * tamano)
        # mtimes crecientes: f0 es la más antigua.
        os.utime(ruta, (1000 + i, 1000 + i))
    # Límite de 2 KB: debe borrar solo la más antigua (f0).
    cache._podar(limite_mb=0.002)
    assert not (carpeta / "f0.json").exists()
    assert (carpeta / "f1.json").exists()
    assert (carpeta / "f2.json").exists()


def test_transcribir_reutiliza_cache(tmp_path, cache_tmp, monkeypatch):
    _preparar_fake(monkeypatch, "cpu")
    video = video_sintetico(tmp_path / "video.mp4", duracion=5.0)
    primero = tr.transcribir(video)
    segundo = tr.transcribir(video)
    assert primero == segundo
    assert len(FakePipeline.llamadas) == 1, "la 2ª vez debió usar la caché"


def test_transcribir_cache_invalida_si_cambia_modelo(tmp_path, cache_tmp,
                                                     monkeypatch):
    _preparar_fake(monkeypatch, "cpu")
    video = video_sintetico(tmp_path / "video.mp4", duracion=5.0)
    tr.transcribir(video, modelo="base")
    tr.transcribir(video, modelo="tiny")
    assert len(FakePipeline.llamadas) == 2


def test_transcribir_sin_cache_transcribe_siempre(tmp_path, cache_tmp,
                                                  monkeypatch):
    _preparar_fake(monkeypatch, "cpu")
    video = video_sintetico(tmp_path / "video.mp4", duracion=5.0)
    tr.transcribir(video, usar_cache=False)
    tr.transcribir(video, usar_cache=False)
    assert len(FakePipeline.llamadas) == 2


def test_rostros_no_cachea_errores(tmp_path, cache_tmp, monkeypatch):
    import clipia.rostros as rostros_mod

    video = video_sintetico(tmp_path / "video.mp4", duracion=5.0)
    monkeypatch.setattr(rostros_mod, "ejecutar",
                        lambda *a, **k: (_ for _ in ()).throw(
                            RuntimeError("ffmpeg roto")))
    assert detectar_rostros(video, 0, 5) == []
    assert not list(cache_tmp.rglob("*.json"))


@pytest.mark.skipif(not os.path.isfile(VIDEO_CON_CARA),
                    reason="solo local: necesita el video de prueba")
def test_rostros_reutiliza_cache(cache_tmp):
    """Prueba real: la 2ª detección del mismo clip sale de la caché y
    es casi instantánea."""
    t0 = time.time()
    primero = detectar_rostros(VIDEO_CON_CARA, 0, 30)
    t_primero = time.time() - t0
    assert len(primero) >= 10
    t0 = time.time()
    segundo = detectar_rostros(VIDEO_CON_CARA, 0, 30)
    t_segundo = time.time() - t0
    assert segundo == primero
    assert t_segundo < 0.5, "la 2ª vez debió salir de la caché"
    assert t_segundo < t_primero / 5
