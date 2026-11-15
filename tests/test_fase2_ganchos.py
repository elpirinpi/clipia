"""Fase 2: limpieza de PALABRAS_GANCHO + ponderación por rareza (idf)."""
import pytest

from clipia.momentos import (
    PALABRAS_GANCHO,
    _idf_ganchos,
    _puntuar_ventana,
    detectar_momentos,
)

ELIMINADAS = {"te", "voy", "pasa", "paso", "todos", "ahora", "nuevo"}


def test_palabras_genericas_fuera():
    assert not (ELIMINADAS & PALABRAS_GANCHO)


def test_palabras_gancho_utiles_siguen():
    for palabra in ("dinero", "secreto", "increíble", "truco", "gratis",
                    "importante", "misterio", "error"):
        assert palabra in PALABRAS_GANCHO


def _frase(inicio, texto):
    return {"start": inicio, "end": inicio + 5, "text": texto}


def test_idf_raro_pesa_mas_que_comun():
    frases = ([_frase(i * 5, "dinero dinero dinero") for i in range(39)]
              + [_frase(195, "secreto revelado")])
    idf = _idf_ganchos(frases)
    assert idf["dinero"] < idf["secreto"]
    assert idf["dinero"] == pytest.approx(1.0, abs=0.05)
    assert idf["secreto"] > 3.0


def test_idf_sin_ganchos_es_vacio():
    assert _idf_ganchos([_frase(0, "hola mundo")]) == {}


def test_puntuar_con_idf_raro_supera_a_comun():
    frases = ([_frase(i * 5, "dinero dinero") for i in range(10)]
              + [_frase(50, "secreto misterio")])
    idf = _idf_ganchos(frases)
    comun = _puntuar_ventana(frases, 0, 10, idf=idf)
    raro = _puntuar_ventana(frases, 50, 60, idf=idf)
    assert raro > comun


def test_puntuar_sin_idf_igual_que_antes():
    # Sin idf, 4 ganchos dan el máximo del componente (0.30).
    puntos = _puntuar_ventana(
        [_frase(0, "increíble dinero truco misterio")], 0, 30)
    assert puntos == pytest.approx(0.30 + 0.45 * (4 / 30) / 3)


def test_puntuar_con_idf_cuatro_raros_llegan_al_maximo():
    frases = [_frase(i * 5, "palabra comun") for i in range(40)]
    frases.append(_frase(200, "increíble secreto misterio truco"))
    idf = _idf_ganchos(frases)
    puntos = _puntuar_ventana(frases, 200, 230, idf=idf)
    # 4 ganchos muy raros: componente de gancho al máximo (0.30).
    assert puntos == pytest.approx(0.30 + 0.45 * (4 / 30) / 3, abs=0.01)


def test_detectar_momentos_usa_idf():
    # Dos zonas: una repite "dinero" en todas las frases (común) y
    # otra dice "secreto" una sola vez (raro). Con la misma densidad,
    # la zona rara debe quedar primero.
    frases_texto = []
    for _i in range(12):
        frases_texto.append("dinero dinero dinero dinero")
    frases_texto.append("esto es un secreto increíble de verdad")
    palabras = []
    t = 0.0
    for texto in frases_texto:
        for token in texto.split():
            palabras.append({"word": " " + token, "start": t,
                             "end": t + 0.4})
            t += 0.5
        palabras[-1]["word"] += "."
    segmentos = [{"start": 0.0, "end": t, "text": " ".join(
        p["word"] for p in palabras), "words": palabras}]
    candidatos = detectar_momentos(segmentos, t, cantidad=3)
    assert candidatos
    # El mejor candidato debe incluir la frase del secreto.
    assert "secreto" in candidatos[0]["text"]


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
