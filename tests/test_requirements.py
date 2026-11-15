# -*- coding: utf-8 -*-
"""Tests de requirements.txt (B7 y regla de versiones fijadas)."""
import os

import ctranslate2
import numpy

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def leer_requirements():
    paquetes = {}
    with open(os.path.join(RAIZ, "requirements.txt")) as f:
        for linea in f:
            linea = linea.strip()
            if not linea or linea.startswith("#"):
                continue
            nombre, _, version = linea.partition("==")
            paquetes[nombre.strip()] = version.strip()
    return paquetes


def test_numpy_y_ctranslate2_declarados_y_fijados():
    """B7: numpy y ctranslate2 están declarados con versión fijada
    (se importan directo en el código)."""
    paquetes = leer_requirements()
    assert "numpy" in paquetes and paquetes["numpy"], \
        "numpy no está declarado en requirements.txt"
    assert "ctranslate2" in paquetes and paquetes["ctranslate2"], \
        "ctranslate2 no está declarado en requirements.txt"


def test_versiones_fijadas_coinciden_con_lo_instalado():
    """Las versiones fijadas de numpy y ctranslate2 son las que
    realmente están instaladas y probadas en este entorno."""
    paquetes = leer_requirements()
    assert paquetes["numpy"] == numpy.__version__
    assert paquetes["ctranslate2"] == ctranslate2.__version__


def test_todas_las_dependencias_con_version_fijada():
    """Regla de la casa: toda dependencia lleva == versión (nada de
    rangos que cambien la instalación entre un día y otro)."""
    with open(os.path.join(RAIZ, "requirements.txt")) as f:
        for linea in f:
            linea = linea.strip()
            if not linea or linea.startswith("#"):
                continue
            assert "==" in linea, "dependencia sin versión fijada: %s" % linea
