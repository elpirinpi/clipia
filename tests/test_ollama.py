"""Fase 2: re-ranking opcional con Ollama (nunca bloquea).

Sin Ollama la app sigue con la heurística. Con Ollama simulado
(servidor HTTP local) se comprueba el reorden, el timeout ante un
servidor lento y las respuestas inválidas.
"""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from clipia.ollama import (
    INSTRUCCIONES_INSTALACION,
    _extraer_json,
    modelo_disponible,
    ollama_disponible,
    rerank_ollama,
)

PUERTO_CERRADO = "http://127.0.0.1:1"

# Respuesta enlatada: invierte el orden heurístico (el 3.º pasa 1.º).
RESPUESTA_ENLATADA = {
    "puntuaciones": [
        {"indice": 0, "gancho": 2, "coherencia": 2, "remate": 2},
        {"indice": 1, "gancho": 5, "coherencia": 5, "remate": 5},
        {"indice": 2, "gancho": 9, "coherencia": 9, "remate": 9},
    ]
}


def _candidatos(n=3):
    return [{"start": float(i * 60), "end": float(i * 60 + 45),
             "score": 0.9 - i * 0.1, "text": "clip número %d" % i}
            for i in range(n)]


class _ManejadorOllama(BaseHTTPRequestHandler):
    respuesta_generate = json.dumps(
        {"response": json.dumps(RESPUESTA_ENLATADA)})
    modelos = [{"name": "qwen2.5:7b"}]
    demora = 0.0
    ultimo_prompt = None

    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path == "/api/tags":
            self._responder(200, {"models": self.modelos})
        else:
            self._responder(404, {})

    def do_POST(self):
        if self.path != "/api/generate":
            self._responder(404, {})
            return
        largo = int(self.headers.get("Content-Length", 0))
        cuerpo = json.loads(self.rfile.read(largo).decode("utf-8"))
        type(self).ultimo_prompt = cuerpo.get("prompt", "")
        if self.demora:
            time.sleep(self.demora)
        self._responder(200, json.loads(self.respuesta_generate)
                        if self.respuesta_generate.startswith("{")
                        else {})

    def _responder(self, codigo, valor):
        datos = json.dumps(valor).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(datos)))
        self.end_headers()
        self.wfile.write(datos)


@pytest.fixture
def ollama_falso():
    _ManejadorOllama.respuesta_generate = json.dumps(
        {"response": json.dumps(RESPUESTA_ENLATADA)})
    _ManejadorOllama.modelos = [{"name": "qwen2.5:7b"}]
    _ManejadorOllama.demora = 0.0
    servidor = ThreadingHTTPServer(("127.0.0.1", 0), _ManejadorOllama)
    servidor.daemon_threads = True
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    host = "http://127.0.0.1:%d" % servidor.server_address[1]
    yield host, _ManejadorOllama
    servidor.shutdown()
    servidor.server_close()


# -- Sin Ollama: nunca bloquea -------------------------------------------

def test_disponible_falso_sin_servidor():
    t0 = time.monotonic()
    assert ollama_disponible(PUERTO_CERRADO, timeout=1.0) is False
    assert time.monotonic() - t0 < 3.0


def test_rerank_sin_servidor_devuelve_none_rapido():
    t0 = time.monotonic()
    assert rerank_ollama(_candidatos(), host=PUERTO_CERRADO,
                         timeout=1.0) is None
    assert time.monotonic() - t0 < 3.0


def test_rerank_sin_candidatos_es_none():
    assert rerank_ollama([], host=PUERTO_CERRADO) is None


# -- Ollama simulado -------------------------------------------------------

def test_disponible_y_modelo_con_servidor(ollama_falso):
    host, _manejador = ollama_falso
    assert ollama_disponible(host) is True
    assert modelo_disponible("qwen2.5:7b", host) is True
    assert modelo_disponible("otro:1b", host) is False


def test_rerank_reordena_segun_llm(ollama_falso):
    host, _manejador = ollama_falso
    resultado = rerank_ollama(_candidatos(), host=host)
    assert resultado is not None
    # El LLM puntuó mejor al 3.º: queda primero.
    assert [c["text"] for c in resultado] == [
        "clip número 2", "clip número 1", "clip número 0"]
    assert resultado[0]["score_llm"] == pytest.approx(0.9)
    assert resultado[0]["score_heuristica"] == pytest.approx(0.7)
    # Mezcla 0.6 LLM + 0.4 heurística.
    assert resultado[0]["score"] == pytest.approx(0.6 * 0.9 + 0.4 * 0.7)


def test_rerank_manda_el_prompt_con_los_candidatos(ollama_falso):
    host, manejador = ollama_falso
    rerank_ollama(_candidatos(), host=host)
    assert "clip número 0" in manejador.ultimo_prompt
    assert "gancho" in manejador.ultimo_prompt
    assert "coherencia" in manejador.ultimo_prompt
    assert "remate" in manejador.ultimo_prompt


def test_rerank_respeta_max_candidatos(ollama_falso):
    host, _manejador = ollama_falso
    candidatos = _candidatos(30)
    resultado = rerank_ollama(candidatos, host=host, max_candidatos=3)
    assert resultado is not None
    assert len(resultado) == 30
    # Los 3 primeros se reordenaron; del 4.º en adelante, orden original.
    assert [c["text"] for c in resultado[3:6]] == [
        "clip número 3", "clip número 4", "clip número 5"]


def test_rerank_json_invalido_devuelve_none(ollama_falso):
    host, manejador = ollama_falso
    manejador.respuesta_generate = json.dumps(
        {"response": "esto no es JSON ni de lejos"})
    assert rerank_ollama(_candidatos(), host=host) is None


def test_rerank_respuesta_sin_puntuaciones_devuelve_none(ollama_falso):
    host, manejador = ollama_falso
    manejador.respuesta_generate = json.dumps({"response": '{"otro": 1}'})
    assert rerank_ollama(_candidatos(), host=host) is None


def test_rerank_pocos_puntuados_devuelve_none(ollama_falso):
    host, manejador = ollama_falso
    manejador.respuesta_generate = json.dumps({"response": json.dumps(
        {"puntuaciones": [
            {"indice": 0, "gancho": 9, "coherencia": 9, "remate": 9}]})})
    # Solo 1 de 3 puntuados: no es de fiar.
    assert rerank_ollama(_candidatos(), host=host) is None


def test_rerank_timeout_ante_servidor_lento(ollama_falso):
    host, manejador = ollama_falso
    manejador.demora = 5.0
    t0 = time.monotonic()
    assert rerank_ollama(_candidatos(), host=host, timeout=1.0) is None
    assert time.monotonic() - t0 < 4.0


def test_extraer_json_tolera_cercas_markdown():
    texto = ("Claro, aquí tienes:\n```json\n"
             '{"puntuaciones": []}\n```\nEspero que sirva.')
    assert _extraer_json(texto) == {"puntuaciones": []}
    assert _extraer_json("sin llaves") is None
    assert _extraer_json("{no json}") is None


# -- GUI -------------------------------------------------------------------

def test_boton_ollama_existe(app):
    assert app.boton_ollama.cget("text") == "✨ Reordenar con IA local"


def _esperar(app, condicion, segundos=5.0):
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        app.update()
        if condicion():
            return True
        time.sleep(0.05)
    app.update()
    return condicion()


def test_gui_sin_candidatos_avisa(app, monkeypatch):
    avisos = []
    monkeypatch.setattr("main.messagebox.showinfo",
                        lambda *a: avisos.append(a))
    app.boton_ollama.invoke()
    assert avisos and "Primero carga y analiza" in avisos[0][1]


def test_gui_sin_ollama_muestra_instrucciones(app, monkeypatch):
    import main as app_mod

    avisos = []
    monkeypatch.setattr("main.messagebox.showinfo",
                        lambda *a: avisos.append(a))
    monkeypatch.setattr(app_mod, "ollama_disponible", lambda: False)
    app.candidatos = _candidatos()
    app.boton_ollama.invoke()
    assert _esperar(app, lambda: bool(avisos))
    assert "ollama pull qwen2.5:7b" in avisos[0][1]
    assert INSTRUCCIONES_INSTALACION.split("\n")[0] in avisos[0][1]


def test_gui_reordena_y_conserva_seleccion(app, monkeypatch):
    import main as app_mod

    monkeypatch.setattr(app_mod, "ollama_disponible", lambda: True)
    monkeypatch.setattr(app_mod, "modelo_disponible", lambda modelo: True)
    invertidos = list(reversed(_candidatos()))
    monkeypatch.setattr(app_mod, "rerank_ollama",
                        lambda c, modelo: invertidos)
    app.candidatos = _candidatos()
    app._mostrar_clips()
    app.update()
    app.seleccion[0].set(False)  # desmarcar el primer clip
    app.boton_ollama.invoke()
    # El estado final llega después del redibujado en la cola de la UI.
    assert _esperar(
        app, lambda: app.etiqueta_estado.cget("text")
        == "Clips reordenados con IA local.")
    assert app.candidatos[0]["text"] == "clip número 2"
    # La selección se conserva por (inicio, fin): el clip 0 sigue
    # desmarcado aunque ahora esté el último.
    assert len(app.seleccion) == 3
    assert app.seleccion[2].get() is False
    assert app.seleccion[0].get() is True


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
