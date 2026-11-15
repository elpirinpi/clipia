"""Fase 2: límites inteligentes (snap a frontera de frase).

Ningún candidato puede cortar a media frase: su inicio coincide con
el inicio de una frase y su fin con el fin de una frase (o con el fin
del video). Funciona también con la forma de segmentos que devuelve
BatchedInferencePipeline (pocos segmentos, largos, con word
timestamps).
"""
import pytest

from clipia.momentos import (
    _frases_de_segmentos,
    _snap_fin,
    detectar_momentos,
)


def _palabras(duracion, paso=0.5, frase_cada=10):
    """Palabras sintéticas con punto cada `frase_cada` palabras."""
    palabras = []
    i = 0
    while i * paso < duracion:
        texto = " palabra%d" % i
        if (i + 1) % frase_cada == 0:
            texto += "."
        palabras.append({"word": texto, "start": i * paso,
                         "end": i * paso + 0.4})
        i += 1
    return palabras


def _segmentos_batched(duracion):
    """Segmentos estilo BatchedInferencePipeline: 2 segmentos largos
    con todas las palabras (en el video de prueba real son 8)."""
    palabras = _palabras(duracion)
    mitad = len(palabras) // 2
    return [
        {"start": 0.0, "end": palabras[mitad - 1]["end"],
         "text": "".join(p["word"] for p in palabras[:mitad]),
         "words": palabras[:mitad]},
        {"start": palabras[mitad]["start"], "end": duracion,
         "text": "".join(p["word"] for p in palabras[mitad:]),
         "words": palabras[mitad:]},
    ]


def _cortes_a_media_frase(candidatos, frases):
    """Candidatos cuya frontera (inicio o fin) cae dentro de una frase."""
    malos = []
    for c in candidatos:
        for frontera in (c["start"], c["end"]):
            for f in frases:
                if f["start"] < frontera < f["end"]:
                    malos.append((c, frontera, f))
    return malos


def _frase(inicio, fin):
    return {"start": inicio, "end": fin, "text": "x", "words": []}


# -- _snap_fin ------------------------------------------------------------

def test_snap_fin_retrocede_a_la_frontera_anterior():
    frases = [_frase(0, 10), _frase(10, 20), _frase(20, 35), _frase(35, 50)]
    # Fin deseado 30: cae dentro de la frase 20-35 -> vuelve a 20... pero
    # eso deja 20 s (<25), así que se alarga a la siguiente frontera (35).
    assert _snap_fin(frases, 0, 30, 100) == 35.0
    # Con inicio en 10: fin deseado 40 -> 35 da 25 s, válido.
    assert _snap_fin(frases, 10, 40, 100) == 35.0


def test_snap_fin_no_recorta_si_ya_es_frontera():
    frases = [_frase(0, 10), _frase(10, 30), _frase(30, 60)]
    assert _snap_fin(frases, 0, 30, 100) == 30.0


def test_snap_fin_frase_larga_cubre_la_ventana():
    frases = [_frase(0, 100)]
    # La única frase cubre toda la ventana: el fin es el fin de la frase.
    assert _snap_fin(frases, 0, 30, 100) == 100.0


def test_snap_fin_al_final_del_video():
    frases = [_frase(0, 10), _frase(10, 20)]
    assert _snap_fin(frases, 0, 95, 90) == 90.0


def test_snap_fin_sin_frases_devuelve_el_deseado():
    assert _snap_fin([], 0, 30, 100) == 30.0


# -- detectar_momentos: 0 cortes a media frase -----------------------------

def test_momentos_sin_cortes_a_media_frase():
    segmentos = _segmentos_batched(180.0)
    frases = _frases_de_segmentos(segmentos)
    assert len(frases) > 5
    candidatos = detectar_momentos(segmentos, 180.0, cantidad=10)
    assert candidatos
    assert _cortes_a_media_frase(candidatos, frases) == []


def test_momentos_fronteras_son_fronteras_de_frase():
    segmentos = _segmentos_batched(180.0)
    frases = _frases_de_segmentos(segmentos)
    inicios = {round(f["start"], 6) for f in frases}
    fines = {round(f["end"], 6) for f in frases} | {180.0}
    for c in detectar_momentos(segmentos, 180.0, cantidad=10):
        assert round(c["start"], 6) in inicios
        assert round(c["end"], 6) in fines


def test_momentos_con_segmentos_cortos_tambien():
    # La forma antigua (muchos segmentos cortos) sigue funcionando.
    palabras = _palabras(120.0)
    segmentos = [{"start": p["start"], "end": p["end"], "text": p["word"],
                  "words": [p]} for p in palabras]
    frases = _frases_de_segmentos(segmentos)
    candidatos = detectar_momentos(segmentos, 120.0, cantidad=10)
    assert candidatos
    assert _cortes_a_media_frase(candidatos, frases) == []


def test_momentos_duracion_minima_tras_snap():
    segmentos = _segmentos_batched(180.0)
    for c in detectar_momentos(segmentos, 180.0, cantidad=10):
        assert c["end"] - c["start"] >= 25.0


def test_momentos_sin_palabras_no_revienta():
    segmentos = [{"start": 0.0, "end": 60.0, "text": "hola mundo",
                  "words": []},
                 {"start": 60.0, "end": 120.0, "text": "otra frase",
                  "words": []}]
    candidatos = detectar_momentos(segmentos, 120.0, cantidad=10)
    assert candidatos
    frases = _frases_de_segmentos(segmentos)
    assert _cortes_a_media_frase(candidatos, frases) == []


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
