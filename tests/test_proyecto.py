"""Tests de guardar/cargar proyecto (.clipia, Fase 3). Sin GUI."""
import json

import pytest

from clipia.proyecto import (
    VERSION_PROYECTO,
    cargar_proyecto,
    guardar_proyecto,
)

SEGMENTOS = [{"start": 0.0, "end": 5.0, "text": "Hola mundo.",
              "words": [{"word": "Hola", "start": 0.0, "end": 0.5}]}]

PROYECTO = {
    "videos": [{"ruta": "C:/videos/uno.mp4", "duracion": 120.0,
                "segmentos": SEGMENTOS}],
    "candidatos": [{"start": 1.0, "end": 6.0, "score": 0.9,
                    "text": "Hola mundo.", "video": "C:/videos/uno.mp4"}],
    "seleccion": [False],
    "carpeta_salida": "C:/videos/salida",
}


def test_guardar_y_cargar_round_trip(tmp_path):
    ruta = str(tmp_path / "proyecto.clipia")
    assert guardar_proyecto(ruta, PROYECTO) == ruta
    cargado = cargar_proyecto(ruta)
    assert cargado["version"] == VERSION_PROYECTO
    assert cargado["videos"] == PROYECTO["videos"]
    assert cargado["candidatos"] == PROYECTO["candidatos"]
    assert cargado["seleccion"] == [False]
    assert cargado["carpeta_salida"] == "C:/videos/salida"
    # No queda archivo temporal tras el guardado atómico.
    assert not (tmp_path / "proyecto.clipia.tmp").exists()


def test_cargar_archivo_inexistente(tmp_path):
    with pytest.raises(ValueError, match="No se pudo leer"):
        cargar_proyecto(str(tmp_path / "no_existe.clipia"))


def test_cargar_json_invalido(tmp_path):
    ruta = tmp_path / "roto.clipia"
    ruta.write_text("{esto no es json", encoding="utf-8")
    with pytest.raises(ValueError, match="No se pudo leer"):
        cargar_proyecto(str(ruta))


def test_cargar_version_distinta(tmp_path):
    ruta = tmp_path / "viejo.clipia"
    datos = dict(PROYECTO, version=99)
    ruta.write_text(json.dumps(datos), encoding="utf-8")
    with pytest.raises(ValueError, match="otra versión"):
        cargar_proyecto(str(ruta))


def test_cargar_sin_listas(tmp_path):
    ruta = tmp_path / "mal.clipia"
    datos = {"version": VERSION_PROYECTO, "videos": "no es lista",
             "candidatos": []}
    ruta.write_text(json.dumps(datos), encoding="utf-8")
    with pytest.raises(ValueError, match="lista de videos"):
        cargar_proyecto(str(ruta))


def test_cargar_clip_sin_tiempos(tmp_path):
    ruta = tmp_path / "mal.clipia"
    datos = {"version": VERSION_PROYECTO, "videos": [],
             "candidatos": [{"text": "sin tiempos"}]}
    ruta.write_text(json.dumps(datos), encoding="utf-8")
    with pytest.raises(ValueError, match="inicio/fin"):
        cargar_proyecto(str(ruta))


def test_cargar_seleccion_corta_se_rellena(tmp_path):
    ruta = tmp_path / "proyecto.clipia"
    datos = dict(PROYECTO)
    datos["candidatos"] = list(PROYECTO["candidatos"]) * 3
    datos["seleccion"] = [False]
    guardar_proyecto(str(ruta), datos)
    assert cargar_proyecto(str(ruta))["seleccion"] == [False, True, True]


def test_cargar_video_incompleto(tmp_path):
    ruta = tmp_path / "mal.clipia"
    datos = {"version": VERSION_PROYECTO,
             "videos": [{"ruta": "v.mp4"}], "candidatos": []}
    ruta.write_text(json.dumps(datos), encoding="utf-8")
    with pytest.raises(ValueError, match="incompleto"):
        cargar_proyecto(str(ruta))
