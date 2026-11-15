"""Tests estáticos del repositorio: CI, .gitignore y LICENSE."""
import os

import yaml

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_gitignore_cubre_venv_cache_y_salida():
    ruta = os.path.join(RAIZ, ".gitignore")
    with open(ruta, encoding="utf-8") as f:
        contenido = f.read()
    for marca in (".venv/", "__pycache__/", ".pytest_cache/", "salida/",
                  "diagnostico.log"):
        assert marca in contenido, ".gitignore no cubre %s" % marca


def test_license_es_mit():
    ruta = os.path.join(RAIZ, "LICENSE")
    with open(ruta, encoding="utf-8") as f:
        contenido = f.read()
    assert "MIT License" in contenido
    assert "Permission is hereby granted, free of charge" in contenido


def test_ci_es_windows_latest_con_ruff_y_pytest():
    ruta = os.path.join(RAIZ, ".github", "workflows", "ci.yml")
    with open(ruta, encoding="utf-8") as f:
        flujo = yaml.safe_load(f)
    job = flujo["jobs"]["test-windows"]
    assert job["runs-on"] == "windows-latest"
    pasos = " ".join(p.get("run", "") for p in job["steps"])
    assert "requirements.txt" in pasos
    assert "ruff check" in pasos
    assert "pytest" in pasos
    assert "3.12" in str(job["steps"])
    assert "ffmpeg" in pasos.lower()
