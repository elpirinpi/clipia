"""Tests de los ajustes de la Fase 4: cookies de YouTube."""
from unittest import mock

import clipia_core as core
import main as app_mod
from clipia.config import VALORES_DEFECTO, cargar_config, guardar_config
from clipia.descarga import ErrorDescarga


def test_config_defecto_sin_cookies(tmp_path):
    valores = cargar_config(str(tmp_path / "config.json"))
    assert valores["navegador_cookies"] == "ninguno"
    assert (valores["navegador_cookies"]
            == VALORES_DEFECTO["navegador_cookies"])


def test_config_guarda_y_lee_navegador_cookies(tmp_path):
    ruta = str(tmp_path / "config.json")
    guardar_config({"navegador_cookies": "firefox"}, ruta)
    assert cargar_config(ruta)["navegador_cookies"] == "firefox"


def test_dialogo_muestra_navegador_cookies(app):
    dialogo = app_mod.DialogoAjustes(
        app, {"navegador_cookies": "edge"}, lambda valores: None)
    try:
        assert dialogo.variable_cookies.get() == "Microsoft Edge"
    finally:
        dialogo.destroy()


def test_dialogo_guarda_navegador_cookies(app):
    guardados = {}
    dialogo = app_mod.DialogoAjustes(app, {}, guardados.update)
    try:
        dialogo.variable_cookies.set("Firefox")
        dialogo._guardar()
    finally:
        try:
            dialogo.destroy()
        except Exception:
            pass
    assert guardados["navegador_cookies"] == "firefox"


def test_analizar_video_pasa_el_navegador_configurado(app, tmp_path):
    """_analizar_video pasa el navegador de cookies a la descarga."""
    video = tmp_path / "video.mp4"
    video.write_bytes(b"falso")
    app.config["navegador_cookies"] = "chrome"
    segmentos = [{"start": 0.0, "end": 30.0, "text": "hola",
                 "words": []}]
    candidatos = [{"start": 0.0, "end": 30.0, "score": 1.0,
                   "text": "hola"}]
    with mock.patch.object(core, "descargar_youtube",
                           return_value=str(video)) as descargar, \
            mock.patch.object(core, "obtener_duracion",
                              return_value=30.0), \
            mock.patch.object(core, "transcribir",
                              return_value=segmentos), \
            mock.patch.object(core, "detectar_momentos",
                              return_value=candidatos):
        resultado = app._analizar_video(
            "", "https://www.youtube.com/watch?v=abc",
            lambda texto, valor: None)
    assert descargar.call_args.kwargs["navegador"] == "chrome"
    assert resultado["ruta_video"] == str(video)


def test_detalle_error_muestra_el_mensaje_accionable_tal_cual():
    """Un ErrorDescarga se muestra sin el prefijo del tipo."""
    error = ErrorDescarga("YouTube pide verificar que no eres un bot.",
                          "bot")
    assert app_mod._detalle_error(error) == (
        "YouTube pide verificar que no eres un bot.")


def test_detalle_error_de_otros_errores_lleva_el_tipo():
    assert app_mod._detalle_error(RuntimeError("fallo")) == (
        "RuntimeError: fallo")
