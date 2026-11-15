# -*- coding: utf-8 -*-
"""Tests de GUI del hilo de exportación (B3, B10).

Necesitan pantalla: en Linux correr con xvfb-run -a; en Windows (CI)
corren con el escritorio del runner.
"""
import os
from unittest import mock

import pytest

import main as app_mod


@pytest.fixture
def app(tmp_path, monkeypatch):
    """App real con HOME temporal (no toca la carpeta del usuario)."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    aplicacion = app_mod.AppClipIA()
    aplicacion.withdraw()
    aplicacion.carpeta_salida = str(tmp_path / "salida")
    os.makedirs(aplicacion.carpeta_salida, exist_ok=True)
    yield aplicacion
    aplicacion.destroy()


def test_hilo_exportar_usa_ass_temporal_unico_por_clip(app, tmp_path):
    """B3: cada clip usa su propio ASS temporal y se borra al terminar;
    ya no existe el clip_tmp.ass compartido."""
    segmentos = [{"start": 0.0, "end": 10.0, "text": "hola mundo",
                  "words": []}]
    clips = [{"start": 0.0, "end": 5.0, "score": 1.0, "text": "uno"},
             {"start": 5.0, "end": 10.0, "score": 1.0, "text": "dos"}]
    rutas_ass = []

    def falso_exportar(ruta_video, inicio, fin, ruta_ass, ruta_salida,
                       progreso=None, rostros=None, **kwargs):
        rutas_ass.append(ruta_ass)
        assert os.path.isfile(ruta_ass)
        return ruta_salida

    with mock.patch.object(app_mod.core, "exportar_clip",
                           side_effect=falso_exportar):
        app._hilo_exportar(clips, "video.mp4", segmentos, False)
    assert len(rutas_ass) == 2
    assert rutas_ass[0] != rutas_ass[1]
    assert not os.path.exists(rutas_ass[0])
    assert not os.path.exists(rutas_ass[1])
    assert not os.path.exists(
        os.path.join(app.carpeta_salida, "clip_tmp.ass"))


def test_hilo_exportar_borra_ass_aunque_falle(app):
    """B3: si la exportación de un clip falla, su ASS temporal se borra
    igualmente (try/finally)."""
    segmentos = [{"start": 0.0, "end": 10.0, "text": "hola mundo",
                  "words": []}]
    clips = [{"start": 0.0, "end": 5.0, "score": 1.0, "text": "uno"},
             {"start": 5.0, "end": 10.0, "score": 1.0, "text": "dos"}]
    rutas_ass = []

    def falso_exportar(ruta_video, inicio, fin, ruta_ass, ruta_salida,
                       progreso=None, rostros=None, **kwargs):
        rutas_ass.append(ruta_ass)
        if len(rutas_ass) == 2:
            raise RuntimeError("fallo provocado")
        return ruta_salida

    with mock.patch.object(app_mod.core, "exportar_clip",
                           side_effect=falso_exportar):
        app._hilo_exportar(clips, "video.mp4", segmentos, False)
    assert len(rutas_ass) == 2
    assert not os.path.exists(rutas_ass[0])
    assert not os.path.exists(rutas_ass[1])
