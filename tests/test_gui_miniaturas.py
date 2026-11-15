"""Tests de miniaturas en paralelo (Fase 1)."""
import threading
import time
from unittest import mock

import main as app_mod


def _clips(n):
    return [{"start": float(i * 10), "end": float(i * 10 + 5),
             "score": 1.0, "text": "clip %d" % i} for i in range(n)]


def test_generar_miniaturas_en_paralelo(app):
    """Con 6 clips que tardan 0.3 s cada uno, hay concurrencia real
    (secuencial serían 1.8 s). La prueba de paralelismo es la
    concurrencia observada, no el tiempo total: en una máquina
    compartida y cargada el tiempo total varía mucho (se midió
    29 s en una corrida de la suite completa), así que el tiempo
    solo acota un posible cuelgue."""
    app.ruta_video = "video.mp4"
    app.candidatos = _clips(6)
    estado = {"en_curso": 0, "max": 0}
    bloqueo = threading.Lock()

    def falso_generar(ruta_video, instante, ruta_salida, **kwargs):
        with bloqueo:
            estado["en_curso"] += 1
            estado["max"] = max(estado["max"], estado["en_curso"])
        try:
            time.sleep(0.3)
            with open(ruta_salida, "wb") as archivo:
                archivo.write(b"fake")
            return ruta_salida
        finally:
            with bloqueo:
                estado["en_curso"] -= 1

    with mock.patch.object(app_mod.core, "generar_miniatura",
                           side_effect=falso_generar):
        t0 = time.time()
        app._generar_miniaturas()
        total = time.time() - t0
    assert estado["max"] >= 2, "no hubo concurrencia"
    assert total < 60, "tardó %.2f s (posible cuelgue)" % total
    assert all(c["miniatura"] for c in app.candidatos)
    assert len({c["miniatura"] for c in app.candidatos}) == 6


def test_generar_miniaturas_fallo_aislado(app):
    """Si una miniatura falla, ese clip queda en None y los demás
    salen bien."""
    app.ruta_video = "video.mp4"
    app.candidatos = _clips(3)

    def falso_generar(ruta_video, instante, ruta_salida, **kwargs):
        if instante == 12.5:  # el 2º clip (10–15, punto medio 12.5)
            raise RuntimeError("fallo provocado")
        with open(ruta_salida, "wb") as archivo:
            archivo.write(b"fake")
        return ruta_salida

    with mock.patch.object(app_mod.core, "generar_miniatura",
                           side_effect=falso_generar):
        app._generar_miniaturas()
    assert app.candidatos[0]["miniatura"] is not None
    assert app.candidatos[1]["miniatura"] is None
    assert app.candidatos[2]["miniatura"] is not None
