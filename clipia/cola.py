"""Cola de exportación con workers, ETA, cancelación y reintento.

La cola exporta varios clips con un ThreadPoolExecutor: con libx264
un solo worker (la CPU ya va saturada) y con un codificador por
hardware dos. Cada clip que falla se reintenta una vez sin tumbar el
lote; cancelar mata los ffmpeg en curso y marca el resto como
cancelado sin ejecutarlo.
"""
import logging
import os
import tempfile
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

from .encoder import ENCODER_CPU
from .exportacion import ExportacionCancelada, exportar_clip
from .rostros import detectar_rostros_con_limite
from .subtitulos import generar_subtitulos_ass

log = logging.getLogger("clipia.cola")

REINTENTOS_POR_DEFECTO = 1
MAX_WORKERS = 3


def workers_recomendados(encoder: str) -> int:
    """Workers según el codificador: 1 con libx264 (la CPU ya va
    saturada) y 2 con hardware (el codificador va en la GPU)."""
    return 1 if encoder == ENCODER_CPU else 2


def workers_efectivos(configurados: int, encoder: str) -> int:
    """Workers reales: 0 en config significa automático."""
    if configurados and configurados > 0:
        return max(1, min(MAX_WORKERS, configurados))
    return workers_recomendados(encoder)


@dataclass
class TrabajoExportacion:
    """Un clip pendiente de exportar."""
    clip: dict
    ruta_video: str
    segmentos: list = field(default_factory=list)
    carpeta_salida: str = ""
    nombre: str = ""
    seguir_rostros: bool = True
    encoder: str | None = None
    reintentos: int = REINTENTOS_POR_DEFECTO


@dataclass
class ResultadoClip:
    """Resultado de un clip (éxito, fallo o cancelado)."""
    trabajo: TrabajoExportacion
    ok: bool
    ruta: str | None = None
    error: str | None = None
    cancelado: bool = False


class ColaExportacion:
    """Exporta un lote de clips con workers en paralelo.

    `al_progreso(fraccion, eta, terminados, total, en_curso)` se llama
    desde los hilos de trabajo: la interfaz debe reenviarlo a su hilo
    principal. `en_curso` es una lista de (nombre, progreso 0.0-1.0)
    con los clips que se están exportando ahora mismo.
    """

    def __init__(
        self, workers: int = 1,
        al_progreso: Callable | None = None,
        exportar: Callable = exportar_clip,
        detectar: Callable = detectar_rostros_con_limite,
        generar_ass: Callable = generar_subtitulos_ass,
    ) -> None:
        self.workers = max(1, workers)
        self._al_progreso = al_progreso
        self._exportar = exportar
        self._detectar = detectar
        self._generar_ass = generar_ass
        self._bloqueo = threading.Lock()
        self._progreso_clip: dict[int, float] = {}
        self._trabajos: list[TrabajoExportacion] = []
        self._total = 0
        self._inicio = 0.0

    def exportar(self, trabajos: list[TrabajoExportacion],
                 cancelar: threading.Event | None = None
                 ) -> list[ResultadoClip]:
        """Exporta el lote y devuelve un resultado por trabajo, en el
        mismo orden en que se recibieron."""
        cancelar = cancelar or threading.Event()
        self._total = len(trabajos)
        self._trabajos = list(trabajos)
        self._inicio = time.monotonic()
        with self._bloqueo:
            self._progreso_clip = {id(t): 0.0 for t in trabajos}
        for trabajo in trabajos:
            os.makedirs(trabajo.carpeta_salida, exist_ok=True)
        resultados: list[ResultadoClip] = []
        with ThreadPoolExecutor(max_workers=self.workers) as ejecutor:
            futuros = {}
            for trabajo in trabajos:
                if cancelar.is_set():
                    resultados.append(ResultadoClip(
                        trabajo, False, cancelado=True))
                    continue
                futuros[ejecutor.submit(self._exportar_un_trabajo,
                                        trabajo, cancelar)] = trabajo
            for futuro in as_completed(futuros):
                resultados.append(futuro.result())
        orden = {id(t): i for i, t in enumerate(trabajos)}
        resultados.sort(key=lambda r: orden[id(r.trabajo)])
        return resultados

    def _progreso_trabajo(self, trabajo: TrabajoExportacion,
                          progreso: float) -> None:
        with self._bloqueo:
            self._progreso_clip[id(trabajo)] = min(1.0, max(0.0, progreso))
            total = self._total or 1
            hechos = sum(self._progreso_clip.values())
            fraccion = hechos / total
            terminados = sum(1 for p in self._progreso_clip.values()
                             if p >= 1.0)
            en_curso = [(t.nombre, self._progreso_clip.get(id(t), 0.0))
                        for t in self._trabajos_en_curso()]
            transcurrido = time.monotonic() - self._inicio
            eta = None
            if fraccion > 0.02 and transcurrido > 0:
                eta = transcurrido * (1.0 - fraccion) / fraccion
        if self._al_progreso:
            self._al_progreso(min(1.0, fraccion), eta, terminados,
                              self._total, en_curso)

    def _trabajos_en_curso(self) -> list[TrabajoExportacion]:
        return [t for t in self._trabajos
                if 0.0 < self._progreso_clip.get(id(t), 0.0) < 1.0]

    def _exportar_un_trabajo(self, trabajo: TrabajoExportacion,
                             cancelar: threading.Event) -> ResultadoClip:
        if cancelar.is_set():
            self._progreso_trabajo(trabajo, 1.0)
            return ResultadoClip(trabajo, False, cancelado=True)
        ultimo_error: Exception | None = None
        for intento in range(trabajo.reintentos + 1):
            if cancelar.is_set():
                self._progreso_trabajo(trabajo, 1.0)
                return ResultadoClip(trabajo, False, cancelado=True)
            try:
                ruta = self._exportar_un_intento(trabajo, cancelar)
                self._progreso_trabajo(trabajo, 1.0)
                return ResultadoClip(trabajo, True, ruta=ruta)
            except ExportacionCancelada:
                self._progreso_trabajo(trabajo, 1.0)
                return ResultadoClip(trabajo, False, cancelado=True)
            except Exception as error:  # noqa: BLE001 - reintento por clip
                ultimo_error = error
                log.warning("clip %s falló (intento %d): %s",
                            trabajo.nombre, intento + 1, error)
        self._progreso_trabajo(trabajo, 1.0)
        return ResultadoClip(trabajo, False,
                             error=str(ultimo_error))

    def _exportar_un_intento(self, trabajo: TrabajoExportacion,
                             cancelar: threading.Event) -> str:
        clip = trabajo.clip
        ruta_salida = os.path.join(trabajo.carpeta_salida, trabajo.nombre)
        # B3: un ASS temporal único por clip, borrado siempre.
        fd, ruta_ass = tempfile.mkstemp(suffix=".ass",
                                        prefix="clipia_sub_")
        os.close(fd)
        try:
            self._generar_ass(trabajo.segmentos, clip["start"],
                              clip["end"], ruta_ass)
            rostros = None
            if trabajo.seguir_rostros:
                rostros = self._detectar(
                    trabajo.ruta_video, clip["start"], clip["end"],
                    progreso=None)
            if cancelar.is_set():
                raise ExportacionCancelada("exportación cancelada")
            return self._exportar(
                trabajo.ruta_video, clip["start"], clip["end"],
                ruta_ass, ruta_salida,
                progreso=lambda p: self._progreso_trabajo(trabajo, p),
                rostros=rostros, encoder=trabajo.encoder,
                cancelar=cancelar)
        finally:
            if os.path.exists(ruta_ass):
                os.remove(ruta_ass)
