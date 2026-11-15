"""Tests del binario externo de yt-dlp y su actualización (Fase 4).

Sin red ni Windows real: el binario y los subprocesos van mockeados,
y os.name se finge "nt" donde hace falta.
"""
import os
import subprocess
import sys
from unittest import mock

import pytest
import yt_dlp

import clipia_core as core
from clipia import descarga as descarga_mod
from clipia.descarga import ErrorDescarga


@pytest.fixture
def windows(monkeypatch):
    """Finge Windows: os.name "nt" y LOCALAPPDATA temporal."""
    monkeypatch.setattr(os, "name", "nt")
    return monkeypatch


def _respuesta_ok(stdout="", returncode=0):
    return subprocess.CompletedProcess([], returncode, stdout, "")


class _PopenFalso:
    """Popen falso para la ruta CLI: stdout con líneas dadas y
    returncode configurable."""

    def __init__(self, lineas, returncode=0):
        self._lineas = lineas
        self.returncode = returncode
        self.stdout = iter(lineas)
        self.args = None

    def wait(self, timeout=None):
        return self.returncode

    def poll(self):
        return self.returncode


# --- Detección del binario externo ---------------------------------------

def test_ruta_ytdlp_externo_en_linux_es_none(tmp_path, monkeypatch):
    """En Linux el .exe no puede ejecutarse: aunque exista el archivo,
    no se usa."""
    binario = tmp_path / "bin" / "yt-dlp.exe"
    binario.parent.mkdir()
    binario.write_bytes(b"MZ")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert descarga_mod.ruta_ytdlp_externo() is None


def test_ruta_ytdlp_externo_en_windows_usa_la_carpeta_bin(
        tmp_path, windows, monkeypatch):
    binario = tmp_path / "ClipIA" / "bin" / "yt-dlp.exe"
    binario.parent.mkdir(parents=True)
    binario.write_bytes(b"MZ")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert descarga_mod.ruta_ytdlp_externo() == str(binario)


def test_ruta_ytdlp_externo_prefiere_el_de_junto_a_la_app(
        tmp_path, windows, monkeypatch):
    """En el instalador, el binario junto al .exe gana al de la
    carpeta bin."""
    junto_app = tmp_path / "app" / "yt-dlp.exe"
    junto_app.parent.mkdir(parents=True)
    junto_app.write_bytes(b"MZ")
    en_bin = tmp_path / "ClipIA" / "bin" / "yt-dlp.exe"
    en_bin.parent.mkdir(parents=True)
    en_bin.write_bytes(b"MZ")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable",
                        str(tmp_path / "app" / "ClipIA.exe"))
    assert descarga_mod.ruta_ytdlp_externo() == str(junto_app)


def test_esta_congelado():
    assert descarga_mod.esta_congelado() is False


# --- Versión ---------------------------------------------------------------

def test_version_ytdlp_de_la_libreria():
    assert core.version_ytdlp() == yt_dlp.version.__version__


def test_version_ytdlp_del_binario_externo(monkeypatch):
    monkeypatch.setattr(descarga_mod, "ruta_ytdlp_externo",
                        lambda: "C:/ClipIA/yt-dlp.exe")
    with mock.patch.object(descarga_mod, "ejecutar",
                           return_value=_respuesta_ok(
                               "2026.11.01\n")) as ejecutar:
        assert core.version_ytdlp() == "2026.11.01"
    assert ejecutar.call_args.args[0][1] == "--version"


# --- Actualización ---------------------------------------------------------

def test_actualizar_ytdlp_en_dev_usa_pip(monkeypatch):
    """En modo dev: pip install -U y la versión se lee en un proceso
    aparte."""
    llamadas = []

    def ejecutar_falso(cmd, **kwargs):
        llamadas.append(cmd)
        if "-m" in cmd:
            return _respuesta_ok("Successfully installed\n")
        return _respuesta_ok("2026.11.05\n")

    monkeypatch.setattr(descarga_mod, "esta_congelado", lambda: False)
    with mock.patch.object(descarga_mod, "ejecutar",
                           side_effect=ejecutar_falso):
        assert core.actualizar_ytdlp() == "2026.11.05"
    assert llamadas[0][1:5] == ["-m", "pip", "install", "--upgrade"]
    assert llamadas[0][5] == "yt-dlp"
    assert llamadas[1][1] == "-c"


def test_actualizar_ytdlp_en_dev_falla_con_mensaje_accionable(monkeypatch):
    monkeypatch.setattr(descarga_mod, "esta_congelado", lambda: False)
    with mock.patch.object(descarga_mod, "ejecutar",
                           return_value=_respuesta_ok("", 1)):
        with pytest.raises(RuntimeError) as excinfo:
            core.actualizar_ytdlp()
    assert "conexión" in str(excinfo.value)


def test_actualizar_ytdlp_congelado_con_binario_usa_menos_u(monkeypatch):
    """En el instalador con binario: `yt-dlp -U` en su sitio."""
    monkeypatch.setattr(descarga_mod, "esta_congelado", lambda: True)
    monkeypatch.setattr(descarga_mod, "ruta_ytdlp_externo",
                        lambda: "C:/ClipIA/yt-dlp.exe")

    def ejecutar_falso(cmd, **kwargs):
        if cmd[1] == "-U":
            return _respuesta_ok("Updated to version 2026.11.06\n")
        return _respuesta_ok("2026.11.06\n")

    with mock.patch.object(descarga_mod, "ejecutar",
                           side_effect=ejecutar_falso):
        assert core.actualizar_ytdlp() == "2026.11.06"


def test_actualizar_ytdlp_congelado_sin_binario_lo_descarga(
        tmp_path, monkeypatch):
    """En el instalador sin binario: descarga yt-dlp.exe y lo deja
    en la carpeta bin (verificado: cabecera MZ y tamaño)."""
    datos = b"MZ" + b"\x00" * 1_500_000
    monkeypatch.setattr(descarga_mod, "esta_congelado", lambda: True)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    rutas = [None, str(tmp_path / "ClipIA" / "bin" / "yt-dlp.exe")]
    monkeypatch.setattr(descarga_mod, "ruta_ytdlp_externo",
                        lambda: rutas.pop(0))

    class _Respuesta:
        headers = {"Content-Length": str(len(datos))}

        def __init__(self):
            self._leido = False

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, _n):
            if self._leido:
                return b""
            self._leido = True
            return datos

    with mock.patch("urllib.request.urlopen",
                    return_value=_Respuesta()), \
            mock.patch.object(descarga_mod, "ejecutar",
                              return_value=_respuesta_ok(
                                  "2026.11.07\n")):
        assert core.actualizar_ytdlp() == "2026.11.07"
    binario = tmp_path / "ClipIA" / "bin" / "yt-dlp.exe"
    assert binario.exists()
    assert binario.read_bytes()[:2] == b"MZ"


def test_actualizar_ytdlp_rechaza_descarga_corrupta(
        tmp_path, monkeypatch):
    """Si lo descargado no es un .exe válido, se borra y se avisa."""
    datos = b"esto no es un ejecutable"
    monkeypatch.setattr(descarga_mod, "esta_congelado", lambda: True)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(descarga_mod, "ruta_ytdlp_externo",
                        lambda: None)

    class _Respuesta:
        headers = {"Content-Length": str(len(datos))}

        def __init__(self):
            self._leido = False

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, _n):
            if self._leido:
                return b""
            self._leido = True
            return datos

    with mock.patch("urllib.request.urlopen",
                    return_value=_Respuesta()):
        with pytest.raises(RuntimeError) as excinfo:
            core.actualizar_ytdlp()
    assert "no es válida" in str(excinfo.value)
    assert not (tmp_path / "ClipIA" / "bin" / "yt-dlp.exe").exists()


# --- Descarga por CLI ------------------------------------------------------

def test_descargar_con_binario_usa_cli_y_lee_el_avance(
        tmp_path, monkeypatch):
    """Con binario externo, la descarga va por CLI: se parsea el
    porcentaje y la ruta sale del --print-to-file (aquí, del respaldo:
    el mp4 más reciente)."""
    video = tmp_path / "descargas" / "video_final.mp4"
    video.parent.mkdir()
    video.write_bytes(b"falso")
    monkeypatch.setattr(descarga_mod, "ruta_ytdlp_externo",
                        lambda: "C:/ClipIA/yt-dlp.exe")
    lineas = ["[download]  10.0% of 10.00MiB at 1.00MiB/s ETA 00:09\n",
              "[download] 100.0% of 10.00MiB at 5.00MiB/s ETA 00:00\n"]
    avances = []
    with mock.patch.object(descarga_mod.subprocess, "Popen") as mock_popen:
        mock_popen.return_value = _PopenFalso(lineas)
        ruta = core.descargar_youtube(
            "https://www.youtube.com/watch?v=abc",
            str(video.parent), progreso=avances.append,
            navegador="chrome")
    assert ruta == str(video)
    assert avances[0] == pytest.approx(0.1)
    assert avances[-1] == 1.0
    comando = mock_popen.call_args.args[0]
    assert comando[0] == "C:/ClipIA/yt-dlp.exe"
    assert "--cookies-from-browser" in comando
    assert "chrome" in comando
    assert "--print-to-file" in comando
    assert "--no-playlist" in comando


def test_descargar_con_binario_traduce_el_error(tmp_path, monkeypatch):
    """Si el binario falla, el error sube como ErrorDescarga con su
    código (aquí: anti-bot)."""
    monkeypatch.setattr(descarga_mod, "ruta_ytdlp_externo",
                        lambda: "C:/ClipIA/yt-dlp.exe")
    lineas = ["ERROR: Sign in to confirm you're not a bot\n"]
    with mock.patch.object(descarga_mod.subprocess, "Popen") as mock_popen:
        mock_popen.return_value = _PopenFalso(lineas, returncode=1)
        with pytest.raises(ErrorDescarga) as excinfo:
            core.descargar_youtube("https://www.youtube.com/watch?v=abc",
                                   str(tmp_path))
    assert excinfo.value.codigo == "bot"
