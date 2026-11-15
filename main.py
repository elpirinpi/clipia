"""
ClipIA - app de escritorio para crear clips cortos verticales con IA.

Flujo: Cargar -> Analizar -> Clips -> Exportar.
Todo corre 100% local: faster-whisper transcribe, el detector de momentos
elige los mejores fragmentos y ffmpeg exporta los clips en 1080x1920
con subtítulos quemados.
"""

import logging
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
import traceback
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from tkinter import filedialog, messagebox

import customtkinter as ctk
from PIL import Image

# Arrastrar y soltar (tkinterdnd2, Fase 3): la API oficial `require()`
# activa tkdnd en una ventana CustomTkinter (probado en el prototipo
# R3: tkdnd 2.10.3 carga limpio). Si la librería falta, la app sigue
# funcionando sin DnD (el import es opcional a propósito).
try:
    from tkinterdnd2 import DND_FILES, DND_TEXT
    from tkinterdnd2.TkinterDnD import DnDWrapper
    from tkinterdnd2.TkinterDnD import require as dnd_require
    _DND_DISPONIBLE = True
except ImportError:
    DND_FILES = DND_TEXT = None
    DnDWrapper = object
    dnd_require = None
    _DND_DISPONIBLE = False

import clipia_core as core
from clipia import __version__, editor, proyecto
from clipia.cola import ColaExportacion, TrabajoExportacion, workers_efectivos
from clipia.config import cargar_config, guardar_config
from clipia.encoder import descripcion_encoder, detectar_encoder
from clipia.logs import configurar_logging
from clipia.ollama import (
    INSTRUCCIONES_INSTALACION,
    INSTRUCCIONES_MODELO,
    MODELO_DEFECTO,
    modelo_disponible,
    ollama_disponible,
    rerank_ollama,
)
from clipia.procesos import matar_todos
from clipia.rostros import detectar_rostros_con_limite
from clipia.subtitulos import PRESETS_SUBTITULOS
from clipia.transcripcion import IDIOMAS, MODELOS_WHISPER, ram_total_gb

log = logging.getLogger("clipia.gui")

# ---------------------------------------------------------------------------
# Paleta "Estudio de clips" (oscura, un solo acento rojo como en el video)
# ---------------------------------------------------------------------------
BG = "#0E1116"        # fondo de la ventana
PANEL = "#171B22"     # fondo de los paneles
TARJETA = "#1F242E"   # fondo de cada clip
BORDE = "#2A303C"     # bordes suaves
TEXTO = "#E8EAED"     # texto principal
SILENCIO = "#9AA3B2"  # texto secundario
ROJO = "#E5484D"      # acción principal (exportar)
ROJO_HOVER = "#C93A3F"
AZUL = "#3B82F6"      # acción secundaria (analizar)
AZUL_HOVER = "#2F6FED"
VERDE = "#3FB950"     # estado "listo"

PASOS = ["Cargar", "Analizar", "Clips", "Exportar"]


def _detalle_error(error: Exception) -> str:
    """Texto para mostrar un error al usuario: los errores de
    descarga (YouTube, modelo de voz) ya traen su mensaje accionable
    (qué hacer), así que se muestran tal cual; los demás llevan el
    tipo delante."""
    if isinstance(error, (core.ErrorDescarga,
                          core.ErrorDescargaModelo)):
        return str(error)
    return "%s: %s" % (type(error).__name__, error)


class DialogoClipManual(ctk.CTkToplevel):
    """Ventana pequeña para crear un clip manual (inicio y fin)."""

    def __init__(self, padre, duracion: float, al_agregar) -> None:
        super().__init__(padre)
        self.title("Crear clip")
        self.geometry("360x230")
        self.resizable(False, False)
        self.configure(fg_color=PANEL)
        self.transient(padre)
        self.grab_set()
        self._duracion = duracion
        self._al_agregar = al_agregar

        ctk.CTkLabel(self, text="Crear clip manual",
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color=TEXTO).pack(pady=(16, 4))
        ctk.CTkLabel(
            self,
            text="Duración del video: %s  ·  Escribe m:ss (ej. 1:30)"
                 % core.formato_hora(duracion),
            font=ctk.CTkFont(size=12), text_color=SILENCIO,
        ).pack(pady=(0, 12))

        marco = ctk.CTkFrame(self, fg_color="transparent")
        marco.pack(fill="x", padx=24)
        ctk.CTkLabel(marco, text="Inicio", text_color=SILENCIO).grid(
            row=0, column=0, sticky="w")
        self.entrada_inicio = ctk.CTkEntry(marco, width=120)
        self.entrada_inicio.grid(row=0, column=1, padx=(8, 0), pady=4)
        self.entrada_inicio.insert(0, "0:00")
        ctk.CTkLabel(marco, text="Fin", text_color=SILENCIO).grid(
            row=1, column=0, sticky="w")
        self.entrada_fin = ctk.CTkEntry(marco, width=120)
        self.entrada_fin.grid(row=1, column=1, padx=(8, 0), pady=4)
        self.entrada_fin.insert(0, "0:45")

        ctk.CTkButton(
            self, text="Agregar clip", fg_color=AZUL, hover_color=AZUL_HOVER,
            command=self._agregar,
        ).pack(pady=(16, 8))

    @staticmethod
    def _a_segundos(texto: str) -> float:
        texto = texto.strip()
        if ":" in texto:
            partes = texto.split(":")
            if len(partes) == 2:
                return int(partes[0]) * 60 + float(partes[1])
            if len(partes) == 3:
                return (int(partes[0]) * 3600 + int(partes[1]) * 60
                        + float(partes[2]))
            raise ValueError
        return float(texto)

    def _agregar(self) -> None:
        try:
            inicio = self._a_segundos(self.entrada_inicio.get())
            fin = self._a_segundos(self.entrada_fin.get())
        except ValueError:
            messagebox.showerror(
                "ClipIA", "Usa el formato m:ss, por ejemplo 1:30.")
            return
        if inicio < 0 or fin <= inicio or fin > self._duracion:
            messagebox.showerror(
                "ClipIA",
                "Revisa los tiempos: el fin debe ser mayor que el inicio "
                "y no pasar de la duración del video.")
            return
        self._al_agregar(inicio, fin)
        self.destroy()


class DialogoAjustes(ctk.CTkToplevel):
    """Ventana de ajustes (codificador, modelo de voz, idioma, workers)."""

    OPCIONES_ENCODER = [
        ("Automático (recomendado)", "auto"),
        ("NVENC — GPU NVIDIA", "h264_nvenc"),
        ("Quick Sync — GPU Intel", "h264_qsv"),
        ("AMF — GPU AMD", "h264_amf"),
        ("libx264 — CPU", "libx264"),
    ]

    OPCIONES_WORKERS = [
        ("Automático (recomendado)", 0),
        ("1 clip a la vez", 1),
        ("2 clips a la vez", 2),
        ("3 clips a la vez", 3),
    ]

    OPCIONES_LOTE = [
        ("Automático", 0),
        ("4", 4),
        ("8", 8),
        ("16", 16),
    ]

    OPCIONES_COOKIES = [
        ("Sin cookies (recomendado)", "ninguno"),
        ("Chrome", "chrome"),
        ("Microsoft Edge", "edge"),
        ("Firefox", "firefox"),
    ]

    def __init__(self, padre, config: dict, al_guardar) -> None:
        super().__init__(padre)
        self.title("Ajustes")
        self.geometry("400x720")
        self.resizable(False, False)
        self.configure(fg_color=PANEL)
        self.transient(padre)
        self.grab_set()
        self._al_guardar = al_guardar
        self._ram_total = ram_total_gb()
        # Contenido con desplazamiento: con 8 secciones el diálogo
        # no cabe en pantallas bajas; el botón Guardar queda fijo
        # abajo, fuera del área con desplazamiento.
        contenido = ctk.CTkScrollableFrame(
            self, fg_color="transparent",
            scrollbar_button_color=BORDE)
        contenido.pack(fill="both", expand=True)

        ctk.CTkLabel(contenido, text="Ajustes",
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color=TEXTO).pack(pady=(16, 4))

        ctk.CTkLabel(contenido, text="Codificador de video",
                     font=ctk.CTkFont(size=12), text_color=SILENCIO,
                     anchor="w").pack(fill="x", padx=24, pady=(12, 4))
        actual = config.get("encoder", "auto")
        texto_actual = next((t for t, v in self.OPCIONES_ENCODER
                             if v == actual), self.OPCIONES_ENCODER[0][0])
        self.variable_encoder = tk.StringVar(value=texto_actual)
        ctk.CTkOptionMenu(
            contenido, values=[t for t, _v in self.OPCIONES_ENCODER],
            variable=self.variable_encoder, width=320,
        ).pack(padx=24)
        ctk.CTkLabel(
            contenido,
            text="«Automático» prueba el hardware de tu PC y usa la CPU\n"
                 "si no hay codificador compatible. Si el elegido falla,\n"
                 "la app siempre vuelve a la CPU.",
            font=ctk.CTkFont(size=11), text_color=SILENCIO,
            justify="left").pack(padx=24, pady=(8, 4), anchor="w")

        ctk.CTkLabel(contenido, text="Modelo de voz (transcripción)",
                     font=ctk.CTkFont(size=12), text_color=SILENCIO,
                     anchor="w").pack(fill="x", padx=24, pady=(12, 4))
        modelo_actual = config.get("modelo", "base")
        if modelo_actual not in MODELOS_WHISPER:
            modelo_actual = "base"
        self.variable_modelo = tk.StringVar(
            value=MODELOS_WHISPER[modelo_actual]["descripcion"])
        ctk.CTkOptionMenu(
            contenido, values=[m["descripcion"]
                          for m in MODELOS_WHISPER.values()],
            variable=self.variable_modelo, width=320,
            command=lambda _v: self._actualizar_aviso_ram(),
        ).pack(padx=24)
        self.etiqueta_ram = ctk.CTkLabel(
            contenido, text="", font=ctk.CTkFont(size=11),
            text_color=SILENCIO, justify="left")
        self.etiqueta_ram.pack(padx=24, pady=(8, 4), anchor="w")
        self._actualizar_aviso_ram()

        ctk.CTkLabel(contenido, text="Idioma del audio",
                     font=ctk.CTkFont(size=12), text_color=SILENCIO,
                     anchor="w").pack(fill="x", padx=24, pady=(12, 4))
        idioma_actual = config.get("idioma", "es")
        texto_idioma = next((t for c, t in IDIOMAS if c == idioma_actual),
                            IDIOMAS[0][1])
        self.variable_idioma = tk.StringVar(value=texto_idioma)
        ctk.CTkOptionMenu(
            contenido, values=[t for _c, t in IDIOMAS],
            variable=self.variable_idioma, width=320,
        ).pack(padx=24)

        ctk.CTkLabel(contenido, text="Clips a exportar a la vez",
                     font=ctk.CTkFont(size=12), text_color=SILENCIO,
                     anchor="w").pack(fill="x", padx=24, pady=(12, 4))
        workers_actual = config.get("workers_exportacion", 0)
        texto_workers = next((t for t, v in self.OPCIONES_WORKERS
                              if v == workers_actual),
                             self.OPCIONES_WORKERS[0][0])
        self.variable_workers = tk.StringVar(value=texto_workers)
        ctk.CTkOptionMenu(
            contenido, values=[t for t, _v in self.OPCIONES_WORKERS],
            variable=self.variable_workers, width=320,
        ).pack(padx=24)
        ctk.CTkLabel(
            contenido,
            text="«Automático» usa 1 con CPU y 2 con codificador por\n"
                 "hardware. Con CPU, exportar varios a la vez no es\n"
                 "más rápido: los workers se reparten la misma CPU.",
            font=ctk.CTkFont(size=11), text_color=SILENCIO,
            justify="left").pack(padx=24, pady=(8, 4), anchor="w")

        ctk.CTkLabel(contenido, text="Estilo de subtítulos",
                     font=ctk.CTkFont(size=12), text_color=SILENCIO,
                     anchor="w").pack(fill="x", padx=24, pady=(12, 4))
        estilo_actual = config.get("estilo_subtitulos", "Shorts clásico")
        if estilo_actual not in PRESETS_SUBTITULOS:
            estilo_actual = "Shorts clásico"
        self.variable_estilo = tk.StringVar(value=estilo_actual)
        ctk.CTkOptionMenu(
            contenido, values=list(PRESETS_SUBTITULOS),
            variable=self.variable_estilo, width=320,
        ).pack(padx=24)
        ctk.CTkLabel(
            contenido,
            text="«Hormozi» y «Neón» resaltan cada palabra al hablarse\n"
                 "(karaoke); «Hormozi» además usa MAYÚSCULAS.",
            font=ctk.CTkFont(size=11), text_color=SILENCIO,
            justify="left").pack(padx=24, pady=(8, 4), anchor="w")

        ctk.CTkLabel(contenido, text="Margen vertical de subtítulos (px)",
                     font=ctk.CTkFont(size=12), text_color=SILENCIO,
                     anchor="w").pack(fill="x", padx=24, pady=(12, 4))
        self.entrada_margen = ctk.CTkEntry(contenido, width=120)
        self.entrada_margen.pack(anchor="w", padx=24)
        self.entrada_margen.insert(
            0, str(config.get("margen_vertical", 300)))
        ctk.CTkLabel(
            contenido,
            text="Distancia desde abajo: 300 es lo habitual. Súbelo si\n"
                 "los botones de TikTok tapan los subtítulos.",
            font=ctk.CTkFont(size=11), text_color=SILENCIO,
            justify="left").pack(padx=24, pady=(8, 4), anchor="w")

        ctk.CTkLabel(contenido, text="Modelo de Ollama (IA local, opcional)",
                     font=ctk.CTkFont(size=12), text_color=SILENCIO,
                     anchor="w").pack(fill="x", padx=24, pady=(12, 4))
        self.variable_ollama = tk.StringVar(
            value=config.get("ollama_modelo", MODELO_DEFECTO))
        ctk.CTkEntry(contenido, textvariable=self.variable_ollama,
                     width=320).pack(padx=24)
        ctk.CTkLabel(
            contenido,
            text="Se usa al pulsar «Reordenar con IA local». En blanco\n"
                 "usa el modelo por defecto (%s)." % MODELO_DEFECTO,
            font=ctk.CTkFont(size=11), text_color=SILENCIO,
            justify="left").pack(padx=24, pady=(8, 4), anchor="w")

        ctk.CTkLabel(contenido, text="Lote de transcripción",
                     font=ctk.CTkFont(size=12), text_color=SILENCIO,
                     anchor="w").pack(fill="x", padx=24, pady=(12, 4))
        lote_actual = config.get("lote_transcripcion", 0)
        texto_lote = next((t for t, v in self.OPCIONES_LOTE
                           if v == lote_actual),
                          self.OPCIONES_LOTE[0][0])
        self.variable_lote = tk.StringVar(value=texto_lote)
        ctk.CTkOptionMenu(
            contenido, values=[t for t, _v in self.OPCIONES_LOTE],
            variable=self.variable_lote, width=320,
        ).pack(padx=24)
        ctk.CTkLabel(
            contenido,
            text="Cuántas frases transcribe a la vez. «Automático»\n"
                 "elige según tu PC (16 con GPU, 8 con CPU). Un lote\n"
                 "mayor usa más RAM.",
            font=ctk.CTkFont(size=11), text_color=SILENCIO,
            justify="left").pack(padx=24, pady=(8, 4), anchor="w")

        ctk.CTkLabel(contenido, text="Cookies de YouTube",
                     font=ctk.CTkFont(size=12), text_color=SILENCIO,
                     anchor="w").pack(fill="x", padx=24, pady=(12, 4))
        cookies_actual = config.get("navegador_cookies", "ninguno")
        texto_cookies = next((t for t, v in self.OPCIONES_COOKIES
                              if v == cookies_actual),
                             self.OPCIONES_COOKIES[0][0])
        self.variable_cookies = tk.StringVar(value=texto_cookies)
        ctk.CTkOptionMenu(
            contenido, values=[t for t, _v in self.OPCIONES_COOKIES],
            variable=self.variable_cookies, width=320,
        ).pack(padx=24)
        ctk.CTkLabel(
            contenido,
            text="Si YouTube bloquea la descarga pidiendo verificar\n"
                 "que no eres un bot, elige el navegador donde\n"
                 "tengas sesión iniciada en YouTube.",
            font=ctk.CTkFont(size=11), text_color=SILENCIO,
            justify="left").pack(padx=24, pady=(8, 4), anchor="w")

        ctk.CTkLabel(contenido, text="Actualizar yt-dlp",
                     font=ctk.CTkFont(size=12), text_color=SILENCIO,
                     anchor="w").pack(fill="x", padx=24, pady=(12, 4))
        fila_ytdlp = ctk.CTkFrame(contenido, fg_color="transparent")
        fila_ytdlp.pack(fill="x", padx=24)
        version = core.version_ytdlp()
        self.etiqueta_ytdlp = ctk.CTkLabel(
            fila_ytdlp,
            text="yt-dlp: %s" % version if version
            else "yt-dlp: no disponible",
            font=ctk.CTkFont(size=12), text_color=TEXTO)
        self.etiqueta_ytdlp.pack(side="left")
        self.boton_ytdlp = ctk.CTkButton(
            fila_ytdlp, text="Actualizar yt-dlp", width=150,
            fg_color=AZUL, hover_color=AZUL_HOVER,
            command=self._actualizar_ytdlp)
        self.boton_ytdlp.pack(side="right")
        ctk.CTkLabel(
            contenido,
            text="YouTube cambia a menudo: si una descarga falla,\n"
                 "actualiza yt-dlp antes de reintentar.",
            font=ctk.CTkFont(size=11), text_color=SILENCIO,
            justify="left").pack(padx=24, pady=(8, 4), anchor="w")

        self.boton_guardar = ctk.CTkButton(
            self, text="Guardar", fg_color=AZUL, hover_color=AZUL_HOVER,
            command=self._guardar,
        )
        self.boton_guardar.pack(side="bottom", pady=(8, 12))

    def _modelo_elegido(self) -> str:
        elegido = self.variable_modelo.get()
        return next((c for c, m in MODELOS_WHISPER.items()
                     if m["descripcion"] == elegido), "base")

    def _actualizar_aviso_ram(self) -> None:
        """Aviso de RAM según el modelo elegido y la RAM del equipo."""
        necesario = MODELOS_WHISPER[self._modelo_elegido()]["ram_gb"]
        if self._ram_total is None:
            texto = "Necesita unos %d GB de RAM." % necesario
            color = SILENCIO
        elif self._ram_total >= necesario:
            texto = ("Necesita unos %d GB de RAM "
                     "(tu PC tiene ~%.0f GB)." % (necesario, self._ram_total))
            color = SILENCIO
        else:
            texto = ("⚠ Necesita unos %d GB de RAM y tu PC tiene ~%.0f GB:\n"
                     "puede ir muy lento o fallar."
                     % (necesario, self._ram_total))
            color = ROJO
        self.etiqueta_ram.configure(text=texto, text_color=color)

    def _actualizar_ytdlp(self) -> None:
        """Actualiza yt-dlp en segundo plano (la red es lenta)."""
        self.boton_ytdlp.configure(state="disabled")
        self.etiqueta_ytdlp.configure(text="Actualizando yt-dlp…")
        threading.Thread(target=self._hilo_actualizar_ytdlp,
                         daemon=True).start()

    def _hilo_actualizar_ytdlp(self) -> None:
        """Actualiza yt-dlp y deja el resultado en la etiqueta."""
        try:
            version = core.actualizar_ytdlp()
            if core.esta_congelado():
                texto = "yt-dlp: %s" % version
            else:
                # En modo dev la versión nueva se usa al reiniciar
                # la app: este proceso ya cargó la vieja.
                texto = ("yt-dlp: %s (reinicia la app para usarlo)"
                         % version)
        except Exception as error:  # noqa: BLE001 - mostrar el error
            texto = "No se pudo actualizar: %s" % error
        try:
            self.after(0, self._mostrar_version_ytdlp, texto)
        except tk.TclError:
            pass  # el diálogo se cerró mientras actualizaba

    def _mostrar_version_ytdlp(self, texto: str) -> None:
        try:
            self.etiqueta_ytdlp.configure(text=texto)
            self.boton_ytdlp.configure(state="normal")
        except tk.TclError:
            pass  # el diálogo se cerró

    def _guardar(self) -> None:
        elegido = self.variable_encoder.get()
        valor_encoder = next((v for t, v in self.OPCIONES_ENCODER
                              if t == elegido), "auto")
        idioma_elegido = self.variable_idioma.get()
        valor_idioma = next((c for c, t in IDIOMAS
                             if t == idioma_elegido), "es")
        workers_elegido = self.variable_workers.get()
        valor_workers = next((v for t, v in self.OPCIONES_WORKERS
                              if t == workers_elegido), 0)
        try:
            valor_margen = int(self.entrada_margen.get().strip())
        except ValueError:
            valor_margen = 300
        valor_margen = min(1500, max(0, valor_margen))
        estilo_elegido = self.variable_estilo.get()
        if estilo_elegido not in PRESETS_SUBTITULOS:
            estilo_elegido = "Shorts clásico"
        modelo_ollama = self.variable_ollama.get().strip() or MODELO_DEFECTO
        lote_elegido = self.variable_lote.get()
        valor_lote = next((v for t, v in self.OPCIONES_LOTE
                           if t == lote_elegido), 0)
        cookies_elegido = self.variable_cookies.get()
        valor_cookies = next((v for t, v in self.OPCIONES_COOKIES
                              if t == cookies_elegido), "ninguno")
        self._al_guardar({"encoder": valor_encoder,
                          "modelo": self._modelo_elegido(),
                          "idioma": valor_idioma,
                          "workers_exportacion": valor_workers,
                          "estilo_subtitulos": estilo_elegido,
                          "margen_vertical": valor_margen,
                          "ollama_modelo": modelo_ollama,
                          "lote_transcripcion": valor_lote,
                          "navegador_cookies": valor_cookies})
        self.destroy()


class DialogoEditorClip(ctk.CTkToplevel):
    """Ventana para ajustar los límites de un clip.

    Sliders de inicio/fin, forma de onda del tramo (con el clip
    resaltado en rojo) y transcripción clicable: un clic en una
    palabra (o en la onda) fija el límite activo (inicio o fin). Al
    guardar, el llamador recibe (inicio, fin) y actualiza el clip.
    """

    def __init__(self, padre, clip: dict, segmentos: list,
                 ruta_video: str, duracion: float, al_guardar) -> None:
        super().__init__(padre)
        self.title("Editar clip")
        self.geometry("640x640")
        self.resizable(False, False)
        self.configure(fg_color=PANEL)
        self.transient(padre)
        self.grab_set()
        self._al_guardar = al_guardar
        self._segmentos = segmentos
        self._ruta_video = ruta_video
        self._duracion = max(1.0, float(duracion))
        self._inicio = float(clip["start"])
        self._fin = float(clip["end"])
        self._limite_activo = "inicio"
        # Ventana visible de la onda y la transcripción: el clip con
        # contexto a ambos lados para poder ampliarlo con un clic.
        self._ventana_inicio = max(0.0,
                                   self._inicio - editor.MARGEN_CONTEXTO)
        self._ventana_fin = min(self._duracion,
                                self._fin + editor.MARGEN_CONTEXTO)
        self._muestras = None
        self._forma_lista = threading.Event()
        self._imagen_forma = None

        ctk.CTkLabel(self, text="Editar clip",
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color=TEXTO).pack(pady=(16, 4))

        # Forma de onda (se carga en un hilo: extraer el audio tarda
        # 1-3 s y la ventana no debe congelarse).
        self.etiqueta_forma = ctk.CTkLabel(
            self, text="Cargando forma de onda…",
            font=ctk.CTkFont(size=12), text_color=SILENCIO,
            width=560, height=90, fg_color=BG, corner_radius=8)
        self.etiqueta_forma.pack(padx=24, pady=(8, 4))
        self.etiqueta_forma.bind("<Button-1>", self._al_clic_onda)
        threading.Thread(target=self._cargar_forma, daemon=True).start()
        self.after(100, self._revisar_forma)

        # Sliders de inicio y fin.
        self.etiqueta_inicio = ctk.CTkLabel(
            self, text="", font=ctk.CTkFont(size=12), text_color=TEXTO,
            anchor="w")
        self.etiqueta_inicio.pack(fill="x", padx=24, pady=(8, 0))
        self.slider_inicio = ctk.CTkSlider(
            self, from_=0, to=self._duracion,
            number_of_steps=max(1, int(self._duracion * 10)),
            command=self._al_mover_inicio)
        self.slider_inicio.pack(fill="x", padx=24)
        self.slider_inicio.set(self._inicio)
        self.etiqueta_fin = ctk.CTkLabel(
            self, text="", font=ctk.CTkFont(size=12), text_color=TEXTO,
            anchor="w")
        self.etiqueta_fin.pack(fill="x", padx=24, pady=(8, 0))
        self.slider_fin = ctk.CTkSlider(
            self, from_=0, to=self._duracion,
            number_of_steps=max(1, int(self._duracion * 10)),
            command=self._al_mover_fin)
        self.slider_fin.pack(fill="x", padx=24)
        self.slider_fin.set(self._fin)

        # Qué límite fija un clic en la transcripción o en la onda.
        ctk.CTkLabel(
            self, text="Un clic en una palabra o en la onda fija:",
            font=ctk.CTkFont(size=12), text_color=SILENCIO,
            anchor="w").pack(fill="x", padx=24, pady=(12, 4))
        self.boton_limite = ctk.CTkSegmentedButton(
            self, values=["Editar inicio", "Editar fin"],
            command=self._al_elegir_limite)
        self.boton_limite.pack(anchor="w", padx=24)
        self.boton_limite.set("Editar inicio")

        # Transcripción clicable del tramo.
        self.texto = tk.Text(self, height=6, wrap="word", bg=BG, fg=TEXTO,
                             relief="flat", highlightthickness=0)
        self.texto.pack(fill="x", padx=24, pady=(8, 4))
        self.texto.bind("<Key>", lambda _e: "break")  # solo lectura
        self._palabras = editor.palabras_entre(
            segmentos, self._inicio, self._fin,
            margen=editor.MARGEN_CONTEXTO)
        self._pintar_transcripcion()

        # Texto que quedará en el clip con los límites actuales.
        self.etiqueta_texto = ctk.CTkLabel(
            self, text="", font=ctk.CTkFont(size=12),
            text_color=SILENCIO, wraplength=560, justify="left",
            anchor="w")
        self.etiqueta_texto.pack(fill="x", padx=24, pady=(4, 4))

        fila = ctk.CTkFrame(self, fg_color="transparent")
        fila.pack(fill="x", padx=24, pady=(8, 8))
        ctk.CTkButton(
            fila, text="Guardar", fg_color=AZUL, hover_color=AZUL_HOVER,
            command=self._guardar,
        ).pack(side="left")
        ctk.CTkButton(
            fila, text="Cancelar", fg_color=TARJETA, hover_color=BORDE,
            text_color=TEXTO, command=self.destroy,
        ).pack(side="left", padx=(8, 0))
        self._actualizar_etiquetas()

    # -- Forma de onda ---------------------------------------------------

    def _cargar_forma(self) -> None:
        self._muestras = editor.extraer_muestras_audio(
            self._ruta_video, self._ventana_inicio, self._ventana_fin)
        self._forma_lista.set()

    def _revisar_forma(self) -> None:
        if not self.winfo_exists():
            return
        if self._forma_lista.is_set():
            self._actualizar_forma()
        else:
            try:
                self.after(100, self._revisar_forma)
            except tk.TclError:
                pass

    def _actualizar_forma(self) -> None:
        if self._muestras is None:
            return
        if not self._muestras:
            self.etiqueta_forma.configure(text="Sin audio en este tramo")
            return
        ancho_ventana = max(0.1, self._ventana_fin - self._ventana_inicio)
        seleccion = ((self._inicio - self._ventana_inicio) / ancho_ventana,
                     (self._fin - self._ventana_inicio) / ancho_ventana)
        imagen = editor.imagen_waveform(
            self._muestras, 560, 90, color_fondo=BG, color_onda=AZUL,
            color_seleccion=ROJO, seleccion=seleccion)
        self._imagen_forma = ctk.CTkImage(imagen, size=(560, 90))
        self.etiqueta_forma.configure(image=self._imagen_forma, text="")

    # -- Transcripción ---------------------------------------------------

    def _pintar_transcripcion(self) -> None:
        """Escribe las palabras con una etiqueta por palabra (clic)."""
        self.texto.configure(state="normal")
        self.texto.delete("1.0", "end")
        for i, palabra in enumerate(self._palabras):
            etiqueta = "palabra_%d" % i
            self.texto.insert("end", palabra["word"], etiqueta)
            self.texto.tag_bind(
                etiqueta, "<Button-1>",
                lambda _e, p=palabra: self._al_clic_palabra(p))
        self._colorear_transcripcion()

    def _colorear_transcripcion(self) -> None:
        """Las palabras dentro del clip en claro, las de fuera en gris."""
        for i, palabra in enumerate(self._palabras):
            etiqueta = "palabra_%d" % i
            dentro = (palabra["start"] >= self._inicio
                      and palabra["end"] <= self._fin)
            self.texto.tag_config(
                etiqueta,
                foreground=TEXTO if dentro else SILENCIO)

    # -- Límites ---------------------------------------------------------

    def _al_elegir_limite(self, valor: str) -> None:
        self._limite_activo = ("inicio" if valor == "Editar inicio"
                               else "fin")

    def _al_mover_inicio(self, valor: float) -> None:
        self._fijar_inicio(float(valor))

    def _al_mover_fin(self, valor: float) -> None:
        self._fijar_fin(float(valor))

    def _fijar_inicio(self, tiempo: float) -> None:
        self._inicio = min(max(0.0, tiempo),
                           self._fin - editor.DURACION_MINIMA_CLIP)
        self.slider_inicio.set(self._inicio)
        self._actualizar_etiquetas()

    def _fijar_fin(self, tiempo: float) -> None:
        self._fin = max(min(self._duracion, tiempo),
                        self._inicio + editor.DURACION_MINIMA_CLIP)
        self.slider_fin.set(self._fin)
        self._actualizar_etiquetas()

    def _al_clic_palabra(self, palabra: dict) -> None:
        if self._limite_activo == "inicio":
            self._fijar_inicio(palabra["start"])
            # Tras fijar el inicio, lo natural es fijar el fin.
            self._limite_activo = "fin"
            self.boton_limite.set("Editar fin")
        else:
            self._fijar_fin(palabra["end"])

    def _al_clic_onda(self, evento) -> None:
        # La imagen de la onda siempre tiene 560 px de ancho (el
        # ancho configurado de la etiqueta); winfo_width() puede dar 1
        # si la ventana aún no está mapeada.
        ancho = self.etiqueta_forma.cget("width") or 560
        fraccion = min(1.0, max(0.0, evento.x / ancho))
        tiempo = (self._ventana_inicio
                  + fraccion * (self._ventana_fin - self._ventana_inicio))
        if self._limite_activo == "inicio":
            self._fijar_inicio(tiempo)
            self._limite_activo = "fin"
            self.boton_limite.set("Editar fin")
        else:
            self._fijar_fin(tiempo)

    def _actualizar_etiquetas(self) -> None:
        self.etiqueta_inicio.configure(
            text="Inicio: %s" % editor.formato_tiempo(self._inicio))
        self.etiqueta_fin.configure(
            text="Fin: %s  (%s)"
            % (editor.formato_tiempo(self._fin),
               editor.formato_tiempo(self._fin - self._inicio)))
        texto = editor.texto_entre(self._segmentos,
                                   self._inicio, self._fin)
        if len(texto) > 160:
            texto = texto[:157] + "…"
        self.etiqueta_texto.configure(
            text="Contenido: %s" % (texto or "—"))
        self._colorear_transcripcion()
        self._actualizar_forma()

    def _guardar(self) -> None:
        self._al_guardar(self._inicio, self._fin)
        self.destroy()


class DialogoResultadoExportacion(ctk.CTkToplevel):
    """Resumen al terminar la exportación: lista de éxito/fallo por
    clip y botón para abrir la carpeta de salida."""

    def __init__(self, padre, resultados, carpeta_salida,
                 al_abrir_carpeta) -> None:
        super().__init__(padre)
        self.title("Exportación terminada")
        self.geometry("480x420")
        self.resizable(False, False)
        self.configure(fg_color=PANEL)
        self.transient(padre)
        self.grab_set()
        self._carpeta = carpeta_salida
        self._al_abrir_carpeta = al_abrir_carpeta
        ok = sum(1 for r in resultados if r.ok)
        ctk.CTkLabel(self, text="%d de %d clip(s) exportados."
                     % (ok, len(resultados)),
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=TEXTO).pack(pady=(16, 4))
        lista = ctk.CTkScrollableFrame(
            self, fg_color="transparent",
            scrollbar_button_color=BORDE)
        lista.pack(fill="both", expand=True, padx=16, pady=(8, 4))
        for resultado in resultados:
            if resultado.ok:
                texto = "✓ %s" % resultado.trabajo.nombre
                color = VERDE
            elif resultado.cancelado:
                texto = "⊘ %s — cancelado" % resultado.trabajo.nombre
                color = SILENCIO
            else:
                texto = "✗ %s — %s" % (resultado.trabajo.nombre,
                                       resultado.error or "error")
                color = ROJO
            ctk.CTkLabel(lista, text=texto,
                         font=ctk.CTkFont(size=12), text_color=color,
                         anchor="w", wraplength=400,
                         justify="left").pack(anchor="w", fill="x",
                                              pady=2)
        fila = ctk.CTkFrame(self, fg_color="transparent")
        fila.pack(fill="x", padx=16, pady=(8, 12))
        self.boton_abrir = ctk.CTkButton(
            fila, text="Abrir carpeta", fg_color=AZUL,
            hover_color=AZUL_HOVER, command=self._abrir)
        self.boton_abrir.pack(side="left")
        ctk.CTkButton(
            fila, text="Cerrar", fg_color=TARJETA, hover_color=BORDE,
            text_color=TEXTO, command=self.destroy,
        ).pack(side="left", padx=(8, 0))

    def _abrir(self) -> None:
        self._al_abrir_carpeta(self._carpeta)


def _crear_carpeta_salida() -> str:
    """Devuelve una carpeta de salida usable.

    Intenta en orden: Videos/ClipIA, ~/ClipIA y una carpeta 'salida'
    junto a la app. La carpeta Videos de Windows a veces está
    redirigida o dañada (OneDrive, enlaces rotos) y no se puede crear
    nada dentro de ella, así que nunca se queda con una sola opción.
    """
    base_app = os.path.dirname(os.path.abspath(__file__))
    inicio = os.path.expanduser("~")
    candidatos = [
        os.path.join(inicio, "Videos", "ClipIA"),
        os.path.join(inicio, "ClipIA"),
        os.path.join(base_app, "salida"),
    ]
    for carpeta in candidatos:
        try:
            os.makedirs(carpeta, exist_ok=True)
            if os.path.isdir(carpeta):
                return carpeta
        except OSError:
            continue
    return candidatos[0]


def _limpiar_temps_vista_previa() -> None:
    """Borra los temporales de vistas previas y miniaturas de sesiones
    anteriores (B10: quedaban huérfanos al cerrar la app)."""
    base = tempfile.gettempdir()
    try:
        nombres = os.listdir(base)
    except OSError:
        return
    for nombre in nombres:
        if nombre.startswith(("clipia_vista_previa_", "clipia_miniaturas_")):
            shutil.rmtree(os.path.join(base, nombre), ignore_errors=True)


def _claves_seleccion(clips: list[dict]) -> list:
    """Claves únicas por clip para preservar la selección.

    (video, inicio, fin) más un índice de ocurrencia: dos clips con
    los mismos tiempos (p. ej. uno editado sobre otro, o dos manuales
    iguales) no colisionan en el diccionario de selección.
    """
    vistos: dict = {}
    claves = []
    for clip in clips:
        clave = (clip.get("video"), clip["start"], clip["end"])
        n = vistos.get(clave, 0)
        vistos[clave] = n + 1
        claves.append((clave, n))
    return claves


class AppClipIA(DnDWrapper, ctk.CTk):
    """Ventana principal de ClipIA.

    El mixin DnDWrapper añade drop_target_register/dnd_bind para el
    arrastrar y soltar; sin tkinterdnd2 es `object` y el DnD queda
    desactivado (ver _activar_dnd).
    """

    def __init__(self) -> None:
        super().__init__()
        ctk.set_appearance_mode("dark")
        self.title("ClipIA — Estudio de clips")
        self.geometry("1120x720")
        self.minsize(960, 620)
        self.configure(fg_color=BG)
        # B10: limpiar temporales de sesiones anteriores y limpiar las
        # miniaturas al cerrar.
        _limpiar_temps_vista_previa()
        self.protocol("WM_DELETE_WINDOW", self._al_cerrar)

        # Estado
        self.ruta_video = None
        self.duracion_video = 0.0
        self.segmentos = []
        # Fase 3: la cola multi-video analiza varios videos; cada uno
        # guarda su transcripción y duración por ruta, y cada clip
        # recuerda de qué video viene (clip["video"]). `segmentos` y
        # `duracion_video` siguen siendo los del video actual (el
        # último analizado) para compatibilidad.
        self.segmentos_por_video: dict[str, list] = {}
        self.duracion_por_video: dict[str, float] = {}
        self.cola_videos: list[dict] = []  # {"ruta", "estado", "error"}
        self.candidatos = []       # dicts con start, end, score, text
        self.seleccion = []        # lista de tk.BooleanVar, una por clip
        self.config = cargar_config()
        carpeta_guardada = self.config.get("carpeta_salida") or ""
        if carpeta_guardada:
            try:
                os.makedirs(carpeta_guardada, exist_ok=True)
                self.carpeta_salida = carpeta_guardada
            except OSError:
                self.carpeta_salida = _crear_carpeta_salida()
        else:
            self.carpeta_salida = _crear_carpeta_salida()
        self.ocupado = False
        self._cancelar_exportacion: threading.Event | None = None
        self.seguir_rostros = tk.BooleanVar(
            value=bool(self.config.get("seguir_rostros", True)))
        self._imagenes_miniaturas = []
        self._dir_miniaturas = None
        self._cola_ui = queue.Queue()
        self.after(100, self._procesar_cola)

        self._construir_encabezado()
        self._construir_cuerpo()
        self._construir_pie()
        self._ir_paso(0)
        self._activar_dnd()
        # La detección del codificador tarda ~1 s por prueba: se hace en
        # un hilo para no retrasar el arranque.
        threading.Thread(target=self._detectar_encoder_inicio,
                         daemon=True).start()

    def _activar_dnd(self) -> None:
        """Activa el arrastrar y soltar en la ventana (si está
        tkinterdnd2). Un fallo aquí no tumba la app: el DnD queda
        desactivado y se registra en el log."""
        self._dnd_activo = False
        if not _DND_DISPONIBLE:
            return
        try:
            dnd_require(self)
            self.drop_target_register(DND_FILES, DND_TEXT)
            self.dnd_bind("<<Drop>>", self._al_soltar)
            self.dnd_bind("<<DropEnter>>", self._al_entrar_arrastre)
            self.dnd_bind("<<DropLeave>>", self._al_salir_arrastre)
            self._dnd_activo = True
        except Exception:
            log.warning("arrastrar y soltar no disponible", exc_info=True)

    def _al_entrar_arrastre(self, _evento) -> None:
        if not self.ocupado:
            self._estado("Suelta los archivos para añadirlos.", None)

    def _al_salir_arrastre(self, _evento) -> None:
        if not self.ocupado:
            self._estado("Listo.", 0)

    def _al_soltar(self, evento) -> None:
        """Archivos soltados sobre la ventana: un video va al campo
        de archivo; varios, a la cola multi-video. Un texto soltado
        que sea una URL va al campo de URL."""
        if self.ocupado:
            return
        try:
            datos = self.tk.splitlist(evento.data)
        except tk.TclError:
            datos = [evento.data]
        archivos = [d for d in datos if os.path.isfile(d)]
        if not archivos and evento.data:
            # Respaldo: si la fuente entrega la ruta sin entrecomillar
            # en formato Tcl, splitlist destroza las barras invertidas
            # de Windows; la ruta cruda sigue siendo un archivo real.
            crudo = evento.data.strip()
            if crudo and os.path.isfile(crudo):
                archivos = [crudo]
        if archivos:
            videos = [a for a in archivos
                      if a.lower().endswith((".mp4", ".mkv", ".mov",
                                             ".webm", ".avi"))]
            if not videos:
                messagebox.showinfo(
                    "ClipIA", "Los archivos soltados no son videos.")
                return
            if len(videos) == 1 and not self.cola_videos:
                self.entrada_archivo.delete(0, "end")
                self.entrada_archivo.insert(0, videos[0])
                self.entrada_url.delete(0, "end")
            else:
                self._agregar_a_cola(videos)
            self._estado("Listo.", 0)
            return
        texto = (evento.data or "").strip()
        if texto.startswith(("http://", "https://")):
            self.entrada_url.delete(0, "end")
            self.entrada_url.insert(0, texto)
            self.entrada_archivo.delete(0, "end")
            self._estado("Listo.", 0)

    # -- Construcción de la interfaz -------------------------------------

    def _construir_encabezado(self) -> None:
        barra = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=0, height=64)
        barra.pack(fill="x")
        barra.pack_propagate(False)

        ctk.CTkLabel(
            barra, text="ClipIA", font=ctk.CTkFont(size=24, weight="bold"),
            text_color=TEXTO,
        ).pack(side="left", padx=(20, 6), pady=12)
        ctk.CTkLabel(
            barra, text="Estudio de clips",
            font=ctk.CTkFont(size=13), text_color=SILENCIO,
        ).pack(side="left", pady=(20, 12))

        # Indicador de pasos (es una secuencia real: Cargar -> ... -> Exportar)
        self._etiquetas_pasos = []
        marco_pasos = ctk.CTkFrame(barra, fg_color="transparent")
        marco_pasos.pack(side="right", padx=20)
        for i, nombre in enumerate(PASOS):
            etiqueta = ctk.CTkLabel(
                marco_pasos, text="%d · %s" % (i + 1, nombre),
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=SILENCIO, fg_color=TARJETA, corner_radius=12,
                width=110, height=28,
            )
            etiqueta.pack(side="left", padx=3)
            self._etiquetas_pasos.append(etiqueta)

    def _construir_cuerpo(self) -> None:
        cuerpo = ctk.CTkFrame(self, fg_color="transparent")
        cuerpo.pack(fill="both", expand=True, padx=16, pady=16)

        # --- Columna izquierda: origen y análisis ---
        # Con desplazamiento: la cola multi-video y los proyectos
        # (Fase 3) alargan esta columna más que la altura de la ventana.
        izquierda = ctk.CTkScrollableFrame(
            cuerpo, fg_color=PANEL, corner_radius=12, width=360,
            scrollbar_button_color=BORDE)
        izquierda.pack(side="left", fill="y", padx=(0, 12))
        izquierda.pack_propagate(False)

        ctk.CTkLabel(
            izquierda, text="Origen del video",
            font=ctk.CTkFont(size=15, weight="bold"), text_color=TEXTO,
        ).pack(anchor="w", padx=16, pady=(16, 8))

        self.entrada_archivo = ctk.CTkEntry(
            izquierda,
            placeholder_text="Archivo de video (mp4, mkv, mov, webm)",
            height=36)
        self.entrada_archivo.pack(fill="x", padx=16)
        self.boton_examinar = ctk.CTkButton(
            izquierda, text="Examinar…", fg_color=TARJETA,
            hover_color=BORDE, text_color=TEXTO, height=32,
            command=self._elegir_archivo,
        )
        self.boton_examinar.pack(anchor="w", padx=16, pady=(8, 4))

        ctk.CTkLabel(
            izquierda, text="o pega una URL de YouTube",
            font=ctk.CTkFont(size=12), text_color=SILENCIO,
        ).pack(anchor="w", padx=16, pady=(12, 4))
        self.entrada_url = ctk.CTkEntry(
            izquierda, placeholder_text="https://www.youtube.com/watch?v=…",
            height=36)
        self.entrada_url.pack(fill="x", padx=16)
        self.boton_pegar_url = ctk.CTkButton(
            izquierda, text="Pegar URL", fg_color=TARJETA,
            hover_color=BORDE, text_color=TEXTO, height=30,
            command=self._pegar_url,
        )
        self.boton_pegar_url.pack(anchor="w", padx=16, pady=(8, 4))

        self.boton_analizar = ctk.CTkButton(
            izquierda, text="Analizar video", fg_color=AZUL,
            hover_color=AZUL_HOVER, height=40,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._analizar,
        )
        self.boton_analizar.pack(fill="x", padx=16, pady=(16, 8))

        self.etiqueta_video = ctk.CTkLabel(
            izquierda, text="Sin video cargado", font=ctk.CTkFont(size=12),
            text_color=SILENCIO, wraplength=320, justify="left")
        self.etiqueta_video.pack(anchor="w", padx=16, pady=(4, 4))

        ctk.CTkLabel(
            izquierda, text="Carpeta de salida",
            font=ctk.CTkFont(size=13, weight="bold"), text_color=TEXTO,
        ).pack(anchor="w", padx=16, pady=(16, 4))
        self.entrada_salida = ctk.CTkEntry(izquierda, height=32)
        self.entrada_salida.insert(0, self.carpeta_salida)
        self.entrada_salida.pack(fill="x", padx=16)
        self.boton_carpeta = ctk.CTkButton(
            izquierda, text="Cambiar carpeta", fg_color=TARJETA,
            hover_color=BORDE, text_color=TEXTO, height=30,
            command=self._elegir_salida,
        )
        self.boton_carpeta.pack(anchor="w", padx=16, pady=(8, 4))

        self.check_rostros = ctk.CTkCheckBox(
            izquierda, text="Seguir rostros al exportar",
            variable=self.seguir_rostros,
            font=ctk.CTkFont(size=12), text_color=TEXTO,
            checkbox_width=18, checkbox_height=18)
        self.check_rostros.pack(anchor="w", padx=16, pady=(12, 4))

        self.boton_ajustes = ctk.CTkButton(
            izquierda, text="⚙ Ajustes", fg_color=TARJETA,
            hover_color=BORDE, text_color=TEXTO, height=30,
            command=self._abrir_ajustes,
        )
        self.boton_ajustes.pack(anchor="w", padx=16, pady=(8, 4))

        ctk.CTkLabel(
            izquierda, text="Cola de videos",
            font=ctk.CTkFont(size=13, weight="bold"), text_color=TEXTO,
        ).pack(anchor="w", padx=16, pady=(16, 4))
        self.marco_cola = ctk.CTkFrame(izquierda, fg_color="transparent")
        self.marco_cola.pack(fill="x", padx=16)
        self.etiqueta_cola_vacia = ctk.CTkLabel(
            self.marco_cola, text="Sin videos en cola",
            font=ctk.CTkFont(size=12), text_color=SILENCIO, anchor="w")
        self.etiqueta_cola_vacia.pack(anchor="w")
        fila_cola = ctk.CTkFrame(izquierda, fg_color="transparent")
        fila_cola.pack(fill="x", padx=16, pady=(8, 4))
        self.boton_agregar_cola = ctk.CTkButton(
            fila_cola, text="Añadir videos…", fg_color=TARJETA,
            hover_color=BORDE, text_color=TEXTO, height=30, width=140,
            command=self._agregar_videos_cola,
        )
        self.boton_agregar_cola.pack(side="left")
        self.boton_analizar_cola = ctk.CTkButton(
            fila_cola, text="Analizar cola", fg_color=AZUL,
            hover_color=AZUL_HOVER, text_color="white", height=30,
            width=130, command=self._analizar_cola,
        )
        self.boton_analizar_cola.pack(side="left", padx=(8, 0))

        ctk.CTkLabel(
            izquierda, text="Proyecto",
            font=ctk.CTkFont(size=13, weight="bold"), text_color=TEXTO,
        ).pack(anchor="w", padx=16, pady=(16, 4))
        fila_proyecto = ctk.CTkFrame(izquierda, fg_color="transparent")
        fila_proyecto.pack(fill="x", padx=16, pady=(4, 4))
        self.boton_guardar_proyecto = ctk.CTkButton(
            fila_proyecto, text="Guardar proyecto", fg_color=TARJETA,
            hover_color=BORDE, text_color=TEXTO, height=30, width=140,
            command=self._guardar_proyecto,
        )
        self.boton_guardar_proyecto.pack(side="left")
        self.boton_abrir_proyecto = ctk.CTkButton(
            fila_proyecto, text="Abrir proyecto", fg_color=TARJETA,
            hover_color=BORDE, text_color=TEXTO, height=30, width=130,
            command=self._abrir_proyecto,
        )
        self.boton_abrir_proyecto.pack(side="left", padx=(8, 0))

        # --- Columna derecha: lista de clips ---
        derecha = ctk.CTkFrame(cuerpo, fg_color=PANEL, corner_radius=12)
        derecha.pack(side="left", fill="both", expand=True)

        cabecera = ctk.CTkFrame(derecha, fg_color="transparent")
        cabecera.pack(fill="x", padx=16, pady=(16, 8))
        ctk.CTkLabel(
            cabecera, text="Clips automáticos",
            font=ctk.CTkFont(size=15, weight="bold"), text_color=TEXTO,
        ).pack(side="left")
        self.etiqueta_conteo = ctk.CTkLabel(
            cabecera, text="", font=ctk.CTkFont(size=12),
            text_color=SILENCIO)
        self.etiqueta_conteo.pack(side="left", padx=(8, 0))

        self.boton_seleccionar = ctk.CTkButton(
            cabecera, text="Seleccionar todo", fg_color=TARJETA,
            hover_color=BORDE, text_color=TEXTO, height=30, width=130,
            command=self._seleccionar_todo)
        self.boton_seleccionar.pack(side="right", padx=(6, 0))
        self.boton_crear_clip = ctk.CTkButton(
            cabecera, text="Crear clip", fg_color=TARJETA, hover_color=BORDE,
            text_color=TEXTO, height=30, width=110,
            command=self._crear_clip_manual,
        )
        self.boton_crear_clip.pack(side="right")
        self.boton_ollama = ctk.CTkButton(
            cabecera, text="✨ Reordenar con IA local", fg_color=TARJETA,
            hover_color=BORDE, text_color=TEXTO, height=30, width=200,
            command=self._reordenar_ollama,
        )
        self.boton_ollama.pack(side="right", padx=(0, 6))

        self.lista_clips = ctk.CTkScrollableFrame(
            derecha, fg_color="transparent", scrollbar_button_color=BORDE)
        self.lista_clips.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self.etiqueta_vacia = ctk.CTkLabel(
            self.lista_clips,
            text="Aquí aparecerán los clips.\n"
                 "Carga un video y pulsa «Analizar video».",
            font=ctk.CTkFont(size=13), text_color=SILENCIO, justify="center")
        self.etiqueta_vacia.pack(pady=60)

    def _construir_pie(self) -> None:
        pie = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=0, height=96)
        pie.pack(fill="x")
        pie.pack_propagate(False)

        izquierda_pie = ctk.CTkFrame(pie, fg_color="transparent")
        izquierda_pie.pack(side="left", padx=20, pady=10, anchor="nw")
        self.etiqueta_estado = ctk.CTkLabel(
            izquierda_pie, text="Listo.", font=ctk.CTkFont(size=12),
            text_color=SILENCIO, anchor="w")
        self.etiqueta_estado.pack(anchor="w")
        self.barra_progreso = ctk.CTkProgressBar(
            izquierda_pie, width=420, height=12, progress_color=ROJO)
        self.barra_progreso.pack(anchor="w", pady=(6, 0))
        self.barra_progreso.set(0)
        self.etiqueta_encoder = ctk.CTkLabel(
            izquierda_pie, text="Codificador: detectando…",
            font=ctk.CTkFont(size=11), text_color=SILENCIO, anchor="w")
        self.etiqueta_encoder.pack(anchor="w", pady=(4, 0))

        self.boton_exportar = ctk.CTkButton(
            pie, text="Descargar clips", fg_color=ROJO, hover_color=ROJO_HOVER,
            height=44, width=200, font=ctk.CTkFont(size=15, weight="bold"),
            command=self._exportar)
        self.boton_exportar.pack(side="right", padx=20, pady=26)
        self.boton_cancelar = ctk.CTkButton(
            pie, text="Cancelar", fg_color=TARJETA, hover_color=BORDE,
            text_color=TEXTO, height=44, width=110,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._cancelar_exportar, state="disabled")
        self.boton_cancelar.pack(side="right", padx=(0, 10), pady=26)

    # -- Utilidades de interfaz ------------------------------------------

    def _ui(self, funcion: Callable, *args, **kwargs) -> None:
        """Ejecuta `funcion` en el hilo principal (seguro desde hilos)."""
        self._cola_ui.put((funcion, args, kwargs))

    def _procesar_cola(self) -> None:
        try:
            while True:
                funcion, args, kwargs = self._cola_ui.get_nowait()
                try:
                    funcion(*args, **kwargs)
                except Exception:
                    # Un callback fallido no puede matar el actualizador:
                    # se registra y se sigue con el siguiente.
                    traceback.print_exc()
        except queue.Empty:
            pass
        finally:
            self.after(100, self._procesar_cola)

    def _ir_paso(self, indice: int) -> None:
        for i, etiqueta in enumerate(self._etiquetas_pasos):
            if i == indice:
                etiqueta.configure(fg_color=ROJO, text_color="white")
            elif i < indice:
                etiqueta.configure(fg_color=VERDE, text_color="white")
            else:
                etiqueta.configure(fg_color=TARJETA, text_color=SILENCIO)

    def _estado(self, texto: str, progreso: float | None = None) -> None:
        self.etiqueta_estado.configure(text=texto)
        if progreso is not None:
            self.barra_progreso.set(min(1.0, max(0.0, progreso)))

    def _bloquear(self, bloqueado: bool) -> None:
        # B10: deshabilitar también los botones y entradas que cambian
        # el trabajo en curso (antes solo 3 botones).
        self.ocupado = bloqueado
        estado = "disabled" if bloqueado else "normal"
        self.boton_analizar.configure(state=estado)
        self.boton_exportar.configure(state=estado)
        self.boton_seleccionar.configure(state=estado)
        self.boton_crear_clip.configure(state=estado)
        self.boton_ollama.configure(state=estado)
        self.boton_examinar.configure(state=estado)
        self.boton_carpeta.configure(state=estado)
        self.boton_ajustes.configure(state=estado)
        self.boton_pegar_url.configure(state=estado)
        self.boton_agregar_cola.configure(state=estado)
        self.boton_analizar_cola.configure(state=estado)
        self.boton_guardar_proyecto.configure(state=estado)
        self.boton_abrir_proyecto.configure(state=estado)
        self.check_rostros.configure(state=estado)
        self.entrada_archivo.configure(state=estado)
        self.entrada_url.configure(state=estado)
        self.entrada_salida.configure(state=estado)

    def _detectar_encoder_inicio(self) -> None:
        """Detecta el codificador en segundo plano y actualiza la etiqueta."""
        encoder = detectar_encoder(self.config.get("encoder", "auto"))
        self._ui(self.etiqueta_encoder.configure,
                 text="Codificador: %s" % descripcion_encoder(encoder))

    def _abrir_ajustes(self) -> None:
        if self.ocupado:
            return
        DialogoAjustes(self, self.config, self._al_guardar_ajustes)

    def _al_guardar_ajustes(self, valores: dict) -> None:
        self.config.update(valores)
        try:
            guardar_config(self.config)
        except OSError:
            log.warning("no se pudo guardar la configuración", exc_info=True)
        threading.Thread(target=self._detectar_encoder_inicio,
                         daemon=True).start()

    def _al_cerrar(self) -> None:
        """Cancela el trabajo en curso, mata los ffmpeg hijos y cierra
        la ventana (B10 + Fase 1: nada de procesos huérfanos).

        Los hilos de trabajo son daemon y mueren con el intérprete,
        pero los ffmpeg hijos NO morirían solos: por eso se cancelan
        primero (para que la cola borre los parciales) y se matan
        después los que sigan vivos.
        """
        if self._cancelar_exportacion is not None:
            self._cancelar_exportacion.set()
        matar_todos()
        if self._dir_miniaturas:
            shutil.rmtree(self._dir_miniaturas, ignore_errors=True)
            self._dir_miniaturas = None
        try:
            self.config["carpeta_salida"] = self.carpeta_salida
            self.config["seguir_rostros"] = self.seguir_rostros.get()
            guardar_config(self.config)
        except OSError:
            pass
        self.destroy()

    # -- Acciones ----------------------------------------------------------

    def _pegar_url(self) -> None:
        """Pega una URL de YouTube desde el portapapeles."""
        try:
            texto = self.clipboard_get().strip()
        except tk.TclError:
            messagebox.showinfo("ClipIA",
                                "El portapapeles no tiene texto.")
            return
        if not texto.startswith(("http://", "https://")):
            messagebox.showinfo(
                "ClipIA",
                "El portapapeles no tiene una URL (debe empezar por "
                "http:// o https://).")
            return
        self.entrada_url.delete(0, "end")
        self.entrada_url.insert(0, texto)
        self.entrada_archivo.delete(0, "end")

    def _elegir_archivo(self) -> None:
        ruta = filedialog.askopenfilename(
            title="Elegir video",
            filetypes=[("Videos", "*.mp4 *.mkv *.mov *.webm *.avi"),
                       ("Todos los archivos", "*.*")])
        if ruta:
            self.entrada_archivo.delete(0, "end")
            self.entrada_archivo.insert(0, ruta)
            self.entrada_url.delete(0, "end")
            self.etiqueta_video.configure(
                text="Video: %s" % os.path.basename(ruta))

    def _elegir_salida(self) -> None:
        carpeta = filedialog.askdirectory(title="Carpeta de salida")
        if carpeta:
            self.carpeta_salida = carpeta
            self.entrada_salida.delete(0, "end")
            self.entrada_salida.insert(0, carpeta)

    def _asegurar_carpeta_salida(self) -> None:
        """Crea la carpeta de salida; si no se puede, cambia a una
        alternativa que funcione y avisa al usuario."""
        self.carpeta_salida = self.entrada_salida.get().strip() \
            or self.carpeta_salida
        try:
            os.makedirs(self.carpeta_salida, exist_ok=True)
        except OSError:
            alternativa = _crear_carpeta_salida()
            messagebox.showwarning(
                "ClipIA",
                "No se pudo usar la carpeta:\n%s\n\n"
                "Los clips se guardarán en:\n%s"
                % (self.carpeta_salida, alternativa))
            self.carpeta_salida = alternativa
            self.entrada_salida.delete(0, "end")
            self.entrada_salida.insert(0, alternativa)

    def _agregar_videos_cola(self) -> None:
        """Añade videos a la cola multi-video (sin duplicados)."""
        rutas = filedialog.askopenfilenames(
            title="Añadir videos a la cola",
            filetypes=[("Videos", "*.mp4 *.mkv *.mov *.webm *.avi"),
                       ("Todos los archivos", "*.*")])
        self._agregar_a_cola(rutas)

    def _agregar_a_cola(self, rutas) -> None:
        """Añade rutas a la cola multi-video (sin duplicados)."""
        en_cola = {v["ruta"] for v in self.cola_videos}
        for ruta in rutas:
            if ruta and ruta not in en_cola:
                self.cola_videos.append({"ruta": ruta,
                                         "estado": "pendiente",
                                         "error": None})
                en_cola.add(ruta)
        self._mostrar_cola()

    def _mostrar_cola(self) -> None:
        """Redibuja la lista de videos en cola con su estado."""
        for widget in self.marco_cola.winfo_children():
            widget.destroy()
        if not self.cola_videos:
            ctk.CTkLabel(self.marco_cola, text="Sin videos en cola",
                         font=ctk.CTkFont(size=12), text_color=SILENCIO,
                         anchor="w").pack(anchor="w")
            return
        colores = {"pendiente": SILENCIO, "analizando": AZUL,
                   "listo": VERDE, "error": ROJO}
        for video in self.cola_videos:
            estado = video["estado"]
            texto = "%s — %s" % (os.path.basename(video["ruta"]), estado)
            ctk.CTkLabel(self.marco_cola, text=texto,
                         font=ctk.CTkFont(size=12),
                         text_color=colores.get(estado, SILENCIO),
                         anchor="w").pack(anchor="w", fill="x")

    def _analizar_cola(self) -> None:
        """Analiza los videos pendientes de la cola, uno tras otro."""
        if self.ocupado:
            return
        pendientes = [v for v in self.cola_videos
                      if v["estado"] in ("pendiente", "error")]
        if not pendientes:
            messagebox.showinfo(
                "ClipIA",
                "La cola está vacía o ya está analizada.\n"
                "Usa «Añadir videos…» para agregar videos.")
            return
        self._asegurar_carpeta_salida()
        self._bloquear(True)
        self._ir_paso(1)
        threading.Thread(target=self._hilo_cola, daemon=True).start()

    def _hilo_cola(self) -> None:
        """Analiza la cola video a video; un video con error no tumba
        los demás (queda marcado como error y se sigue)."""
        pendientes = [v for v in self.cola_videos
                      if v["estado"] in ("pendiente", "error")]
        total = len(pendientes)
        listos = 0
        try:
            for i, video in enumerate(pendientes, start=1):
                video["estado"] = "analizando"
                video["error"] = None
                self._ui(self._mostrar_cola)
                nombre = os.path.basename(video["ruta"])
                try:
                    resultado = self._analizar_video(
                        video["ruta"], "",
                        lambda texto, valor, i=i, total=total, nombre=nombre:
                        self._ui(self._estado,
                                 "Video %d de %d (%s): %s"
                                 % (i, total, nombre, texto),
                                 (i - 1 + (valor or 0)) / total))
                    self._aplicar_analisis(resultado, reemplazar=False)
                    video["estado"] = "listo"
                    listos += 1
                except Exception as error:  # noqa: BLE001 - por video
                    video["estado"] = "error"
                    video["error"] = "%s: %s" % (type(error).__name__, error)
                    log.exception("error al analizar %s", video["ruta"])
                self._ui(self._mostrar_cola)
            self._ui(self._estado, "Generando miniaturas…", 0.98)
            self._generar_miniaturas()
            self._ui(self._mostrar_clips, True)
            self._ui(self._ir_paso, 2)
            self._ui(self._estado,
                     "Cola terminada: %d de %d video(s) analizados, "
                     "%d clips en total."
                     % (listos, total, len(self.candidatos)), 1.0)
        except Exception as error:  # noqa: BLE001 - mostrar cualquier error
            detalle = "%s: %s" % (type(error).__name__, error)
            log.exception("error en la cola de videos")
            self._ui(self._estado, "Error: %s" % detalle, 0)
            self._ui(messagebox.showerror, "ClipIA", detalle)
            self._ui(self._ir_paso, 0)
        finally:
            self._ui(self._bloquear, False)

    def _proyecto_actual(self) -> dict:
        """El estado actual como proyecto (videos, clips, selección).

        Solo los videos de los clips actuales (un video analizado
        antes y reemplazado no se guarda). Las miniaturas no se
        guardan: son archivos temporales que se regeneran al abrir.
        """
        videos = {c.get("video") for c in self.candidatos if c.get("video")}
        if self.ruta_video:
            videos.add(self.ruta_video)
        return {
            "videos": [{"ruta": ruta,
                        "duracion": self.duracion_por_video.get(ruta, 0.0),
                        "segmentos": self.segmentos_por_video.get(ruta, [])}
                       for ruta in sorted(videos)],
            "candidatos": [{k: v for k, v in clip.items()
                            if k != "miniatura"}
                           for clip in self.candidatos],
            "seleccion": [v.get() for v in self.seleccion],
            "carpeta_salida": self.carpeta_salida,
        }

    def _guardar_proyecto(self) -> None:
        """Guarda el proyecto actual en un archivo .clipia."""
        if not self.candidatos:
            messagebox.showinfo(
                "ClipIA", "No hay clips para guardar.\n"
                "Analiza un video primero.")
            return
        ruta = filedialog.asksaveasfilename(
            title="Guardar proyecto",
            defaultextension=".clipia",
            filetypes=[("Proyecto ClipIA", "*.clipia")])
        if not ruta:
            return
        try:
            proyecto.guardar_proyecto(ruta, self._proyecto_actual())
        except OSError as error:
            messagebox.showerror("ClipIA",
                                 "No se pudo guardar el proyecto:\n%s"
                                 % error)
            return
        self._estado("Proyecto guardado: %s" % os.path.basename(ruta), 1.0)
        log.info("proyecto guardado en %s", ruta)

    def _abrir_proyecto(self) -> None:
        """Abre un proyecto .clipia guardado."""
        if self.ocupado:
            messagebox.showinfo(
                "ClipIA", "Espera a que termine el trabajo en curso.")
            return
        ruta = filedialog.askopenfilename(
            title="Abrir proyecto",
            filetypes=[("Proyecto ClipIA", "*.clipia")])
        if not ruta:
            return
        try:
            datos = proyecto.cargar_proyecto(ruta)
        except ValueError as error:
            messagebox.showerror("ClipIA", str(error))
            return
        self._aplicar_proyecto(datos)

    def _aplicar_proyecto(self, datos: dict) -> None:
        """Restaura el estado desde un proyecto cargado.

        Los videos que ya no están en su ruta se ofrecen para
        localizarlos; si el usuario no los reubica, se conserva la
        ruta vieja (la exportación de esos clips fallará con un
        error claro) y se avisa en la barra de estado.
        """
        sin_localizar = []
        for video in datos["videos"]:
            if os.path.isfile(video["ruta"]):
                continue
            reubicar = messagebox.askyesno(
                "ClipIA",
                "El video «%s» ya no está en su ruta.\n"
                "¿Quieres localizarlo?"
                % os.path.basename(video["ruta"]))
            nueva = None
            if reubicar:
                nueva = filedialog.askopenfilename(
                    title="Localizar %s"
                    % os.path.basename(video["ruta"]),
                    filetypes=[("Videos", "*.mp4 *.mkv *.mov *.webm *.avi"),
                               ("Todos los archivos", "*.*")])
            if nueva:
                anterior = video["ruta"]
                video["ruta"] = nueva
                for clip in datos["candidatos"]:
                    if clip.get("video") == anterior:
                        clip["video"] = nueva
            else:
                sin_localizar.append(os.path.basename(video["ruta"]))
        self.segmentos_por_video = {v["ruta"]: v["segmentos"]
                                    for v in datos["videos"]}
        self.duracion_por_video = {v["ruta"]: v["duracion"]
                                   for v in datos["videos"]}
        self.candidatos = list(datos["candidatos"])
        if datos["videos"]:
            ultimo = datos["videos"][-1]
            self.ruta_video = ultimo["ruta"]
            self.duracion_video = ultimo["duracion"]
            self.segmentos = ultimo["segmentos"]
            self.etiqueta_video.configure(
                text="Video: %s · %s"
                % (os.path.basename(ultimo["ruta"]),
                   core.formato_hora(ultimo["duracion"])))
        carpeta = datos["carpeta_salida"]
        if carpeta and os.path.isdir(carpeta):
            self.carpeta_salida = carpeta
            self.entrada_salida.delete(0, "end")
            self.entrada_salida.insert(0, carpeta)
        seleccion_previa = {
            clave: datos["seleccion"][i]
            for i, clave in enumerate(
                _claves_seleccion(self.candidatos))}
        self._mostrar_clips(seleccion_previa=seleccion_previa)
        self._ir_paso(2)
        mensaje = ("Proyecto abierto: %d clip(s) de %d video(s)."
                   % (len(self.candidatos), len(datos["videos"])))
        if sin_localizar:
            mensaje += (" %d video(s) sin localizar: %s."
                        % (len(sin_localizar), ", ".join(sin_localizar)))
        self._estado(mensaje, 1.0)

        def regenerar():
            self._generar_miniaturas()
            self._ui(self._mostrar_clips, True)

        threading.Thread(target=regenerar, daemon=True).start()

    def _analizar_video(self, ruta: str, url: str, al_progreso) -> dict:
        """Analiza un video: descarga (si es URL), duración,
        transcripción y momentos. Corre en un hilo de trabajo;
        `al_progreso(texto, valor)` recibe los avances (el llamador
        los reenvía al hilo de la UI). Devuelve {"ruta_video",
        "duracion", "segmentos", "candidatos"} y marca cada candidato
        con su video (clip["video"]). Lanza la excepción si algo falla.
        """
        if url:
            al_progreso("Descargando video de YouTube…", 0)
            carpeta = os.path.join(self.carpeta_salida, "descargas")
            ruta = core.descargar_youtube(
                url, carpeta,
                progreso=lambda p: al_progreso(
                    "Descargando video de YouTube…", p),
                navegador=self.config.get("navegador_cookies",
                                          "ninguno"))
            self._ui(self.entrada_archivo.delete, 0, "end")
            self._ui(self.entrada_archivo.insert, 0, ruta)
        if not os.path.isfile(ruta):
            raise FileNotFoundError("No se encontró el archivo: %s" % ruta)
        duracion = core.obtener_duracion(ruta)
        al_progreso("Transcribiendo audio con IA…", 0)
        lote = self.config.get("lote_transcripcion", 0)
        segmentos = core.transcribir(
            ruta,
            modelo=self.config.get("modelo", "base"),
            idioma=self.config.get("idioma", "es"),
            batch_size=lote if lote else None,
            progreso_descarga=lambda p: al_progreso(
                "Descargando modelo de voz…", p),
            progreso=lambda p: al_progreso(
                "Transcribiendo audio con IA…", p))
        if not segmentos:
            raise RuntimeError("No se detectó habla en el video.")
        al_progreso("Buscando los mejores momentos…", 0.95)
        candidatos = core.detectar_momentos(segmentos, duracion,
                                            cantidad=10)
        if not candidatos:
            raise RuntimeError("No se encontraron momentos para clips.")
        for clip in candidatos:
            clip["video"] = ruta
        return {"ruta_video": ruta, "duracion": duracion,
                "segmentos": segmentos, "candidatos": candidatos}

    def _aplicar_analisis(self, resultado: dict,
                          reemplazar: bool = True) -> None:
        """Guarda un análisis terminado en el estado de la app (corre
        en el hilo de trabajo, como el resto del estado; solo los
        widgets van por la cola de UI). Con `reemplazar` los clips
        nuevos sustituyen a los anteriores (análisis de un video);
        sin él, se añaden (cola multi-video)."""
        ruta = resultado["ruta_video"]
        self.ruta_video = ruta
        self.duracion_video = resultado["duracion"]
        self.segmentos = resultado["segmentos"]
        self.segmentos_por_video[ruta] = resultado["segmentos"]
        self.duracion_por_video[ruta] = resultado["duracion"]
        if reemplazar:
            self.candidatos = list(resultado["candidatos"])
        else:
            self.candidatos.extend(resultado["candidatos"])
        self._ui(self.etiqueta_video.configure,
                 text="Video: %s · %s"
                 % (os.path.basename(ruta),
                    core.formato_hora(resultado["duracion"])))

    def _analizar(self) -> None:
        if self.ocupado:
            return
        ruta = self.entrada_archivo.get().strip()
        url = self.entrada_url.get().strip()
        if not ruta and not url:
            messagebox.showinfo(
                "ClipIA",
                "Elige un archivo de video o pega una URL de YouTube.")
            return
        self._asegurar_carpeta_salida()
        self._bloquear(True)
        self._ir_paso(1)
        threading.Thread(target=self._hilo_analizar, args=(ruta, url),
                         daemon=True).start()

    def _hilo_analizar(self, ruta: str, url: str) -> None:
        try:
            resultado = self._analizar_video(
                ruta, url,
                lambda texto, valor: self._ui(self._estado, texto, valor))
            self._aplicar_analisis(resultado, reemplazar=True)
            self._ui(self._estado, "Generando miniaturas…", 0.98)
            self._generar_miniaturas()
            self._ui(self._mostrar_clips)
            self._ui(self._ir_paso, 2)
            self._ui(self._estado,
                     "Análisis listo: %d clips encontrados."
                     % len(self.candidatos), 1.0)
        except Exception as error:  # noqa: BLE001 - mostrar cualquier error
            detalle = _detalle_error(error)
            log.exception("error en el análisis del video")
            self._ui(self._estado, "Error: %s" % detalle, 0)
            self._ui(messagebox.showerror, "ClipIA", detalle)
            self._ui(self._ir_paso, 0)
        finally:
            self._ui(self._bloquear, False)

    def _generar_miniaturas(self) -> None:
        """Genera una miniatura vertical por clip que aún no la tenga,
        en paralelo.

        Corre en el hilo de análisis. Cada miniatura es un ffmpeg
        aparte (un solo fotograma), así que 4 en paralelo recortan el
        tiempo total sin saturar la CPU. Si una falla, ese clip queda
        sin miniatura y los demás siguen. En la cola multi-video cada
        clip usa su propio video, y los clips que ya tienen miniatura
        (de un video anterior de la cola) no se regeneran.
        """
        if not self._dir_miniaturas or not os.path.isdir(
                self._dir_miniaturas):
            self._dir_miniaturas = tempfile.mkdtemp(
                prefix="clipia_miniaturas_")
        pendientes = [(i, clip) for i, clip in enumerate(self.candidatos)
                      if not clip.get("miniatura")
                      or not os.path.isfile(clip["miniatura"])]

        def generar(i_clip):
            i, clip = i_clip
            fd, ruta = tempfile.mkstemp(
                suffix=".jpg", prefix="mini_",
                dir=self._dir_miniaturas)
            os.close(fd)
            try:
                core.generar_miniatura(
                    clip.get("video") or self.ruta_video,
                    (clip["start"] + clip["end"]) / 2, ruta)
                return i, ruta
            except Exception:
                if os.path.exists(ruta):
                    os.remove(ruta)
                return i, None

        with ThreadPoolExecutor(max_workers=4) as ejecutor:
            # map conserva el orden: cada resultado vuelve a su clip.
            for i, ruta in ejecutor.map(generar, pendientes):
                self.candidatos[i]["miniatura"] = ruta

    def _mostrar_clips(self, preservar_seleccion: bool = False,
                       seleccion_previa: dict | None = None) -> None:
        # B10: al agregar un clip manual se redibuja la lista; con
        # preservar_seleccion se mantiene lo que el usuario desmarcó
        # (antes todo volvía a marcado). Tras un análisis nuevo no se
        # preserva (son otros clips). Si se pasa `seleccion_previa`
        # (reorden con Ollama), se usa ese mapa en vez de reconstruirlo
        # de la lista actual, que ya cambió de orden.
        if seleccion_previa is None:
            seleccion_previa = {}
            if preservar_seleccion:
                # Las listas pueden diferir en uno: el clip manual recién
                # agregado aún no tiene selección (queda en True).
                for i, clave in enumerate(
                        _claves_seleccion(self.candidatos)):
                    if i < len(self.seleccion):
                        seleccion_previa[clave] = self.seleccion[i].get()
        for widget in self.lista_clips.winfo_children():
            widget.destroy()
        self.seleccion = []
        self._imagenes_miniaturas = []
        videos_distintos = {c.get("video") for c in self.candidatos}
        claves = _claves_seleccion(self.candidatos)
        for i, clip in enumerate(self.candidatos, start=1):
            tarjeta = ctk.CTkFrame(self.lista_clips, fg_color=TARJETA,
                                   corner_radius=10)
            tarjeta.pack(fill="x", padx=8, pady=5)

            miniatura = clip.get("miniatura")
            if miniatura and os.path.isfile(miniatura):
                try:
                    imagen = ctk.CTkImage(Image.open(miniatura),
                                          size=(72, 128))
                    self._imagenes_miniaturas.append(imagen)
                    ctk.CTkLabel(tarjeta, image=imagen, text="").pack(
                        side="left", padx=(10, 4), pady=10)
                except Exception:
                    pass

            cuerpo = ctk.CTkFrame(tarjeta, fg_color="transparent")
            cuerpo.pack(side="left", fill="both", expand=True)

            variable = tk.BooleanVar(
                value=seleccion_previa.get(claves[i - 1], True))
            self.seleccion.append(variable)
            titulo = "Clip %d · %s · %s – %s" % (
                i, core.formato_hora(clip["end"] - clip["start"]),
                core.formato_hora(clip["start"]),
                core.formato_hora(clip["end"]))
            # Con varios videos en la lista, cada tarjeta dice de cuál
            # viene el clip.
            if len(videos_distintos) > 1 and clip.get("video"):
                titulo += " · %s" % os.path.basename(clip["video"])
            ctk.CTkCheckBox(
                cuerpo, text=titulo, variable=variable,
                font=ctk.CTkFont(size=13, weight="bold"), text_color=TEXTO,
                checkbox_width=20, checkbox_height=20,
            ).pack(anchor="w", padx=12, pady=(10, 2))

            vista_previa = clip["text"].strip()
            if len(vista_previa) > 160:
                vista_previa = vista_previa[:157] + "…"
            ctk.CTkLabel(
                cuerpo, text=vista_previa, font=ctk.CTkFont(size=12),
                text_color=SILENCIO, wraplength=420, justify="left",
            ).pack(anchor="w", padx=36, pady=(0, 10))

            ctk.CTkButton(
                tarjeta, text="▶ Vista previa", fg_color=PANEL,
                hover_color=BORDE, text_color=TEXTO, height=30, width=120,
                command=lambda c=clip: self._vista_previa(c),
            ).pack(side="right", padx=12, pady=10)
            ctk.CTkButton(
                tarjeta, text="✎ Editar", fg_color=PANEL,
                hover_color=BORDE, text_color=TEXTO, height=30, width=90,
                command=lambda c=clip: self._editar_clip(c),
            ).pack(side="right", padx=(0, 6), pady=10)

        self.etiqueta_conteo.configure(
            text="%d clips · %s de video"
            % (len(self.candidatos), core.formato_hora(self.duracion_video)))

    def _seleccionar_todo(self) -> None:
        if not self.seleccion:
            return
        todos = all(v.get() for v in self.seleccion)
        for variable in self.seleccion:
            variable.set(not todos)
        self.boton_seleccionar.configure(
            text="Quitar selección" if not todos else "Seleccionar todo")

    def _crear_clip_manual(self) -> None:
        if not self.ruta_video:
            messagebox.showinfo(
                "ClipIA", "Primero carga y analiza un video.")
            return

        def agregar(inicio, fin):
            self.candidatos.append({
                "start": inicio, "end": fin, "score": 0.0,
                "text": "Clip manual · %s – %s"
                        % (core.formato_hora(inicio), core.formato_hora(fin)),
                "video": self.ruta_video,
            })
            self._mostrar_clips(preservar_seleccion=True)

        DialogoClipManual(self, self.duracion_video, agregar)

    def _reordenar_ollama(self) -> None:
        """Reordena los clips con un LLM local (Ollama), si está
        instalado. Sin Ollama muestra las instrucciones; nunca bloquea
        la app (todo corre en un hilo)."""
        if self.ocupado:
            return
        if not self.candidatos:
            messagebox.showinfo(
                "ClipIA", "Primero carga y analiza un video.")
            return
        self._bloquear(True)
        self._estado("Comprobando la IA local…", 0)
        # La selección se captura en el hilo de la UI, antes de que el
        # reorden cambie el orden de los candidatos.
        seleccion_previa = {
            clave: v.get()
            for clave, v in zip(_claves_seleccion(self.candidatos),
                                self.seleccion, strict=False)}
        threading.Thread(target=self._hilo_reordenar_ollama,
                         args=(seleccion_previa,), daemon=True).start()

    def _hilo_reordenar_ollama(self, seleccion_previa: dict) -> None:
        try:
            if not ollama_disponible():
                self._ui(messagebox.showinfo, "ClipIA",
                         INSTRUCCIONES_INSTALACION)
                self._ui(self._estado, "Listo.", 0)
                return
            modelo = self.config.get("ollama_modelo", MODELO_DEFECTO)
            if not modelo_disponible(modelo):
                self._ui(messagebox.showinfo, "ClipIA",
                         INSTRUCCIONES_MODELO % (modelo, modelo))
                self._ui(self._estado, "Listo.", 0)
                return
            self._ui(self._estado,
                     "Reordenando con IA local… (puede tardar 1-2 min)",
                     0)
            reordenados = rerank_ollama(list(self.candidatos), modelo)
            if reordenados is None:
                self._ui(
                    self._estado,
                    "La IA local no respondió; se mantiene el orden actual.",
                    0)
                return
            # El cambio de candidatos y el redibujado ocurren juntos en
            # el hilo de la UI (la selección se conserva por tiempos).
            self._ui(self._aplicar_reorden, reordenados, seleccion_previa)
            self._ui(self._estado, "Clips reordenados con IA local.", 1.0)
        except Exception as error:  # noqa: BLE001 - mostrar cualquier error
            detalle = "%s: %s" % (type(error).__name__, error)
            log.exception("error al reordenar con Ollama")
            self._ui(self._estado, "Error: %s" % detalle, 0)
            self._ui(messagebox.showerror, "ClipIA", detalle)
        finally:
            self._ui(self._bloquear, False)

    def _aplicar_reorden(self, reordenados: list[dict],
                         seleccion_previa: dict) -> None:
        """Aplica un reorden de candidatos (corre en el hilo de la UI)."""
        self.candidatos = reordenados
        self._mostrar_clips(True, seleccion_previa)

    def _editar_clip(self, clip: dict) -> None:
        """Abre el editor de clip (sliders, onda, transcripción)."""
        if self.ocupado:
            messagebox.showinfo(
                "ClipIA", "Espera a que termine el trabajo en curso.")
            return
        video = clip.get("video") or self.ruta_video
        if not video:
            return
        segmentos = self.segmentos_por_video.get(video, self.segmentos)
        duracion = self.duracion_por_video.get(video, self.duracion_video)

        def al_guardar(inicio, fin):
            nuevo = editor.ajustar_limites(clip, segmentos, inicio, fin,
                                           duracion)
            indice = None
            for i, c in enumerate(self.candidatos):
                if c is clip:
                    indice = i
                    break
            if indice is None:
                return
            # La clave de selección es (video, inicio, fin): al cambiar
            # los tiempos hay que trasladar la selección a la clave
            # nueva para que el clip editado no vuelva a marcarse.
            # Se traslada por índice (la lista no cambia de orden).
            seleccionado = (self.seleccion[indice].get()
                            if indice < len(self.seleccion) else True)
            self.candidatos[indice] = nuevo
            seleccion_previa = {}
            for i, clave in enumerate(
                    _claves_seleccion(self.candidatos)):
                if i == indice:
                    seleccion_previa[clave] = seleccionado
                elif i < len(self.seleccion):
                    seleccion_previa[clave] = self.seleccion[i].get()
            self._mostrar_clips(seleccion_previa=seleccion_previa)

            def regenerar():
                # La miniatura era del punto medio anterior.
                self._generar_miniaturas()
                self._ui(self._mostrar_clips, True)

            threading.Thread(target=regenerar, daemon=True).start()

        DialogoEditorClip(self, clip, segmentos, video, duracion,
                          al_guardar)

    def _vista_previa(self, clip: dict) -> None:
        if self.ocupado:
            messagebox.showinfo(
                "ClipIA", "Espera a que termine el trabajo en curso.")
            return
        if not self.ruta_video:
            return
        self._bloquear(True)
        self._estado("Generando vista previa…", 0)
        video = clip.get("video") or self.ruta_video
        segmentos = self.segmentos_por_video.get(video, self.segmentos)
        threading.Thread(
            target=self._hilo_vista_previa,
            args=(clip, video, self.seguir_rostros.get(), segmentos),
            daemon=True).start()

    def _hilo_vista_previa(self, clip: dict, ruta_video: str,
                           seguir_rostros: bool,
                           segmentos: list[dict] | None = None) -> None:
        try:
            encoder = detectar_encoder(self.config.get("encoder", "auto"))
            rostros = None
            if seguir_rostros:
                rostros = detectar_rostros_con_limite(
                    ruta_video, clip["start"], clip["end"],
                    progreso=lambda p: self._ui(
                        self._estado,
                        "Detectando rostros… (%d%%)" % int(p * 100), 0))
            tmp = tempfile.mkdtemp(prefix="clipia_vista_previa_")
            ruta = os.path.join(tmp, "vista_previa.mp4")
            ruta_ass = None
            if segmentos:
                # La previa lleva los mismos subtítulos que el clip
                # final (estilo y margen actuales de los ajustes).
                ruta_ass = os.path.join(tmp, "vista_previa.ass")
                core.generar_subtitulos_ass(
                    segmentos, clip["start"], clip["end"], ruta_ass,
                    estilo=self.config.get("estilo_subtitulos",
                                           "Shorts clásico"),
                    margen_vertical=self.config.get("margen_vertical",
                                                    300))
            core.generar_vista_previa(
                ruta_video, clip["start"], clip["end"], ruta, rostros=rostros,
                progreso=lambda p: self._ui(self._estado,
                                            "Generando vista previa…", p),
                encoder=encoder, ruta_ass=ruta_ass)
            self._ui(self._abrir_archivo, ruta)
            self._ui(self._estado, "Vista previa lista.", 1.0)
        except Exception as error:  # noqa: BLE001 - mostrar cualquier error
            detalle = "%s: %s" % (type(error).__name__, error)
            log.exception("error en la vista previa")
            self._ui(self._estado, "Error: %s" % detalle, 0)
            self._ui(messagebox.showerror, "ClipIA", detalle)
        finally:
            self._ui(self._bloquear, False)

    @staticmethod
    def _abrir_archivo(ruta: str) -> None:
        """Abre un archivo con el programa predeterminado del sistema."""
        if sys.platform.startswith("win"):
            os.startfile(ruta)
        elif sys.platform == "darwin":
            subprocess.run(["open", ruta])
        else:
            subprocess.run(["xdg-open", ruta])

    def _cancelar_exportar(self) -> None:
        """Marca la cancelación: la cola mata los ffmpeg en curso,
        borra los parciales y no empieza los clips pendientes."""
        if self._cancelar_exportacion is not None:
            self._cancelar_exportacion.set()
            self._estado("Cancelando…", None)
            self.boton_cancelar.configure(state="disabled")

    def _exportar(self) -> None:
        if self.ocupado:
            return
        elegidos = [c for c, v in zip(self.candidatos, self.seleccion,
                                       strict=True)
                    if v.get()]
        if not elegidos:
            messagebox.showinfo("ClipIA", "Selecciona al menos un clip.")
            return
        self._asegurar_carpeta_salida()
        self._bloquear(True)
        self._ir_paso(3)
        self._cancelar_exportacion = threading.Event()
        self.boton_cancelar.configure(state="normal")
        threading.Thread(
            target=self._hilo_exportar,
            args=(elegidos, self.ruta_video, list(self.segmentos),
                  self.seguir_rostros.get(),
                  dict(self.segmentos_por_video)),
            daemon=True).start()

    def _hilo_exportar(self, elegidos: list[dict], ruta_video: str,
                       segmentos: list[dict], seguir_rostros: bool,
                       segmentos_por_video: dict | None = None) -> None:
        try:
            os.makedirs(self.carpeta_salida, exist_ok=True)
            total = len(elegidos)
            encoder = detectar_encoder(self.config.get("encoder", "auto"))
            workers = workers_efectivos(
                self.config.get("workers_exportacion", 0), encoder)
            cancelar = self._cancelar_exportacion or threading.Event()
            trabajos = []
            for i, clip in enumerate(elegidos, start=1):
                # Cada clip se exporta desde su propio video (cola
                # multi-video); sin "video" se usa el actual.
                video_clip = clip.get("video") or ruta_video
                base = os.path.splitext(os.path.basename(video_clip))[0]
                nombre = "%s_clip%02d_%s-%s.mp4" % (
                    base, i, core.formato_hora(clip["start"]).replace(":", ""),
                    core.formato_hora(clip["end"]).replace(":", ""))
                segmentos_clip = segmentos
                if segmentos_por_video:
                    segmentos_clip = segmentos_por_video.get(
                        video_clip, segmentos)
                trabajos.append(TrabajoExportacion(
                    clip=clip, ruta_video=video_clip,
                    segmentos=list(segmentos_clip),
                    carpeta_salida=self.carpeta_salida, nombre=nombre,
                    seguir_rostros=seguir_rostros, encoder=encoder,
                    estilo=self.config.get("estilo_subtitulos",
                                           "Shorts clásico"),
                    margen_vertical=self.config.get("margen_vertical",
                                                    300)))

            def al_progreso(fraccion, eta, terminados, total_lote, en_curso):
                if en_curso:
                    nombre, p = en_curso[0]
                    texto = "Exportando %s… (%d%%)" % (nombre, int(p * 100))
                else:
                    texto = "Exportando…"
                texto += " · %d de %d listos" % (terminados, total_lote)
                if eta is not None:
                    texto += " · quedan ~%s" % core.formato_hora(eta)
                self._ui(self._estado, texto, fraccion)

            cola = ColaExportacion(workers=workers, al_progreso=al_progreso)
            resultados = cola.exportar(trabajos, cancelar)
            ok = [r for r in resultados if r.ok]
            fallidos = [r for r in resultados
                        if not r.ok and not r.cancelado]
            cancelados = [r for r in resultados if r.cancelado]
            if cancelados and not ok:
                self._ui(self._estado, "Exportación cancelada.", 0)
                return
            if fallidos:
                detalle = "\n".join(
                    "%s: %s" % (r.trabajo.nombre, r.error)
                    for r in fallidos)
                log.warning("exportación con fallos:\n%s", detalle)
                self._ui(self._estado,
                         "Listo con errores: %d de %d clip(s) en %s"
                         % (len(ok), total, self.carpeta_salida), 1.0)
            else:
                self._ui(self._estado,
                         "Listo: %d clip(s) en %s"
                         % (len(ok), self.carpeta_salida), 1.0)
            self._ui(self._mostrar_resultado_exportacion, resultados)
        except Exception as error:  # noqa: BLE001 - mostrar cualquier error
            detalle = "%s: %s" % (type(error).__name__, error)
            log.exception("error en la exportación")
            self._ui(self._estado, "Error: %s" % detalle, 0)
            self._ui(messagebox.showerror, "ClipIA", detalle)
        finally:
            self._ui(self._bloquear, False)
            self._ui(self.boton_cancelar.configure, state="disabled")

    def _mostrar_resultado_exportacion(self, resultados) -> None:
        """Muestra el resumen de la exportación (corre en la UI)."""
        DialogoResultadoExportacion(self, resultados, self.carpeta_salida,
                                    self._abrir_archivo)


def _preparar_ruta_ejecutable() -> None:
    """En el instalador (PyInstaller), ffmpeg, ffprobe y el yt-dlp
    externo van junto al .exe: añadir esa carpeta al PATH para que
    los subprocesos los encuentren sin instalar nada más."""
    if getattr(sys, "frozen", False):
        carpeta = os.path.dirname(sys.executable)
        path = os.environ.get("PATH", "")
        if carpeta and carpeta not in path.split(os.pathsep):
            os.environ["PATH"] = carpeta + os.pathsep + path


def main() -> None:
    if "--version" in sys.argv:
        # Sin ventana: lo usa la prueba de humo del workflow de build
        # para comprobar que el .exe arranca (imports resueltos).
        print("ClipIA %s" % __version__)
        return
    _preparar_ruta_ejecutable()
    configurar_logging()
    app = AppClipIA()
    app.mainloop()


if __name__ == "__main__":
    main()
