"""Tests del registro de procesos hijos (Fase 1, p1-06)."""
import os
import subprocess
import sys
import threading
import time

import pytest

from clipia.procesos import contar, ejecutar, matar_todos, olvidar, registrar

VIDEO_PRUEBA = os.path.expanduser(
    "~/workspace/clipia-test/video_prueba.mp4")


def _dormir(segundos=60):
    """Un proceso hijo que duerme (multiplataforma)."""
    return subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(%d)" % segundos])


def test_registrar_olvidar_contar():
    proceso = _dormir()
    try:
        assert contar() == 0
        assert registrar(proceso) is proceso
        assert contar() == 1
        olvidar(proceso)
        assert contar() == 0
    finally:
        proceso.kill()
        proceso.wait()


def test_matar_todos_termina_procesos_reales():
    a, b = _dormir(), _dormir()
    registrar(a)
    registrar(b)
    assert contar() == 2
    matar_todos()
    assert contar() == 0
    assert a.poll() is not None
    assert b.poll() is not None


def test_matar_todos_mata_al_que_ignora_terminate():
    """Un proceso que ignora SIGTERM muere por kill tras el timeout."""
    if os.name == "nt":
        pytest.skip("en Windows terminate ya es kill")
    proceso = subprocess.Popen(
        [sys.executable, "-c",
         "import signal, time; "
         "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
         "time.sleep(60)"])
    registrar(proceso)
    t0 = time.time()
    matar_todos(timeout=0.5)
    assert time.time() - t0 < 5
    assert proceso.poll() is not None


def test_ejecutar_como_subprocess_run():
    resultado = ejecutar([sys.executable, "-c", "print('hola')"],
                         capture_output=True, text=True, check=True)
    assert resultado.returncode == 0
    assert resultado.stdout.strip() == "hola"
    assert contar() == 0


def test_ejecutar_check_falla_lanza_called_process_error():
    with pytest.raises(subprocess.CalledProcessError):
        ejecutar([sys.executable, "-c", "raise SystemExit(3)"],
                 check=True)
    assert contar() == 0


def test_ejecutar_timeout_mata_el_proceso():
    with pytest.raises(subprocess.TimeoutExpired):
        ejecutar([sys.executable, "-c", "import time; time.sleep(60)"],
                 timeout=0.5)
    assert contar() == 0


def test_exportar_registra_el_ffmpeg_mientras_corre(tmp_path):
    """Durante una exportación real hay un proceso registrado; al
    cancelar, el registro queda vacío (sin huérfanos)."""
    if not os.path.isfile(VIDEO_PRUEBA):
        pytest.skip("solo local: necesita el video de prueba")
    import clipia_core as core

    cancelar = threading.Event()
    salida = str(tmp_path / "clip.mp4")
    errores = []

    def trabajo():
        try:
            core.exportar_clip(VIDEO_PRUEBA, 0, 30, None, salida,
                               con_subtitulos=False, cancelar=cancelar)
        except Exception as error:  # noqa: BLE001 - se comprueba luego
            errores.append(error)

    hilo = threading.Thread(target=trabajo, daemon=True)
    hilo.start()
    try:
        for _ in range(50):
            if contar() >= 1:
                break
            time.sleep(0.1)
        assert contar() >= 1, "el ffmpeg de exportación no se registró"
        cancelar.set()
        hilo.join(timeout=15)
        assert not hilo.is_alive()
        assert errores and isinstance(errores[0],
                                      core.ExportacionCancelada)
        assert contar() == 0
    finally:
        cancelar.set()
        hilo.join(timeout=15)


def test_al_cerrar_mata_los_ffmpeg_registrados(app):
    """Cerrar la app mata los procesos registrados y marca la
    cancelación de la exportación."""
    proceso = _dormir()
    registrar(proceso)
    app._cancelar_exportacion = threading.Event()
    app._al_cerrar()
    assert app._cancelar_exportacion.is_set()
    assert proceso.poll() is not None
    assert contar() == 0
