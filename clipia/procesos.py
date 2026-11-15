"""Registro de procesos ffmpeg hijos, para matarlos al cerrar la app.

Cuando el usuario cierra la ventana, el intérprete termina y los
hilos mueren, pero los procesos hijos (ffmpeg) NO: quedarían
huérfanos consumiendo CPU hasta terminar solos. Cada ffmpeg de
larga duración se registra aquí al arrancar y se olvida al terminar;
al cerrar, `matar_todos` los termina a todos.

Los comandos cortos (ffprobe, la prueba de 1 s del codificador, las
miniaturas de un fotograma) no se registran: su ventana de
orfandad es de menos de un segundo.
"""
import subprocess
import threading
import time

_BLOQUEO = threading.Lock()
_PROCESOS: set[subprocess.Popen] = set()


def registrar(proceso: subprocess.Popen) -> subprocess.Popen:
    """Registra un proceso hijo. Devuelve el mismo proceso, para usar
    en una sola línea: `proceso = registrar(subprocess.Popen(...))`."""
    with _BLOQUEO:
        _PROCESOS.add(proceso)
    return proceso


def olvidar(proceso: subprocess.Popen) -> None:
    """Saca un proceso del registro (ya terminó)."""
    with _BLOQUEO:
        _PROCESOS.discard(proceso)


def contar() -> int:
    """Número de procesos registrados (vivos o no olvidados)."""
    with _BLOQUEO:
        return len(_PROCESOS)


def matar_todos(timeout: float = 2.0) -> None:
    """Termina todos los procesos registrados.

    Primero `terminate` (suave); a los que no mueran en `timeout`
    segundos se les aplica `kill`. Al final el registro queda vacío.
    """
    with _BLOQUEO:
        procesos = list(_PROCESOS)
    for proceso in procesos:
        if proceso.poll() is None:
            try:
                proceso.terminate()
            except OSError:
                pass
    limite = time.monotonic() + timeout
    for proceso in procesos:
        restante = limite - time.monotonic()
        if restante <= 0:
            break
        try:
            proceso.wait(timeout=max(0.0, restante))
        except subprocess.TimeoutExpired:
            pass
    for proceso in procesos:
        if proceso.poll() is None:
            try:
                proceso.kill()
            except OSError:
                pass
    with _BLOQUEO:
        _PROCESOS.clear()


def ejecutar(cmd, timeout: float | None = None, check: bool = False,
             **kwargs) -> subprocess.CompletedProcess:
    """Como `subprocess.run`, pero el proceso queda registrado
    mientras corre, así `matar_todos` lo alcanza aunque la app se
    cierre a mitad. Devuelve un CompletedProcess y lanza las mismas
    excepciones (CalledProcessError, TimeoutExpired)."""
    # capture_output es de subprocess.run: Popen no lo acepta.
    if kwargs.pop("capture_output", False):
        kwargs.setdefault("stdout", subprocess.PIPE)
        kwargs.setdefault("stderr", subprocess.PIPE)
    proceso = subprocess.Popen(cmd, **kwargs)
    registrar(proceso)
    try:
        try:
            stdout, stderr = proceso.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proceso.kill()
            proceso.communicate()
            raise
        resultado = subprocess.CompletedProcess(
            cmd, proceso.returncode, stdout, stderr)
        if check and proceso.returncode != 0:
            raise subprocess.CalledProcessError(
                proceso.returncode, cmd, output=stdout, stderr=stderr)
        return resultado
    finally:
        olvidar(proceso)
