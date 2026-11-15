"""Tests de la cola de exportación (Fase 1)."""
import os
import tempfile
import threading
import time

from clipia.cola import (
    ColaExportacion,
    TrabajoExportacion,
    workers_efectivos,
    workers_recomendados,
)
from clipia.exportacion import ExportacionCancelada


def trabajo(nombre, inicio=0.0, fin=5.0, reintentos=1):
    return TrabajoExportacion(
        clip={"start": inicio, "end": fin, "score": 1.0, "text": nombre},
        ruta_video="video.mp4", segmentos=[],
        carpeta_salida="", nombre=nombre,
        seguir_rostros=False, reintentos=reintentos)


def test_workers_recomendados():
    assert workers_recomendados("libx264") == 1
    assert workers_recomendados("h264_nvenc") == 2
    assert workers_recomendados("h264_qsv") == 2
    assert workers_recomendados("h264_amf") == 2


def test_workers_efectivos():
    assert workers_efectivos(0, "libx264") == 1
    assert workers_efectivos(0, "h264_nvenc") == 2
    assert workers_efectivos(2, "libx264") == 2
    assert workers_efectivos(9, "h264_nvenc") == 3
    assert workers_efectivos(-1, "h264_nvenc") == 2


def test_exportar_lote_ok_y_en_orden(tmp_path):
    """Los resultados vuelven en el orden de entrada, con sus rutas."""
    trabajos = [trabajo("clip1.mp4"), trabajo("clip2.mp4"),
                trabajo("clip3.mp4")]
    for t in trabajos:
        t.carpeta_salida = str(tmp_path)

    def falso_exportar(ruta_video, inicio, fin, ruta_ass, ruta_salida,
                       progreso=None, rostros=None, encoder=None,
                       cancelar=None):
        if progreso:
            progreso(0.5)
            progreso(1.0)
        with open(ruta_salida, "wb") as archivo:
            archivo.write(b"fake")
        return ruta_salida

    cola = ColaExportacion(workers=2, exportar=falso_exportar,
                           generar_ass=lambda *a: None)
    resultados = cola.exportar(trabajos)
    assert [r.trabajo.nombre for r in resultados] == [
        "clip1.mp4", "clip2.mp4", "clip3.mp4"]
    assert all(r.ok for r in resultados)
    assert all(os.path.isfile(r.ruta) for r in resultados)


def test_ass_unico_por_clip_y_siempre_borrado(tmp_path):
    """B3 (movido aquí): cada clip usa su propio ASS temporal, borrado
    al terminar aunque falle."""
    trabajos = [trabajo("clip1.mp4"), trabajo("clip2.mp4")]
    for t in trabajos:
        t.carpeta_salida = str(tmp_path)
    rutas_ass = []

    def falso_exportar(ruta_video, inicio, fin, ruta_ass, ruta_salida,
                       progreso=None, rostros=None, encoder=None,
                       cancelar=None):
        rutas_ass.append(ruta_ass)
        assert os.path.isfile(ruta_ass)
        if len(rutas_ass) == 2:
            raise RuntimeError("fallo provocado")
        return ruta_salida

    cola = ColaExportacion(workers=1, exportar=falso_exportar,
                           generar_ass=lambda *a: None)
    cola.exportar(trabajos)
    assert len(rutas_ass) == 3  # el 2º clip se reintentó una vez
    assert len(set(rutas_ass)) == 3
    assert not any(os.path.exists(r) for r in rutas_ass)


def test_reintento_por_clip_sin_tumbar_el_lote(tmp_path):
    """Un clip que falla en el primer intento se reintenta y sale bien;
    el resto del lote no se entera."""
    trabajos = [trabajo("clip1.mp4"), trabajo("clip2.mp4")]
    for t in trabajos:
        t.carpeta_salida = str(tmp_path)
    intentos = {}

    def falso_exportar(ruta_video, inicio, fin, ruta_ass, ruta_salida,
                       progreso=None, rostros=None, encoder=None,
                       cancelar=None):
        nombre = os.path.basename(ruta_salida)
        intentos[nombre] = intentos.get(nombre, 0) + 1
        if nombre == "clip2.mp4" and intentos[nombre] == 1:
            raise RuntimeError("fallo transitorio")
        return ruta_salida

    cola = ColaExportacion(workers=1, exportar=falso_exportar,
                           generar_ass=lambda *a: None)
    resultados = cola.exportar(trabajos)
    assert all(r.ok for r in resultados)
    assert intentos == {"clip1.mp4": 1, "clip2.mp4": 2}


def test_fallo_definitivo_no_tumba_el_lote(tmp_path):
    """Un clip que falla incluso tras el reintento queda marcado con
    su error; los demás se exportan."""
    trabajos = [trabajo("clip1.mp4"), trabajo("clip2.mp4"),
                trabajo("clip3.mp4")]
    for t in trabajos:
        t.carpeta_salida = str(tmp_path)

    def falso_exportar(ruta_video, inicio, fin, ruta_ass, ruta_salida,
                       progreso=None, rostros=None, encoder=None,
                       cancelar=None):
        if ruta_salida.endswith("clip2.mp4"):
            raise RuntimeError("siempre falla")
        return ruta_salida

    cola = ColaExportacion(workers=1, exportar=falso_exportar,
                           generar_ass=lambda *a: None)
    resultados = cola.exportar(trabajos)
    assert [r.ok for r in resultados] == [True, False, True]
    assert resultados[1].error == "siempre falla"
    assert not resultados[1].cancelado


def test_cancelar_antes_de_empezar(tmp_path):
    """Con el evento ya marcado, ningún clip se exporta."""
    trabajos = [trabajo("clip1.mp4"), trabajo("clip2.mp4")]
    for t in trabajos:
        t.carpeta_salida = str(tmp_path)
    llamadas = []

    def falso_exportar(*a, **k):
        llamadas.append(1)
        return a[4]

    cola = ColaExportacion(workers=1, exportar=falso_exportar,
                           generar_ass=lambda *a: None)
    cancelar = threading.Event()
    cancelar.set()
    resultados = cola.exportar(trabajos, cancelar)
    assert all(r.cancelado for r in resultados)
    assert not llamadas


def test_cancelar_a_mitad_no_empieza_los_pendientes(tmp_path):
    """Cancelar durante el 1er clip: ese queda cancelado y el 2º no se
    empieza."""
    trabajos = [trabajo("clip1.mp4"), trabajo("clip2.mp4")]
    for t in trabajos:
        t.carpeta_salida = str(tmp_path)
    cancelar = threading.Event()
    empezados = []

    def falso_exportar(ruta_video, inicio, fin, ruta_ass, ruta_salida,
                       progreso=None, rostros=None, encoder=None,
                       cancelar=None):
        empezados.append(os.path.basename(ruta_salida))
        # Simula un ffmpeg en curso: espera a que se cancele.
        cancelar.wait(timeout=5)
        raise ExportacionCancelada("cancelado")

    cola = ColaExportacion(workers=1, exportar=falso_exportar,
                           generar_ass=lambda *a: None)
    resultados = []
    hilo = threading.Thread(
        target=lambda: resultados.extend(cola.exportar(trabajos, cancelar)),
        daemon=True)
    hilo.start()
    time.sleep(0.3)
    cancelar.set()
    hilo.join(timeout=10)
    assert not hilo.is_alive()
    assert [r.cancelado for r in resultados] == [True, True]
    assert empezados == ["clip1.mp4"]


def test_progreso_global_monotono_y_con_eta(tmp_path):
    """El progreso global sube de 0 a 1, con terminados y ETA."""
    trabajos = [trabajo("clip1.mp4"), trabajo("clip2.mp4")]
    for t in trabajos:
        t.carpeta_salida = str(tmp_path)
    avisos = []

    def falso_exportar(ruta_video, inicio, fin, ruta_ass, ruta_salida,
                       progreso=None, rostros=None, encoder=None,
                       cancelar=None):
        time.sleep(0.05)
        if progreso:
            progreso(0.5)
            progreso(1.0)
        return ruta_salida

    cola = ColaExportacion(
        workers=1, exportar=falso_exportar,
        generar_ass=lambda *a: None,
        al_progreso=lambda f, e, t, n, c: avisos.append((f, e, t, n, c)))
    cola.exportar(trabajos)
    fracciones = [a[0] for a in avisos]
    assert fracciones == sorted(fracciones)
    assert fracciones[-1] == 1.0
    assert avisos[-1][2] == 2  # terminados
    assert avisos[-1][3] == 2  # total
    assert any(a[1] is not None for a in avisos), "debe haber ETA"
    assert any(a[4] for a in avisos), "debe listar clips en curso"


def test_no_quedan_ass_temporales_tras_el_lote(tmp_path):
    """Tras un lote completo no queda ningún clipia_sub_*.ass."""
    trabajos = [trabajo("clip1.mp4")]
    trabajos[0].carpeta_salida = str(tmp_path)
    antes = {f for f in os.listdir(tempfile.gettempdir())
             if f.startswith("clipia_sub_")}
    cola = ColaExportacion(workers=1,
                           exportar=lambda *a, **k: a[4],
                           generar_ass=lambda *a: None)
    cola.exportar(trabajos)
    despues = {f for f in os.listdir(tempfile.gettempdir())
               if f.startswith("clipia_sub_")}
    assert despues == antes
