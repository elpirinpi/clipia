"""Tests de GUI del diálogo de resultado de exportación (Fase 3)."""
from unittest import mock

from test_gui_exportar import CLIPS, SEGMENTOS, ColaFalsa, _con_cola_falsa

import main as app_mod
from clipia.cola import ResultadoClip, TrabajoExportacion


def _resultados():
    trabajos = [
        TrabajoExportacion(clip=CLIPS[0], ruta_video="video.mp4",
                           carpeta_salida="/tmp/salida",
                           nombre="video_clip01_000-005.mp4"),
        TrabajoExportacion(clip=CLIPS[1], ruta_video="video.mp4",
                           carpeta_salida="/tmp/salida",
                           nombre="video_clip02_005-010.mp4"),
    ]
    return [ResultadoClip(trabajos[0], True,
                          ruta="/tmp/salida/video_clip01_000-005.mp4"),
            ResultadoClip(trabajos[1], False, error="ffmpeg falló")]


def _textos_dialogo(dialogo):
    """Textos de todas las etiquetas del diálogo (recursivo)."""

    def recorrer(widget):
        textos = []
        for hijo in widget.winfo_children():
            if hijo.__class__.__name__ == "CTkLabel":
                textos.append(hijo.cget("text"))
            textos.extend(recorrer(hijo))
        return textos

    return recorrer(dialogo)


def test_dialogo_muestra_lista_exito_fallo(app):
    dialogo = app_mod.DialogoResultadoExportacion(
        app, _resultados(), "/tmp/salida", lambda ruta: None)
    try:
        textos = _textos_dialogo(dialogo)
        assert any("1 de 2" in t for t in textos)
        assert any("✓ video_clip01_000-005.mp4" in t for t in textos)
        assert any("✗ video_clip02_005-010.mp4" in t for t in textos)
        assert any("ffmpeg falló" in t for t in textos)
    finally:
        dialogo.destroy()


def test_dialogo_boton_abrir_carpeta(app):
    abiertas = []
    dialogo = app_mod.DialogoResultadoExportacion(
        app, _resultados(), "/tmp/salida", abiertas.append)
    try:
        dialogo.boton_abrir.invoke()
        assert abiertas == ["/tmp/salida"]
    finally:
        dialogo.destroy()


def test_dialogo_muestra_cancelados(app):
    trabajos = [TrabajoExportacion(clip=CLIPS[0], ruta_video="video.mp4",
                                   nombre="clip01.mp4")]
    resultados = [ResultadoClip(trabajos[0], False, cancelado=True)]
    dialogo = app_mod.DialogoResultadoExportacion(
        app, resultados, "/tmp/salida", lambda ruta: None)
    try:
        textos = _textos_dialogo(dialogo)
        assert any("cancelado" in t for t in textos)
        assert any("0 de 1" in t for t in textos)
    finally:
        dialogo.destroy()


def test_hilo_exportar_muestra_dialogo_resultado(app, tmp_path):
    """Al terminar, _hilo_exportar abre el diálogo de resultado con
    los resultados (en vez del messagebox de antes)."""
    ColaFalsa.instancias.clear()
    app.carpeta_salida = str(tmp_path)
    creados = []

    class DialogoFalso:
        def __init__(self, padre, resultados, carpeta, al_abrir):
            creados.append((resultados, carpeta, al_abrir))

    with _con_cola_falsa(), mock.patch.object(
            app_mod, "DialogoResultadoExportacion", DialogoFalso):
        app._hilo_exportar(CLIPS, "video.mp4", SEGMENTOS, False)
        app._procesar_cola()
    assert len(creados) == 1
    resultados, carpeta, _al_abrir = creados[0]
    assert len(resultados) == 2 and all(r.ok for r in resultados)
    assert carpeta == str(tmp_path)


def test_hilo_exportar_cancelado_no_muestra_dialogo(app, tmp_path):
    ColaFalsa.instancias.clear()

    def exportar_cancelado(self, trabajos, cancelar=None):
        self.trabajos = trabajos
        return [ResultadoClip(t, False, cancelado=True) for t in trabajos]

    with _con_cola_falsa(), mock.patch.object(
            app_mod, "DialogoResultadoExportacion") as dialogo, \
            mock.patch.object(ColaFalsa, "exportar", exportar_cancelado):
        app._hilo_exportar(CLIPS, "video.mp4", SEGMENTOS, False)
        app._procesar_cola()
    dialogo.assert_not_called()
