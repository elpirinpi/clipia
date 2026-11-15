"""Tests de GUI del hilo de exportación (Fase 1: cola + Cancelar).

La cola real se prueba en test_cola.py; aquí se prueba que la GUI la
construye bien (trabajos, workers, encoder) y muestra el resumen
correcto. Necesitan pantalla: en Linux correr con xvfb-run -a.
"""
import threading
import time
from unittest import mock

import main as app_mod
from clipia.cola import ResultadoClip

SEGMENTOS = [{"start": 0.0, "end": 10.0, "text": "hola mundo",
              "words": []}]
CLIPS = [{"start": 0.0, "end": 5.0, "score": 1.0, "text": "uno"},
         {"start": 5.0, "end": 10.0, "score": 1.0, "text": "dos"}]


class ColaFalsa:
    """ColaExportacion falsa: registra cómo se construyó y devuelve
    los resultados que se le indiquen."""

    instancias = []

    def __init__(self, workers=1, al_progreso=None, **kwargs):
        self.workers = workers
        self.al_progreso = al_progreso
        self.trabajos = None
        self.resultados = None  # se fija desde el test
        ColaFalsa.instancias.append(self)

    def exportar(self, trabajos, cancelar=None):
        self.trabajos = trabajos
        if self.al_progreso:
            self.al_progreso(1.0, None, len(trabajos), len(trabajos), [])
        if self.resultados is not None:
            return self.resultados
        return [ResultadoClip(t, True, ruta="salida/%s" % t.nombre)
                for t in trabajos]


def _con_cola_falsa():
    return mock.patch.object(app_mod, "ColaExportacion", ColaFalsa)


def test_hilo_exportar_construye_trabajos_y_resume(app, tmp_path):
    """Los trabajos llevan nombre clipNN_inicio-fin, el encoder
    detectado y la carpeta de salida; al final se muestra el diálogo
    de resultado con los clips exportados."""
    ColaFalsa.instancias.clear()
    app.carpeta_salida = str(tmp_path)
    creados = []

    class DialogoFalso:
        def __init__(self, padre, resultados, carpeta, al_abrir):
            creados.append((resultados, carpeta))

    with _con_cola_falsa(), mock.patch.object(
            app_mod, "DialogoResultadoExportacion", DialogoFalso):
        app._hilo_exportar(CLIPS, "video.mp4", SEGMENTOS, False)
        app._procesar_cola()  # el diálogo va por la cola de UI
    cola = ColaFalsa.instancias[-1]
    assert cola.workers == 1  # libx264 en este servidor
    assert [t.nombre for t in cola.trabajos] == [
        "video_clip01_000-005.mp4", "video_clip02_005-010.mp4"]
    assert all(t.encoder == "libx264" for t in cola.trabajos)
    assert all(t.carpeta_salida == str(tmp_path) for t in cola.trabajos)
    assert all(not t.seguir_rostros for t in cola.trabajos)
    assert len(creados) == 1
    resultados, carpeta = creados[0]
    assert len(resultados) == 2 and all(r.ok for r in resultados)
    assert carpeta == str(tmp_path)


def test_hilo_exportar_usa_workers_configurados(app, tmp_path):
    app.config["workers_exportacion"] = 3
    ColaFalsa.instancias.clear()
    with _con_cola_falsa(), mock.patch.object(app_mod.messagebox,
                                              "showinfo"):
        app._hilo_exportar(CLIPS, "video.mp4", SEGMENTOS, False)
    assert ColaFalsa.instancias[-1].workers == 3


def test_hilo_exportar_con_fallos_muestra_dialogo(app, tmp_path):
    ColaFalsa.instancias.clear()
    app.carpeta_salida = str(tmp_path)
    creados = []

    class DialogoFalso:
        def __init__(self, padre, resultados, carpeta, al_abrir):
            creados.append(resultados)

    def exportar_con_fallo(self, trabajos, cancelar=None):
        self.trabajos = trabajos
        return [ResultadoClip(trabajos[0], True, ruta="a"),
                ResultadoClip(trabajos[1], False, error="ffmpeg falló")]

    with _con_cola_falsa(), mock.patch.object(
            app_mod, "DialogoResultadoExportacion", DialogoFalso):
        with mock.patch.object(ColaFalsa, "exportar", exportar_con_fallo):
            app._hilo_exportar(CLIPS, "video.mp4", SEGMENTOS, False)
            app._procesar_cola()  # el diálogo va por la cola de UI
    assert len(creados) == 1
    resultados = creados[0]
    assert sum(1 for r in resultados if r.ok) == 1
    assert [r for r in resultados if not r.ok][0].error == "ffmpeg falló"


def test_hilo_exportar_cancelado_no_muestra_dialogo(app, tmp_path):
    ColaFalsa.instancias.clear()

    def exportar_cancelado(self, trabajos, cancelar=None):
        self.trabajos = trabajos
        return [ResultadoClip(t, False, cancelado=True) for t in trabajos]

    with _con_cola_falsa(), mock.patch.object(
            app_mod, "DialogoResultadoExportacion") as dialogo:
        with mock.patch.object(ColaFalsa, "exportar", exportar_cancelado):
            app._hilo_exportar(CLIPS, "video.mp4", SEGMENTOS, False)
            app._procesar_cola()  # el estado va por la cola de UI
    dialogo.assert_not_called()
    assert "cancelada" in app.etiqueta_estado.cget("text").lower()


def test_boton_cancelar_marca_el_evento(app):
    app._cancelar_exportacion = threading.Event()
    app.boton_cancelar.configure(state="normal")
    app._cancelar_exportar()
    assert app._cancelar_exportacion.is_set()
    assert str(app.boton_cancelar.cget("state")) == "disabled"


def test_exportar_habilita_boton_cancelar(app, tmp_path, monkeypatch):
    """_exportar habilita el botón Cancelar antes de lanzar el hilo."""
    import tkinter as tk

    ColaFalsa.instancias.clear()
    app.carpeta_salida = str(tmp_path)
    app.ruta_video = "video.mp4"
    app.candidatos = list(CLIPS)
    app.segmentos = list(SEGMENTOS)
    app.seleccion = [tk.BooleanVar(value=True) for _ in CLIPS]
    monkeypatch.setattr(app_mod, "ColaExportacion", ColaFalsa)
    monkeypatch.setattr(app_mod, "DialogoResultadoExportacion",
                        lambda *a: None)
    app._exportar()
    assert str(app.boton_cancelar.cget("state")) == "normal"
    assert app._cancelar_exportacion is not None
    # Esperar a que el hilo termine y procesar la cola de UI.
    for _ in range(100):
        app.update()
        time.sleep(0.05)
        if not app.ocupado:
            break
    app._procesar_cola()
    assert str(app.boton_cancelar.cget("state")) == "disabled"
