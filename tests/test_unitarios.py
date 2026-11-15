"""Unitarios del núcleo: formatos, puntuación, fragmentos, traslapes,
expresión de rostros y parseo de tiempos del diálogo manual."""
import pytest

from clipia.momentos import _puntuar_ventana, _traslapan
from clipia.rostros import _expresion_rostros
from clipia.subtitulos import _fragmentos_subtitulo
from clipia.utilidades import formato_ass, formato_hora
from main import DialogoClipManual

# -- formato_hora ------------------------------------------------------

def test_formato_hora():
    assert formato_hora(0) == "0:00"
    assert formato_hora(52) == "0:52"
    assert formato_hora(65) == "1:05"
    assert formato_hora(3661) == "61:01"
    assert formato_hora(59.6) == "1:00"


def test_formato_hora_negativo_es_cero():
    assert formato_hora(-5) == "0:00"


# -- formato_ass --------------------------------------------------------

def test_formato_ass():
    assert formato_ass(0) == "0:00:00.00"
    assert formato_ass(61.5) == "0:01:01.50"
    assert formato_ass(3661.234) == "1:01:01.23"


def test_formato_ass_redondea_centesimas():
    # 61.999 -> 62.00 (el redondeo sube el segundo).
    assert formato_ass(61.999) == "0:01:02.00"


def test_formato_ass_negativo_es_cero():
    assert formato_ass(-3) == "0:00:00.00"


# -- _puntuar_ventana ---------------------------------------------------

def _frase(inicio, texto):
    return {"start": inicio, "end": inicio + 5, "text": texto}


def test_puntuar_ventana_sin_frases_es_cero():
    assert _puntuar_ventana([], 0, 30) == 0.0
    assert _puntuar_ventana([_frase(40, "hola")], 0, 30) == 0.0


def test_puntuar_ventana_densidad():
    # 30 palabras en 10 s = 3 palabras/s -> densidad máxima (0.45).
    texto = " ".join(["palabra"] * 30)
    assert _puntuar_ventana([_frase(0, texto)], 0, 10) == pytest.approx(0.45)


def test_puntuar_ventana_signos():
    # 2 signos + 1 palabra gancho ("verdad").
    puntos = _puntuar_ventana([_frase(0, "¡qué bien! ¿de verdad?")], 0, 30)
    assert puntos == pytest.approx(0.25 * (2 / 3) + 0.30 * (1 / 4)
                                   + 0.45 * (4 / 30) / 3)


def test_puntuar_ventana_ganchos():
    # 4 palabras gancho -> el máximo del componente de gancho (0.30).
    puntos = _puntuar_ventana(
        [_frase(0, "increíble dinero truco misterio")], 0, 30)
    assert puntos == pytest.approx(0.30 + 0.45 * (4 / 30) / 3)


def test_puntuar_ventana_limites_de_ventana():
    # La frase que empieza justo en fin queda fuera; la que empieza
    # 0.5 s antes del inicio entra.
    assert _puntuar_ventana([_frase(30, "hola")], 0, 30) == 0.0
    assert _puntuar_ventana([_frase(-0.5, "hola")], 0, 30) > 0.0


# -- _traslapan ----------------------------------------------------------

def test_traslapan():
    assert _traslapan(0, 10, 4, 14) is True   # traslape 6/10
    assert _traslapan(0, 10, 5, 15) is False  # traslape 5/10 = umbral
    assert _traslapan(0, 10, 10, 20) is False  # solo se tocan
    assert _traslapan(0, 10, 2, 5) is True     # contenido por completo
    assert _traslapan(5, 5, 0, 10) is False    # ventana vacía
    assert _traslapan(0, 10, 5, 15, umbral=0.4) is True


# -- _fragmentos_subtitulo ----------------------------------------------

def _palabras(n, inicio=0.0, paso=0.4):
    return [{"word": " pal%d" % i, "start": inicio + i * paso,
             "end": inicio + i * paso + 0.3} for i in range(n)]


def test_fragmentos_sin_palabras_usa_la_frase_completa():
    frase = {"start": 1.0, "end": 3.0, "text": "hola mundo", "words": []}
    assert _fragmentos_subtitulo(frase) == [(1.0, 3.0, "hola mundo")]


def test_fragmentos_agrupa_hasta_max_palabras():
    frase = {"start": 0.0, "end": 4.0, "text": "", "words": _palabras(8)}
    fragmentos = _fragmentos_subtitulo(frase)
    assert len(fragmentos) == 2  # 7 + 1 por defecto
    assert fragmentos[0][2] == "pal0 pal1 pal2 pal3 pal4 pal5 pal6"
    assert fragmentos[1][2] == "pal7"


def test_fragmentos_respeta_max_palabras():
    frase = {"start": 0.0, "end": 4.0, "text": "", "words": _palabras(8)}
    assert len(_fragmentos_subtitulo(frase, max_palabras=2)) == 4


def test_fragmentos_tiempos_de_primera_y_ultima_palabra():
    palabras = _palabras(3, inicio=10.0)
    fragmentos = _fragmentos_subtitulo(
        {"start": 10.0, "end": 12.0, "text": "", "words": palabras})
    assert len(fragmentos) == 1
    assert fragmentos[0][0] == pytest.approx(10.0)
    assert fragmentos[0][1] == pytest.approx(11.1)


def test_fragmentos_descarta_grupos_vacios():
    palabras = [{"word": " ", "start": 0.0, "end": 0.3}]
    frase = {"start": 0.0, "end": 1.0, "text": "", "words": palabras}
    assert _fragmentos_subtitulo(frase) == []


# -- _expresion_rostros ---------------------------------------------------

def test_expresion_rostros_sin_muestras_es_none():
    assert _expresion_rostros([], 1080) is None


def test_expresion_rostros_una_muestra_es_constante():
    expr = _expresion_rostros([(0.0, 0.5)], 1080)
    assert expr == "clip((0.5000)*iw-540,0,iw-1080)"
    assert "if(lt(t," not in expr


def test_expresion_rostros_interpola_entre_muestras():
    expr = _expresion_rostros([(0.0, 0.2), (5.0, 0.8)], 1080)
    assert expr.count("if(lt(t,") == 1
    assert "(t-0.000)" in expr
    assert expr.startswith("clip((")
    assert expr.endswith(",0,iw-1080)")


def test_expresion_rostros_maximo_45_puntos():
    # Fase 2: el tope sube de 12 a 45 puntos (crop no admite sendcmd).
    muestras = [(float(i), 0.1 + 0.01 * i) for i in range(60)]
    expr = _expresion_rostros(muestras, 1080)
    # 45 puntos -> 44 interpolaciones anidadas.
    assert expr.count("if(lt(t,") == 44


def test_expresion_rostros_usa_20_puntos_sin_recortar():
    # Con 20 muestras ya no se recorta a 12.
    muestras = [(float(i), 0.1 + 0.03 * i) for i in range(20)]
    expr = _expresion_rostros(muestras, 1080)
    assert expr.count("if(lt(t,") == 19


# -- DialogoClipManual._a_segundos ----------------------------------------

def test_a_segundos():
    assert DialogoClipManual._a_segundos("45") == 45.0
    assert DialogoClipManual._a_segundos("1:30") == 90.0
    assert DialogoClipManual._a_segundos("1:02:03") == 3723.0
    assert DialogoClipManual._a_segundos(" 2:00 ") == 120.0
    assert DialogoClipManual._a_segundos("0:00") == 0.0


def test_a_segundos_invalido():
    for texto in ("", "abc", "1:2:3:4", "1:xx"):
        with pytest.raises(ValueError):
            DialogoClipManual._a_segundos(texto)
