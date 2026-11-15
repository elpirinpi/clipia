"""Tests de los ajustes ampliados (Fase 3): modelo de Ollama y
lote de transcripción."""
from unittest import mock

from test_gui_exportar import SEGMENTOS

import main as app_mod
from clipia.config import VALORES_DEFECTO, cargar_config, guardar_config


def test_config_defectos_ollama_y_lote(tmp_path):
    valores = cargar_config(str(tmp_path / "config.json"))
    assert valores["ollama_modelo"] == "qwen2.5:7b"
    assert valores["lote_transcripcion"] == 0
    assert valores["ollama_modelo"] == VALORES_DEFECTO["ollama_modelo"]


def test_config_guarda_y_lee_nuevas_claves(tmp_path):
    ruta = str(tmp_path / "config.json")
    guardar_config({"ollama_modelo": "llama3:8b", "lote_transcripcion": 8,
                    "clave_desconocida": 1}, ruta)
    valores = cargar_config(ruta)
    assert valores["ollama_modelo"] == "llama3:8b"
    assert valores["lote_transcripcion"] == 8
    assert "clave_desconocida" not in valores


def test_dialogo_muestra_modelo_ollama_y_lote(app):
    dialogo = app_mod.DialogoAjustes(
        app, {"ollama_modelo": "llama3:8b", "lote_transcripcion": 8},
        lambda valores: None)
    try:
        assert dialogo.variable_ollama.get() == "llama3:8b"
        assert dialogo.variable_lote.get() == "8"
    finally:
        dialogo.destroy()


def test_dialogo_guarda_modelo_ollama_y_lote(app):
    guardados = {}
    dialogo = app_mod.DialogoAjustes(app, {}, guardados.update)
    try:
        dialogo.variable_ollama.set("qwen2.5:14b")
        dialogo.variable_lote.set("16")
        dialogo._guardar()
    finally:
        try:
            dialogo.destroy()
        except Exception:
            pass
    assert guardados["ollama_modelo"] == "qwen2.5:14b"
    assert guardados["lote_transcripcion"] == 16


def test_dialogo_ollama_vacio_usa_defecto_y_lote_auto_es_cero(app):
    guardados = {}
    dialogo = app_mod.DialogoAjustes(app, {}, guardados.update)
    try:
        dialogo.variable_ollama.set("   ")
        dialogo.variable_lote.set("Automático")
        dialogo._guardar()
    finally:
        try:
            dialogo.destroy()
        except Exception:
            pass
    assert guardados["ollama_modelo"] == "qwen2.5:7b"
    assert guardados["lote_transcripcion"] == 0


def test_reordenar_usa_modelo_configurado(app):
    app.config["ollama_modelo"] = "llama3:8b"
    app.candidatos = [{"start": 0.0, "end": 5.0, "score": 1.0,
                       "text": "uno"}]
    with mock.patch.object(app_mod, "ollama_disponible",
                           return_value=True), \
            mock.patch.object(app_mod, "modelo_disponible",
                              return_value=True) as disponible, \
            mock.patch.object(app_mod, "rerank_ollama",
                              return_value=None) as rerank:
        app._hilo_reordenar_ollama({})
        app._procesar_cola()
    disponible.assert_called_once_with("llama3:8b")
    rerank.assert_called_once()
    assert rerank.call_args[0][1] == "llama3:8b"
    assert "no respondió" in app.etiqueta_estado.cget("text")


def test_reordenar_avisa_con_el_modelo_configurado(app):
    app.config["ollama_modelo"] = "llama3:8b"
    app.candidatos = [{"start": 0.0, "end": 5.0, "score": 1.0,
                       "text": "uno"}]
    with mock.patch.object(app_mod, "ollama_disponible",
                           return_value=True), \
            mock.patch.object(app_mod, "modelo_disponible",
                              return_value=False), \
            mock.patch.object(app_mod.messagebox,
                              "showinfo") as info:
        app._hilo_reordenar_ollama({})
        app._procesar_cola()
    info.assert_called_once()
    assert "llama3:8b" in info.call_args[0][1]
    assert "ollama pull llama3:8b" in info.call_args[0][1]


def test_analizar_video_pasa_lote_configurado(app, tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"fake")
    clips = [{"start": 0.0, "end": 5.0, "score": 1.0, "text": "uno"}]
    app.config["lote_transcripcion"] = 8
    with mock.patch.object(app_mod.core, "obtener_duracion",
                           return_value=120.0), \
            mock.patch.object(app_mod.core, "transcribir",
                              return_value=list(SEGMENTOS)) as transcribir, \
            mock.patch.object(app_mod.core, "detectar_momentos",
                              return_value=[dict(c) for c in clips]):
        app._analizar_video(str(video), "", lambda t, v: None)
    assert transcribir.call_args[1]["batch_size"] == 8


def test_analizar_video_lote_auto_pasa_none(app, tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"fake")
    clips = [{"start": 0.0, "end": 5.0, "score": 1.0, "text": "uno"}]
    app.config["lote_transcripcion"] = 0
    with mock.patch.object(app_mod.core, "obtener_duracion",
                           return_value=120.0), \
            mock.patch.object(app_mod.core, "transcribir",
                              return_value=list(SEGMENTOS)) as transcribir, \
            mock.patch.object(app_mod.core, "detectar_momentos",
                              return_value=[dict(c) for c in clips]):
        app._analizar_video(str(video), "", lambda t, v: None)
    assert transcribir.call_args[1]["batch_size"] is None
