"""Fase 2: YuNet (FaceDetectorYN) en vez de Haar, banda muerta y más
puntos de interpolación en el recorte."""
import hashlib
import os
import urllib.error

import pytest
from conftest import video_sintetico

from clipia.cache import clave_archivo
from clipia.exportacion import exportar_clip
from clipia.rostros import (
    BANDA_MUERTA,
    SHA256_MODELO_YUNET,
    _expresion_rostros,
    _suavizar_centros,
    descargar_modelo_yunet,
    detectar_rostros,
    ruta_modelo_yunet,
)

VIDEO_ROSTRO = os.path.expanduser(
    "~/workspace/clipia-test/video_rostro.mp4")


def test_descargar_modelo_yunet(monkeypatch, tmp_path):
    """El modelo se descarga, coincide con su SHA-256 y se reutiliza."""
    monkeypatch.setattr("clipia.rostros.carpeta_cache",
                        lambda: str(tmp_path))
    ruta = descargar_modelo_yunet()
    assert ruta == os.path.join(str(tmp_path),
                                "face_detection_yunet_2023mar.onnx")
    assert os.path.isfile(ruta)
    with open(ruta, "rb") as archivo:
        assert (hashlib.sha256(archivo.read()).hexdigest()
                == SHA256_MODELO_YUNET)
    mtime = os.path.getmtime(ruta)
    ruta2 = descargar_modelo_yunet()  # segunda vez: caché local
    assert ruta2 == ruta
    assert os.path.getmtime(ruta) == mtime


def test_descargar_modelo_sin_red_devuelve_none(monkeypatch, tmp_path):
    monkeypatch.setattr("clipia.rostros.carpeta_cache",
                        lambda: str(tmp_path))
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *a, **k: (_ for _ in ()).throw(
            urllib.error.URLError("sin red")))
    assert descargar_modelo_yunet() is None
    assert not os.path.exists(ruta_modelo_yunet())


def test_yunet_detecta_cara_en_movimiento():
    """En video_rostro la cara se mueve de izquierda a derecha."""
    assert os.path.isfile(VIDEO_ROSTRO)
    muestras = detectar_rostros(VIDEO_ROSTRO, 0.0, 30.0, intervalo=2.0)
    assert len(muestras) >= 10
    assert muestras[0][1] < 0.4  # empieza a la izquierda
    assert muestras[-1][1] > 0.6  # termina a la derecha
    # Trayectoria creciente en general (con la banda muerta, en pasos).
    assert muestras[-1][1] - muestras[0][1] > 0.2


def test_banda_muerta_no_mueve_con_tembleque():
    muestras = [(float(t), 0.50 + 0.02 * (1 if t % 2 else -1))
                for t in range(10)]
    resultado = _suavizar_centros(muestras)
    assert all(x == pytest.approx(0.50, abs=1e-9) for _t, x in resultado)


def test_banda_muerta_sigue_movimiento_grande():
    muestras = [(0.0, 0.30), (1.0, 0.31), (2.0, 0.32), (3.0, 0.50),
                (4.0, 0.51), (5.0, 0.52)]
    resultado = _suavizar_centros(muestras)
    assert resultado[0][1] == pytest.approx(0.305, abs=0.01)
    assert resultado[-1][1] == pytest.approx(0.51, abs=0.01)
    # El salto grande se sigue (no se queda en 0.31).
    assert resultado[-1][1] - resultado[0][1] > 0.15


def test_banda_muerta_es_5_por_ciento():
    assert BANDA_MUERTA == 0.05


def test_fallback_haar_sin_modelo(monkeypatch):
    """Sin modelo YuNet, Haar sigue detectando la cara frontal."""
    monkeypatch.setattr("clipia.rostros.descargar_modelo_yunet",
                        lambda progreso=None, timeout=120: None)
    muestras = detectar_rostros(VIDEO_ROSTRO, 0.0, 30.0, intervalo=2.0,
                                usar_cache=False)
    assert len(muestras) >= 5
    assert muestras[-1][1] > muestras[0][1]


def test_clave_cache_incluye_detector():
    clave_yunet = clave_archivo(VIDEO_ROSTRO, version=1, inicio=0.0,
                                fin=30.0, intervalo=2.0, detector="yunet")
    clave_haar = clave_archivo(VIDEO_ROSTRO, version=1, inicio=0.0,
                               fin=30.0, intervalo=2.0, detector="haar")
    assert clave_yunet != clave_haar
    # Sin detector (clave vieja de Fase 1) tampoco coincide.
    clave_vieja = clave_archivo(VIDEO_ROSTRO, version=1, inicio=0.0,
                                fin=30.0, intervalo=2.0)
    assert clave_vieja != clave_yunet
    assert clave_vieja != clave_haar


def test_expresion_usa_todos_los_puntos():
    muestras = [(float(t), 0.30 + 0.01 * t) for t in range(30)]
    expresion = _expresion_rostros(muestras, 608)
    assert expresion is not None
    # 30 puntos -> 29 interpolaciones (antes se recortaba a 12).
    assert expresion.count("if(lt(t,") == 29


def test_export_con_30_puntos_funciona(tmp_path):
    """ffmpeg acepta la expresión larga en una exportación real."""
    video = video_sintetico(tmp_path / "video.mp4", duracion=5.0)
    muestras = [(float(t) / 6, 0.30 + 0.01 * t) for t in range(30)]
    salida = str(tmp_path / "clip.mp4")
    exportar_clip(video, 0.0, 5.0, None, salida, con_subtitulos=False,
                  rostros=muestras)
    assert os.path.isfile(salida)


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
