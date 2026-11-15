"""Tests del logging rotativo (clipia/logs.py)."""
import logging
import os

from clipia.logs import carpeta_logs, configurar_logging, obtener_log


def _cerrar_logger(logger):
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()


def test_carpeta_logs_respeta_localappdata(monkeypatch, tmp_path):
    """Con LOCALAPPDATA, los logs van a %LOCALAPPDATA%/ClipIA/logs."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert carpeta_logs() == os.path.join(str(tmp_path), "ClipIA", "logs")


def test_carpeta_logs_sin_localappdata_usa_home(monkeypatch, tmp_path):
    """Sin LOCALAPPDATA (Linux), los logs van a ~/.local/share/ClipIA."""
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    # En Windows expanduser("~") ignora HOME y usa USERPROFILE.
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    assert carpeta_logs() == os.path.join(str(tmp_path), ".local", "share",
                                          "ClipIA", "logs")


def test_configurar_logging_crea_archivo_y_escribe(monkeypatch, tmp_path):
    """configurar_logging crea clipia.log y el mensaje queda en el
    archivo."""
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    logger = configurar_logging(nombre="clipia_test_archivo")
    try:
        logger.info("mensaje de prueba 123")
        ruta_log = os.path.join(carpeta_logs(), "clipia.log")
        assert os.path.exists(ruta_log)
        with open(ruta_log, encoding="utf-8") as f:
            assert "mensaje de prueba 123" in f.read()
    finally:
        _cerrar_logger(logger)


def test_configurar_logging_es_idempotente(monkeypatch, tmp_path):
    """Llamar dos veces no duplica los handlers."""
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    logger = configurar_logging(nombre="clipia_test_idem")
    try:
        assert len(logger.handlers) == 2  # consola + archivo
        configurar_logging(nombre="clipia_test_idem")
        assert len(logger.handlers) == 2
    finally:
        _cerrar_logger(logger)


def test_obtener_log_devuelve_hijo_de_clipia():
    """obtener_log('gui') es el logger clipia.gui."""
    assert obtener_log("gui").name == "clipia.gui"
    assert obtener_log().name == "clipia"
    assert isinstance(obtener_log("gui"), logging.Logger)
