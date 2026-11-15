# -*- coding: utf-8 -*-
"""Tests de GUI de main.py (B10): limpieza de temps, _bloquear y
selección preservada. La fixture `app` vive en conftest."""
import os
import tempfile

import main as app_mod


def test_arranque_limpia_temps_de_vista_previa(tmp_path, monkeypatch):
    """B10: al arrancar, la app borra los clipia_vista_previa_* y
    clipia_miniaturas_* de sesiones anteriores (y nada más)."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    for nombre in ("clipia_vista_previa_aaa", "clipia_vista_previa_bbb",
                   "clipia_miniaturas_ccc"):
        os.makedirs(os.path.join(str(tmp_path), nombre))
    control = os.path.join(str(tmp_path), "otra_cosa")
    os.makedirs(control)
    aplicacion = app_mod.AppClipIA()
    aplicacion.withdraw()
    try:
        for nombre in ("clipia_vista_previa_aaa", "clipia_vista_previa_bbb",
                       "clipia_miniaturas_ccc"):
            assert not os.path.exists(os.path.join(str(tmp_path), nombre))
        assert os.path.isdir(control)
    finally:
        aplicacion.destroy()


def test_bloquear_deshabilita_botones_y_entradas(app):
    """B10: _bloquear deshabilita también Crear clip, Examinar…,
    Cambiar carpeta, la casilla y los entries (antes solo 3 botones)."""
    widgets = (app.boton_analizar, app.boton_exportar,
               app.boton_seleccionar, app.boton_crear_clip,
               app.boton_examinar, app.boton_carpeta, app.check_rostros,
               app.entrada_archivo, app.entrada_url, app.entrada_salida)
    app._bloquear(True)
    assert app.ocupado is True
    for w in widgets:
        assert str(w.cget("state")) == "disabled", w
    app._bloquear(False)
    assert app.ocupado is False
    for w in widgets:
        assert str(w.cget("state")) == "normal", w


def _dos_clips(app):
    app.duracion_video = 120.0
    app.candidatos = [
        {"start": 0.0, "end": 30.0, "score": 1.0, "text": "uno"},
        {"start": 30.0, "end": 60.0, "score": 0.9, "text": "dos"},
    ]
    app._mostrar_clips()


def test_mostrar_clips_preserva_seleccion(app):
    """B10: al agregar un clip manual, lo que el usuario desmarcó se
    mantiene desmarcado (antes todo volvía a marcado)."""
    _dos_clips(app)
    app.seleccion[0].set(False)
    app.candidatos.append({"start": 60.0, "end": 90.0, "score": 0.0,
                           "text": "manual"})
    app._mostrar_clips(preservar_seleccion=True)
    assert [v.get() for v in app.seleccion] == [False, True, True]


def test_mostrar_clips_sin_preservar_reinicia(app):
    """Tras un análisis nuevo, la selección vuelve toda a marcada."""
    _dos_clips(app)
    app.seleccion[0].set(False)
    app._mostrar_clips()
    assert [v.get() for v in app.seleccion] == [True, True]


def test_al_cerrar_borra_miniaturas(app, tmp_path):
    """B10: al cerrar, se borra el directorio de miniaturas."""
    miniaturas = tmp_path / "miniaturas"
    miniaturas.mkdir()
    (miniaturas / "clip01.jpg").write_bytes(b"fake")
    app._dir_miniaturas = str(miniaturas)
    app._al_cerrar()
    assert not os.path.exists(str(miniaturas))
    assert app._dir_miniaturas is None
