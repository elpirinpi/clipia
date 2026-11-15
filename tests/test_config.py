"""Tests de la configuración JSON (clipia/config.py)."""
import json
import os

from clipia.config import (
    VALORES_DEFECTO,
    cargar_config,
    guardar_config,
    ruta_config,
)


def test_valores_defecto_sin_archivo(tmp_path):
    """Sin archivo guardado, la config son los defectos."""
    assert cargar_config(str(tmp_path / "config.json")) == VALORES_DEFECTO


def test_cargar_config_mezcla_guardados(tmp_path):
    """Lo guardado sobrescribe solo sus claves; el resto son defectos."""
    ruta = tmp_path / "config.json"
    ruta.write_text(json.dumps({"modelo": "small", "idioma": "en"}),
                    encoding="utf-8")
    valores = cargar_config(str(ruta))
    assert valores["modelo"] == "small"
    assert valores["idioma"] == "en"
    assert valores["encoder"] == VALORES_DEFECTO["encoder"]
    assert valores["seguir_rostros"] == VALORES_DEFECTO["seguir_rostros"]


def test_cargar_config_json_corrupto_devuelve_defectos(tmp_path):
    """Un config.json corrupto se ignora (no rompe el arranque)."""
    ruta = tmp_path / "config.json"
    ruta.write_text("{esto no es json", encoding="utf-8")
    assert cargar_config(str(ruta)) == VALORES_DEFECTO


def test_cargar_config_ignora_claves_desconocidas(tmp_path):
    """Las claves que no son del esquema no entran en la config."""
    ruta = tmp_path / "config.json"
    ruta.write_text(json.dumps({"foo": 1, "modelo": "tiny"}),
                    encoding="utf-8")
    valores = cargar_config(str(ruta))
    assert "foo" not in valores
    assert valores["modelo"] == "tiny"


def test_guardar_config_redondo(tmp_path):
    """Guardar y volver a cargar devuelve los mismos valores."""
    ruta = str(tmp_path / "config.json")
    valores = dict(VALORES_DEFECTO, modelo="small", seguir_rostros=False,
                   carpeta_salida=str(tmp_path / "clips"))
    assert guardar_config(valores, ruta) == ruta
    assert cargar_config(ruta) == valores


def test_guardar_config_crea_carpetas(tmp_path):
    """guardar_config crea las carpetas intermedias que falten."""
    ruta = str(tmp_path / "a" / "b" / "config.json")
    guardar_config(VALORES_DEFECTO, ruta)
    assert os.path.exists(ruta)


def test_guardar_config_no_deja_tmp(tmp_path):
    """La escritura atómica no deja el archivo .tmp."""
    ruta = str(tmp_path / "config.json")
    guardar_config(VALORES_DEFECTO, ruta)
    assert not os.path.exists(ruta + ".tmp")


def test_ruta_config_respeta_appdata(monkeypatch, tmp_path):
    """Con APPDATA definido, la config va a %APPDATA%/ClipIA."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert ruta_config() == os.path.join(str(tmp_path), "ClipIA",
                                         "config.json")


def test_ruta_config_sin_appdata_usa_home(monkeypatch, tmp_path):
    """Sin APPDATA (Linux), la config va a ~/.config/ClipIA."""
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    # En Windows expanduser("~") ignora HOME y usa USERPROFILE.
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    assert ruta_config() == os.path.join(str(tmp_path), ".config",
                                         "ClipIA", "config.json")
