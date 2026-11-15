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
    assert guardados["encoder"] == "libx264"
    assert guardados["modelo"] == "base"
    assert guardados["idioma"] == "es"


def test_dialogo_ajustes_muestra_modelo_e_idioma(app):
    dialogo = app_mod.DialogoAjustes(
        app, {"encoder": "auto", "modelo": "small", "idioma": "en"},
        lambda valores: None)
    try:
        assert "Small" in dialogo.variable_modelo.get()
        assert dialogo.variable_idioma.get() == "Inglés"
    finally:
        dialogo.destroy()


def test_dialogo_ajustes_guarda_modelo_e_idioma(app):
    guardados = {}
    dialogo = app_mod.DialogoAjustes(app, {"encoder": "auto"},
                                     guardados.update)
    try:
        dialogo.variable_modelo.set(
            "Small · ~470 MB · más preciso")
        dialogo.variable_idioma.set("Autodetectar")
        dialogo._guardar()
    finally:
        try:
            dialogo.destroy()
        except Exception:
            pass
    assert guardados["modelo"] == "small"
    assert guardados["idioma"] == "auto"


def test_aviso_ram_advierte_si_falta_ram(app):
    dialogo = app_mod.DialogoAjustes(app, {"encoder": "auto"},
                                     lambda valores: None)
    try:
        dialogo._ram_total = 4.0
        dialogo.variable_modelo.set(
            "Large v3 · ~3.1 GB · máxima precisión")
        dialogo._actualizar_aviso_ram()
        assert "⚠" in dialogo.etiqueta_ram.cget("text")
        dialogo._ram_total = 16.0
        dialogo._actualizar_aviso_ram()
        assert "⚠" not in dialogo.etiqueta_ram.cget("text")
    finally:
        dialogo.destroy()


def test_al_guardar_ajustes_actualiza_config(app, monkeypatch):
    monkeypatch.setattr(app_mod, "guardar_config", lambda valores: "x")
    app._al_guardar_ajustes({"encoder": "libx264"})
    assert app.config["encoder"] == "libx264"


def test_dialogo_ajustes_muestra_workers_actual(app):
    dialogo = app_mod.DialogoAjustes(app, {"workers_exportacion": 2},
                                     lambda valores: None)
    try:
        assert dialogo.variable_workers.get() == "2 clips a la vez"
    finally:
        dialogo.destroy()


def test_dialogo_ajustes_guarda_workers(app):
    guardados = {}
    dialogo = app_mod.DialogoAjustes(app, {"workers_exportacion": 0},
                                     guardados.update)
    try:
        dialogo.variable_workers.set("3 clips a la vez")
        dialogo._guardar()
    finally:
        try:
            dialogo.destroy()
        except Exception:
            pass
    assert guardados["workers_exportacion"] == 3
