"""Tests de obtener_duracion (B8)."""
from unittest import mock

import pytest
from conftest import video_sintetico

import clipia_core as core


def _resultado_ffprobe(salida, codigo=0, error=""):
    resultado = mock.Mock()
    resultado.returncode = codigo
    resultado.stdout = salida
    resultado.stderr = error
    return resultado


def test_obtener_duracion_formato_normal():
    """Caso normal: format=duration devuelve un número."""
    with mock.patch.object(core.subprocess, "run") as mock_run:
        mock_run.return_value = _resultado_ffprobe("60.5\n")
        assert core.obtener_duracion("video.mp4") == 60.5
    assert mock_run.call_count == 1


def test_obtener_duracion_na_usa_flujo_de_video():
    """B8: si format=duration es "N/A" (MKV/WebM), se usa la duración
    del primer flujo de video en vez de reventar con float("N/A")."""
    with mock.patch.object(core.subprocess, "run") as mock_run:
        mock_run.side_effect = [
            _resultado_ffprobe("N/A\n"),
            _resultado_ffprobe("123.45\n"),
        ]
        assert core.obtener_duracion("video.mkv") == 123.45
    assert mock_run.call_count == 2
    segunda_llamada = mock_run.call_args_list[1].args[0]
    assert "stream=duration" in segunda_llamada
    assert "v:0" in segunda_llamada


def test_obtener_duracion_na_en_ambos_da_error_claro():
    """B8: si ni el formato ni el flujo dan duración, error claro
    en vez de ValueError de float()."""
    with mock.patch.object(core.subprocess, "run") as mock_run:
        mock_run.side_effect = [
            _resultado_ffprobe("N/A\n"),
            _resultado_ffprobe("N/A\n"),
        ]
        with pytest.raises(RuntimeError, match="no pudo determinar"):
            core.obtener_duracion("video.webm")


def test_obtener_duracion_ffprobe_falla():
    """Si ffprobe falla, el error de ffprobe se propaga."""
    with mock.patch.object(core.subprocess, "run") as mock_run:
        mock_run.return_value = _resultado_ffprobe(
            "", codigo=1, error="no such file")
        with pytest.raises(RuntimeError, match="no such file"):
            core.obtener_duracion("no_existe.mp4")


def test_obtener_duracion_video_real(tmp_path):
    """Happy path con un video sintético real de 5 s."""
    ruta = video_sintetico(tmp_path / "sintetico.mp4", duracion=5.0)
    assert abs(core.obtener_duracion(ruta) - 5.0) < 0.2
