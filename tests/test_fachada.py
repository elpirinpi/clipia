# -*- coding: utf-8 -*-
"""Tests de la fachada clipia_core.py (división en paquete, Fase 0)."""
import clipia
import clipia_core as core


def test_fachada_reexporta_la_api_publica():
    """clipia_core expone las mismas funciones que el paquete clipia."""
    for nombre in clipia.__all__:
        assert getattr(core, nombre) is getattr(clipia, nombre), nombre


def test_fachada_reexporta_nombres_privados_usados_por_tests():
    """Los nombres con guion bajo que usan los tests siguen existiendo
    en clipia_core (son parte de la API interna estable)."""
    for nombre in ("_puntuar_ventana", "_traslapan", "_frases_de_segmentos",
                   "_fragmentos_subtitulo", "_expresion_rostros",
                   "_elegir_dispositivo", "_escapar_ruta_subtitulos"):
        assert hasattr(core, nombre), nombre


def test_fachada_expone_subprocess_para_mocks():
    """core.subprocess existe (los tests lo mockean para ffprobe)."""
    import subprocess

    assert core.subprocess is subprocess
