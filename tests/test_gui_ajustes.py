"""Tests del diálogo de Ajustes (Fase 1)."""
import main as app_mod


def test_etiqueta_encoder_existe(app):
    assert "Codificador" in app.etiqueta_encoder.cget("text")


def test_boton_ajustes_se_bloquea_con_el_trabajo(app):
    app._bloquear(True)
    assert str(app.boton_ajustes.cget("state")) == "disabled"
    app._bloquear(False)
    assert str(app.boton_ajustes.cget("state")) == "normal"


def test_dialogo_ajustes_muestra_encoder_actual(app):
    dialogo = app_mod.DialogoAjustes(app, {"encoder": "h264_nvenc"},
                                     lambda valores: None)
    try:
        assert dialogo.variable_encoder.get() == "NVENC — GPU NVIDIA"
    finally:
        dialogo.destroy()


def test_dialogo_ajustes_guarda_encoder(app):
    guardados = {}
    dialogo = app_mod.DialogoAjustes(app, {"encoder": "auto"},
                                     guardados.update)
    try:
        dialogo.variable_encoder.set("libx264 — CPU")
        dialogo._guardar()
    finally:
        try:
            dialogo.destroy()
        except Exception:
            pass
    assert guardados == {"encoder": "libx264"}


def test_al_guardar_ajustes_actualiza_config(app, monkeypatch):
    monkeypatch.setattr(app_mod, "guardar_config", lambda valores: "x")
    app._al_guardar_ajustes({"encoder": "libx264"})
    assert app.config["encoder"] == "libx264"
