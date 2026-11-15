"""Tests de GUI del editor de clip (Fase 3)."""
import time
from unittest import mock

import pytest
from conftest import video_sintetico
from test_editor import SEGMENTOS

import main as app_mod

CLIP = {"start": 1.0, "end": 4.0, "score": 1.0, "text": "clip",
        "video": "video.mp4"}


def _dialogo(app, clip=None, ruta_video="no_existe.mp4", duracion=120.0):
    guardados = []
    dialogo = app_mod.DialogoEditorClip(
        app, dict(clip or CLIP), SEGMENTOS, ruta_video, duracion,
        lambda inicio, fin: guardados.append((inicio, fin)))
    return dialogo, guardados


def _esperar_forma(app, dialogo, segundos=10):
    limite = time.time() + segundos
    while not dialogo._forma_lista.is_set() and time.time() < limite:
        app.update()
        time.sleep(0.05)
    # La imagen se pone en un after(100) posterior al hilo: dar
    # tiempo a que ese callback corra.
    limite = time.time() + 3
    while time.time() < limite:
        app.update()
        if dialogo.etiqueta_forma.cget("image") or \
                "Sin audio" in dialogo.etiqueta_forma.cget("text"):
            return
        time.sleep(0.05)


def test_dialogo_muestra_tiempos(app):
    dialogo, _guardados = _dialogo(app)
    try:
        assert dialogo.slider_inicio.get() == pytest.approx(1.0)
        assert dialogo.slider_fin.get() == pytest.approx(4.0)
        assert "0:01.0" in dialogo.etiqueta_inicio.cget("text")
        assert "0:04.0" in dialogo.etiqueta_fin.cget("text")
        assert "0:03.0" in dialogo.etiqueta_fin.cget("text")
    finally:
        dialogo.destroy()


def test_slider_actualiza_tiempos_y_sujeta(app):
    dialogo, _guardados = _dialogo(app)
    try:
        dialogo._al_mover_inicio(2.0)
        assert dialogo._inicio == 2.0
        assert "0:02.0" in dialogo.etiqueta_inicio.cget("text")
        # El inicio no puede pasar de fin - 1 s.
        dialogo._al_mover_inicio(3.9)
        assert dialogo._inicio == 3.0
        # El fin no puede bajar de inicio + 1 s.
        dialogo._al_mover_fin(0.5)
        assert dialogo._fin == 4.0
        dialogo._al_mover_fin(5.0)
        assert dialogo._fin == 5.0
        assert "0:02.0" in dialogo.etiqueta_fin.cget("text")
    finally:
        dialogo.destroy()


def test_clic_palabra_fija_limites(app):
    dialogo, _guardados = _dialogo(app)
    try:
        dialogo._al_clic_palabra({"start": 2.0, "end": 2.5, "word": " una"})
        assert dialogo._inicio == 2.0
        # Tras fijar el inicio, el límite activo pasa a ser el fin.
        assert dialogo._limite_activo == "fin"
        assert dialogo.boton_limite.get() == "Editar fin"
        dialogo._al_clic_palabra({"start": 2.5, "end": 3.0,
                                  "word": " prueba."})
        assert dialogo._fin == 3.0
    finally:
        dialogo.destroy()


def test_clic_onda_fija_limite(app):
    dialogo, _guardados = _dialogo(app)
    try:
        dialogo.update()
        # Ventana visible: [0, 9] s (clip 1-4 ± 5 s); x=56 de 560
        # es el 10% -> 0.9 s.
        class Evento:
            x = 56

        dialogo._al_clic_onda(Evento())
        assert dialogo._inicio == pytest.approx(0.9, abs=0.05)
    finally:
        dialogo.destroy()


def test_waveform_se_genera_con_video_real(app, tmp_path):
    video = video_sintetico(tmp_path / "origen.mp4", duracion=10.0)
    clip = {"start": 2.0, "end": 8.0, "score": 1.0, "text": "clip",
            "video": video}
    dialogo, _guardados = _dialogo(app, clip=clip, ruta_video=video,
                                   duracion=10.0)
    try:
        _esperar_forma(app, dialogo)
        assert dialogo._muestras, "la onda no se generó"
        assert len(dialogo._muestras) == 160
        assert dialogo.etiqueta_forma.cget("image")
    finally:
        dialogo.destroy()


def test_waveform_sin_video_muestra_aviso(app):
    dialogo, _guardados = _dialogo(app)
    try:
        _esperar_forma(app, dialogo)
        assert dialogo._muestras == []
        assert "Sin audio" in dialogo.etiqueta_forma.cget("text")
    finally:
        dialogo.destroy()


def test_guardar_devuelve_tiempos(app):
    dialogo, guardados = _dialogo(app)
    try:
        dialogo._al_mover_inicio(1.5)
        dialogo._al_mover_fin(3.5)
        dialogo._guardar()
        assert guardados == [(1.5, 3.5)]
    finally:
        if dialogo.winfo_exists():
            dialogo.destroy()


def test_editar_clip_actualiza_y_preserva_seleccion(app):
    app.segmentos = list(SEGMENTOS)
    app.duracion_video = 120.0
    app.candidatos = [dict(CLIP),
                      {"start": 6.0, "end": 10.0, "score": 0.9,
                       "text": "segundo", "video": "video.mp4"}]
    app._mostrar_clips()
    app.seleccion[0].set(False)

    class DialogoFalso:
        def __init__(self, padre, clip, segmentos, ruta, duracion,
                     al_guardar):
            al_guardar(6.0, 10.0)

    with mock.patch.object(app_mod, "DialogoEditorClip", DialogoFalso), \
            mock.patch.object(app, "_generar_miniaturas") as generar:
        app._editar_clip(app.candidatos[0])
        # Esperar al hilo que regenera la miniatura.
        limite = time.time() + 5
        while not generar.called and time.time() < limite:
            time.sleep(0.05)
        app._procesar_cola()
    assert app.candidatos[0]["start"] == 6.0
    assert app.candidatos[0]["end"] == 10.0
    assert app.candidatos[0]["text"] == "Segunda frase aquí."
    assert [v.get() for v in app.seleccion] == [False, True]
    generar.assert_called()
