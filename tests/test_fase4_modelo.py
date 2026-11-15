"""Tests de la descarga del modelo Whisper con progreso (Fase 4).

Sin red: Hugging Face va mockeado, salvo la comprobación de caché
del modelo base (que sí está descargado en este entorno).
"""
from unittest import mock

import pytest

import clipia_core as core
from clipia import transcripcion as tr
from clipia.transcripcion import ErrorDescargaModelo


def test_repo_modelo_usa_el_mismo_que_faster_whisper():
    assert tr._repo_modelo("base") == "Systran/faster-whisper-base"
    assert tr._repo_modelo("large-v3") == "Systran/faster-whisper-large-v3"
    assert (tr._repo_modelo("Systran/faster-whisper-small")
            == "Systran/faster-whisper-small")


def test_progreso_descarga_acumula_varios_archivos():
    """Dos barras (dos archivos) se suman en un único porcentaje."""
    avances = []
    acumulador = tr._ProgresoDescarga(avances.append)
    barra = tr._clase_barra(acumulador)
    primera = barra(total=100, desc="model.bin")
    segunda = barra(total=300, desc="tokenizer.json")
    primera.update(50)
    assert avances[-1] == pytest.approx(50 / 400)
    segunda.update(300)
    assert avances[-1] == pytest.approx(350 / 400)
    primera.close()
    segunda.close()


def test_descargar_modelo_en_cache_no_descarga(monkeypatch):
    """Si el modelo está en caché, snapshot_download con
    local_files_only devuelve la ruta y no se descarga nada."""
    with mock.patch("huggingface_hub.snapshot_download",
                    return_value="/cache/base") as descargar:
        ruta = tr.descargar_modelo("base")
    assert ruta == "/cache/base"
    assert descargar.call_count == 1
    assert descargar.call_args.kwargs["local_files_only"] is True


def test_descargar_modelo_descarga_si_no_esta_en_cache(monkeypatch):
    """Sin caché: primer intento local falla, segundo descarga con
    la clase tqdm propia y termina en 1.0."""
    avances = []
    llamadas = []

    def descargar_falso(repo_id, **kwargs):
        llamadas.append(kwargs)
        if kwargs.get("local_files_only"):
            raise RuntimeError("no está en caché")
        # Simular que Hugging Face crea una barra y avanza.
        barra = kwargs["tqdm_class"](total=100, desc="model.bin")
        barra.update(100)
        barra.close()
        return "/cache/base"

    with mock.patch("huggingface_hub.snapshot_download",
                    side_effect=descargar_falso):
        ruta = tr.descargar_modelo("base", avances.append)
    assert ruta == "/cache/base"
    assert len(llamadas) == 2
    assert "tqdm_class" in llamadas[1]
    assert llamadas[1]["allow_patterns"] == tr._PATRONES_MODELO
    assert avances[-1] == 1.0


def test_descargar_modelo_sin_red_da_mensaje_accionable():
    """Sin red, el error es ErrorDescargaModelo con el modelo y su
    tamaño, no el error técnico de Hugging Face."""

    def descargar_falso(repo_id, **kwargs):
        if kwargs.get("local_files_only"):
            raise RuntimeError("no está en caché")
        raise ConnectionError("Name or service not known")

    with mock.patch("huggingface_hub.snapshot_download",
                    side_effect=descargar_falso):
        with pytest.raises(ErrorDescargaModelo) as excinfo:
            tr.descargar_modelo("base")
    assert "base" in str(excinfo.value)
    assert "150 MB" in str(excinfo.value)
    assert "conexión" in str(excinfo.value)


def test_obtener_modelo_descarga_antes_de_crear(monkeypatch):
    """obtener_modelo asegura la descarga (con el callback) antes de
    crear el modelo."""
    tr.liberar_modelos()
    llamadas = []
    monkeypatch.setattr(
        tr, "descargar_modelo",
        lambda m, p=None: llamadas.append((m, p)) or "/cache/base")
    monkeypatch.setattr(tr, "_crear_modelo",
                        lambda m, d, t: (object(), d))
    callback = mock.Mock()
    tr.obtener_modelo("base", "cpu", "int8", callback)
    assert llamadas == [("base", callback)]
    tr.liberar_modelos()


def test_obtener_modelo_en_memoria_no_descarga(monkeypatch):
    """Con el modelo ya en memoria, no se toca la descarga."""
    tr.liberar_modelos()
    monkeypatch.setattr(tr, "descargar_modelo",
                        lambda m, p=None: "/cache/base")
    monkeypatch.setattr(tr, "_crear_modelo",
                        lambda m, d, t: (object(), d))
    a = tr.obtener_modelo("base", "cpu", "int8")
    llamadas = []
    monkeypatch.setattr(tr, "descargar_modelo",
                        lambda m, p=None: llamadas.append(m))
    b = tr.obtener_modelo("base", "cpu", "int8")
    assert a is b
    assert llamadas == []
    tr.liberar_modelos()


def test_transcribir_pasa_progreso_descarga(monkeypatch, tmp_path):
    """transcribir pasa el callback de descarga a obtener_modelo."""
    video = tmp_path / "v.mp4"
    video.write_bytes(b"falso")
    monkeypatch.setattr(tr, "obtener_duracion", lambda r: 30.0)
    monkeypatch.setattr(tr, "_elegir_dispositivo", lambda: ("cpu", "int8"))
    llamadas = {}

    def obtener_falso(m, d, t, p=None):
        llamadas["progreso_descarga"] = p
        return "modelo"

    monkeypatch.setattr(tr, "obtener_modelo", obtener_falso)
    monkeypatch.setattr(tr, "_extraer_audio_wav", lambda a, b: None)
    monkeypatch.setattr(tr, "_leer_wav_numpy", lambda r: [0.0])
    monkeypatch.setattr(tr, "_transcribir_con_modelo",
                        lambda *a, **k: [{"start": 0.0, "end": 1.0,
                                          "text": "hola", "words": []}])
    callback = mock.Mock()
    tr.transcribir(str(video), usar_cache=False,
                   progreso_descarga=callback)
    assert llamadas["progreso_descarga"] is callback


def test_analizar_video_pasa_progreso_descarga(app, tmp_path):
    """_analizar_video pasa un callback de descarga a transcribir, y
    al llamarlo cambia el texto de estado."""
    video = tmp_path / "video.mp4"
    video.write_bytes(b"falso")
    segmentos = [{"start": 0.0, "end": 30.0, "text": "hola",
                 "words": []}]
    candidatos = [{"start": 0.0, "end": 30.0, "score": 1.0,
                   "text": "hola"}]
    estados = []
    with mock.patch.object(core, "obtener_duracion",
                           return_value=30.0), \
            mock.patch.object(core, "transcribir",
                              return_value=segmentos) as transcribir, \
            mock.patch.object(core, "detectar_momentos",
                              return_value=candidatos):
        app._analizar_video(str(video), "",
                            lambda texto, valor: estados.append(texto))
    callback = transcribir.call_args.kwargs["progreso_descarga"]
    assert callable(callback)
    callback(0.5)
    assert estados[-1] == "Descargando modelo de voz…"
