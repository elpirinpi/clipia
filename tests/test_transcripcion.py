"""Tests de transcripción (Fase 1): singleton, batching, fallback."""
import os
from types import SimpleNamespace

import pytest
from conftest import video_sintetico

import clipia_core as core
from clipia import transcripcion as tr

VIDEO_CON_VOZ = os.path.expanduser(
    "~/workspace/clipia-test/video_prueba.mp4")


def _palabra(texto, inicio, fin):
    return SimpleNamespace(word=texto, start=inicio, end=fin)


def _segmento(texto, inicio, fin, palabras):
    return SimpleNamespace(text=texto, start=inicio, end=fin,
                           words=palabras)


class FakePipeline:
    """Sustituto de BatchedInferencePipeline que graba sus llamadas."""
    llamadas = []
    fallar_primer_intento = False
    error_vad_primer_intento = False
    _intentos = 0

    def __init__(self, modelo):
        self.modelo = modelo

    def transcribe(self, audio, language=None, batch_size=8, **kwargs):
        FakePipeline.llamadas.append(
            {"modelo": self.modelo, "language": language,
             "batch_size": batch_size,
             "vad_filter": kwargs.get("vad_filter")})
        FakePipeline._intentos += 1
        if (FakePipeline.error_vad_primer_intento
                and FakePipeline._intentos == 1):
            raise RuntimeError(
                "NoSuchFile: [ONNXRuntimeError] : 3 : NO_SUCHFILE : "
                "Load model from .../silero_vad_v6.onnx failed. "
                "File doesn't exist")
        if FakePipeline.fallar_primer_intento and FakePipeline._intentos == 1:
            raise RuntimeError("fallo de GPU provocado")
        palabras = [_palabra(" hola", 0.0, 0.5), _palabra(" mundo", 0.5, 1.0)]
        return [_segmento(" hola mundo", 0.0, 1.0, palabras)], None


@pytest.fixture(autouse=True)
def limpiar():
    tr.liberar_modelos()
    FakePipeline.llamadas = []
    FakePipeline.fallar_primer_intento = False
    FakePipeline.error_vad_primer_intento = False
    FakePipeline._intentos = 0
    yield
    tr.liberar_modelos()


def test_singleton_cachea_el_modelo(monkeypatch):
    creados = []
    monkeypatch.setattr(tr, "descargar_modelo",
                        lambda m, p=None: "/fake/modelo")
    monkeypatch.setattr(tr, "_crear_modelo",
                        lambda m, d, t: (object(), d))
    # Contar creaciones envolviendo la función original parcheada.
    original = tr._crear_modelo
    monkeypatch.setattr(
        tr, "_crear_modelo",
        lambda m, d, t: creados.append((m, d)) or original(m, d, t))
    a = tr.obtener_modelo("base", "cpu", "int8")
    b = tr.obtener_modelo("base", "cpu", "int8")
    assert a is b
    assert len(creados) == 1
    tr.obtener_modelo("tiny", "cpu", "int8")
    assert len(creados) == 2
    tr.liberar_modelos()
    tr.obtener_modelo("base", "cpu", "int8")
    assert len(creados) == 3


def test_singleton_olvida_el_mas_antiguo(monkeypatch):
    monkeypatch.setattr(tr, "descargar_modelo",
                        lambda m, p=None: "/fake/modelo")
    monkeypatch.setattr(tr, "_crear_modelo",
                        lambda m, d, t: (object(), d))
    base = tr.obtener_modelo("base", "cpu", "int8")
    tr.obtener_modelo("tiny", "cpu", "int8")
    tr.obtener_modelo("small", "cpu", "int8")
    # Solo caben 2: base fue desalojado y se vuelve a crear.
    assert tr.obtener_modelo("base", "cpu", "int8") is not base


def test_crear_modelo_cae_a_cpu_si_gpu_falla(monkeypatch):
    import faster_whisper

    def falso_whisper(modelo, device, compute_type):
        if device == "cuda":
            raise RuntimeError("sin CUDA")
        return "modelo-cpu"

    monkeypatch.setattr(faster_whisper, "WhisperModel", falso_whisper)
    modelo, dispositivo = tr._crear_modelo("base", "cuda", "float16")
    assert (modelo, dispositivo) == ("modelo-cpu", "cpu")


def _preparar_fake(monkeypatch, dispositivo="cpu"):
    monkeypatch.setattr(tr, "_elegir_dispositivo",
                        lambda: (dispositivo,
                                 "float16" if dispositivo == "cuda"
                                 else "int8"))
    monkeypatch.setattr(tr, "obtener_modelo",
                        lambda m, d, t, *a, **k: "modelo-%s" % d)
    import faster_whisper
    monkeypatch.setattr(faster_whisper, "BatchedInferencePipeline",
                        FakePipeline)


def test_transcribir_usa_batched_con_batch_8_en_cpu(tmp_path, monkeypatch):
    _preparar_fake(monkeypatch, "cpu")
    video = video_sintetico(tmp_path / "video.mp4", duracion=5.0)
    resultado = tr.transcribir(video)
    assert len(FakePipeline.llamadas) == 1
    llamada = FakePipeline.llamadas[0]
    assert llamada["batch_size"] == 8
    assert llamada["language"] == "es"
    assert resultado[0]["text"] == "hola mundo"
    assert resultado[0]["words"][0]["word"] == " hola"


def test_transcribir_idioma_auto_pasa_none(tmp_path, monkeypatch):
    _preparar_fake(monkeypatch, "cpu")
    video = video_sintetico(tmp_path / "video.mp4", duracion=5.0)
    tr.transcribir(video, idioma="auto")
    assert FakePipeline.llamadas[0]["language"] is None


def test_transcribir_batch_16_en_gpu(tmp_path, monkeypatch):
    _preparar_fake(monkeypatch, "cuda")
    video = video_sintetico(tmp_path / "video.mp4", duracion=5.0)
    tr.transcribir(video)
    assert FakePipeline.llamadas[0]["batch_size"] == 16


def test_transcribir_reintenta_en_cpu_si_gpu_falla(tmp_path, monkeypatch):
    _preparar_fake(monkeypatch, "cuda")
    FakePipeline.fallar_primer_intento = True
    video = video_sintetico(tmp_path / "video.mp4", duracion=5.0)
    resultado = tr.transcribir(video)
    assert resultado[0]["text"] == "hola mundo"
    assert [llamada["modelo"] for llamada in FakePipeline.llamadas] == [
        "modelo-cuda", "modelo-cpu"]


def test_transcribir_reintenta_sin_vad_si_falta_silero(
        tmp_path, monkeypatch):
    """Regresión v2.0.2: si el VAD falla (falta silero_vad_v6.onnx
    en el paquete instalado), se reintenta una vez sin vad_filter
    y la transcripción sale igual."""
    _preparar_fake(monkeypatch, "cpu")
    FakePipeline.error_vad_primer_intento = True
    video = video_sintetico(tmp_path / "video.mp4", duracion=5.0)
    resultado = tr.transcribir(video)
    assert resultado[0]["text"] == "hola mundo"
    assert len(FakePipeline.llamadas) == 2
    assert FakePipeline.llamadas[0]["vad_filter"] is True
    assert FakePipeline.llamadas[1]["vad_filter"] is False


def test_transcribir_no_reintenta_sin_vad_ante_otro_error(
        tmp_path, monkeypatch):
    """Un error que no es del VAD no dispara el reintento sin VAD:
    en CPU sube tal cual tras un solo intento."""
    _preparar_fake(monkeypatch, "cpu")
    FakePipeline.fallar_primer_intento = True
    video = video_sintetico(tmp_path / "video.mp4", duracion=5.0)
    with pytest.raises(RuntimeError, match="fallo de GPU provocado"):
        tr.transcribir(video)
    assert len(FakePipeline.llamadas) == 1


def test_es_error_vad_detecta_silero_onnx_y_otros():
    assert tr._es_error_vad(
        RuntimeError("Load model silero_vad_v6.onnx failed"))
    assert tr._es_error_vad(RuntimeError("vad_filter failed"))
    assert tr._es_error_vad(RuntimeError("[ONNXRuntimeError] NO_SUCHFILE"))
    assert not tr._es_error_vad(RuntimeError("fallo de GPU provocado"))
    assert not tr._es_error_vad(ValueError("otro error"))
    onnx = type("ONNXRuntimeError", (Exception,), {})("sin mensaje")
    assert tr._es_error_vad(onnx)


def test_transcribir_tambien_funciona_desde_la_fachada(tmp_path, monkeypatch):
    _preparar_fake(monkeypatch, "cpu")
    video = video_sintetico(tmp_path / "video.mp4", duracion=5.0)
    assert core.transcribir(video)[0]["text"] == "hola mundo"


@pytest.mark.skipif(not os.path.isfile(VIDEO_CON_VOZ),
                    reason="solo local: necesita el video de prueba")
def test_transcribir_real_batched_con_palabras():
    """Prueba real (lenta): el pipeline batched transcribe voz española
    con timestamps por palabra (sin caché, para probar el modelo)."""
    resultado = tr.transcribir(VIDEO_CON_VOZ, usar_cache=False)
    assert len(resultado) > 0
    palabras = [p for s in resultado for p in s["words"]]
    assert len(palabras) > 100
    assert all(p["end"] >= p["start"] for p in palabras)


def test_ram_total_gb():
    ram = tr.ram_total_gb()
    assert ram is None or ram > 0


def test_modelos_whisper_completos():
    assert set(tr.MODELOS_WHISPER) == {
        "tiny", "base", "small", "medium", "large-v3"}
    for datos in tr.MODELOS_WHISPER.values():
        assert datos["tamano_mb"] > 0
        assert datos["ram_gb"] > 0
        assert datos["descripcion"]
    assert tr.MODELOS_WHISPER["large-v3"]["ram_gb"] == 10
