# -*- coding: utf-8 -*-
"""
ClipIA - app de escritorio para crear clips cortos verticales con IA.

Flujo: Cargar -> Analizar -> Clips -> Exportar.
Todo corre 100% local: faster-whisper transcribe, el detector de momentos
elige los mejores fragmentos y ffmpeg exporta los clips en 1080x1920
con subtítulos quemados.
"""

import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk
from PIL import Image

import clipia_core as core

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


class DialogoClipManual(ctk.CTkToplevel):
    """Ventana pequeña para crear un clip manual (inicio y fin)."""

    def __init__(self, padre, duracion, al_agregar):
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
    def _a_segundos(texto):
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

    def _agregar(self):
        try:
            inicio = self._a_segundos(self.entrada_inicio.get())
            fin = self._a_segundos(self.entrada_fin.get())
        except ValueError:
            messagebox.showerror("ClipIA", "Usa el formato m:ss, por ejemplo 1:30.")
            return
        if inicio < 0 or fin <= inicio or fin > self._duracion:
            messagebox.showerror(
                "ClipIA",
                "Revisa los tiempos: el fin debe ser mayor que el inicio "
                "y no pasar de la duración del video.")
            return
        self._al_agregar(inicio, fin)
        self.destroy()


def _crear_carpeta_salida():
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


class AppClipIA(ctk.CTk):
    """Ventana principal de ClipIA."""

    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        self.title("ClipIA — Estudio de clips")
        self.geometry("1120x720")
        self.minsize(960, 620)
        self.configure(fg_color=BG)

        # Estado
        self.ruta_video = None
        self.duracion_video = 0.0
        self.segmentos = []
        self.candidatos = []       # dicts con start, end, score, text
        self.seleccion = []        # lista de tk.BooleanVar, una por clip
        self.carpeta_salida = _crear_carpeta_salida()
        self.ocupado = False
        self.seguir_rostros = tk.BooleanVar(value=True)
        self._imagenes_miniaturas = []
        self._dir_miniaturas = None
        self._cola_ui = queue.Queue()
        self.after(100, self._procesar_cola)

        self._construir_encabezado()
        self._construir_cuerpo()
        self._construir_pie()
        self._ir_paso(0)

    # -- Construcción de la interfaz -------------------------------------

    def _construir_encabezado(self):
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

    def _construir_cuerpo(self):
        cuerpo = ctk.CTkFrame(self, fg_color="transparent")
        cuerpo.pack(fill="both", expand=True, padx=16, pady=16)

        # --- Columna izquierda: origen y análisis ---
        izquierda = ctk.CTkFrame(cuerpo, fg_color=PANEL, corner_radius=12,
                                 width=360)
        izquierda.pack(side="left", fill="y", padx=(0, 12))
        izquierda.pack_propagate(False)

        ctk.CTkLabel(
            izquierda, text="Origen del video",
            font=ctk.CTkFont(size=15, weight="bold"), text_color=TEXTO,
        ).pack(anchor="w", padx=16, pady=(16, 8))

        self.entrada_archivo = ctk.CTkEntry(
            izquierda, placeholder_text="Archivo de video (mp4, mkv, mov, webm)",
            height=36)
        self.entrada_archivo.pack(fill="x", padx=16)
        ctk.CTkButton(
            izquierda, text="Examinar…", fg_color=TARJETA,
            hover_color=BORDE, text_color=TEXTO, height=32,
            command=self._elegir_archivo,
        ).pack(anchor="w", padx=16, pady=(8, 4))

        ctk.CTkLabel(
            izquierda, text="o pega una URL de YouTube",
            font=ctk.CTkFont(size=12), text_color=SILENCIO,
        ).pack(anchor="w", padx=16, pady=(12, 4))
        self.entrada_url = ctk.CTkEntry(
            izquierda, placeholder_text="https://www.youtube.com/watch?v=…",
            height=36)
        self.entrada_url.pack(fill="x", padx=16)

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
        ctk.CTkButton(
            izquierda, text="Cambiar carpeta", fg_color=TARJETA,
            hover_color=BORDE, text_color=TEXTO, height=30,
            command=self._elegir_salida,
        ).pack(anchor="w", padx=16, pady=(8, 4))

        self.check_rostros = ctk.CTkCheckBox(
            izquierda, text="Seguir rostros al exportar",
            variable=self.seguir_rostros,
            font=ctk.CTkFont(size=12), text_color=TEXTO,
            checkbox_width=18, checkbox_height=18)
        self.check_rostros.pack(anchor="w", padx=16, pady=(12, 4))

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
        ctk.CTkButton(
            cabecera, text="Crear clip", fg_color=TARJETA, hover_color=BORDE,
            text_color=TEXTO, height=30, width=110,
            command=self._crear_clip_manual,
        ).pack(side="right")

        self.lista_clips = ctk.CTkScrollableFrame(
            derecha, fg_color="transparent", scrollbar_button_color=BORDE)
        self.lista_clips.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self.etiqueta_vacia = ctk.CTkLabel(
            self.lista_clips,
            text="Aquí aparecerán los clips.\nCarga un video y pulsa «Analizar video».",
            font=ctk.CTkFont(size=13), text_color=SILENCIO, justify="center")
        self.etiqueta_vacia.pack(pady=60)

    def _construir_pie(self):
        pie = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=0, height=76)
        pie.pack(fill="x")
        pie.pack_propagate(False)

        self.etiqueta_estado = ctk.CTkLabel(
            pie, text="Listo.", font=ctk.CTkFont(size=12),
            text_color=SILENCIO, anchor="w")
        self.etiqueta_estado.pack(side="left", padx=20, pady=(10, 0),
                                  anchor="nw")
        self.barra_progreso = ctk.CTkProgressBar(
            pie, width=420, height=12, progress_color=ROJO)
        self.barra_progreso.pack(side="left", padx=20, pady=(32, 0),
                                 anchor="nw")
        self.barra_progreso.set(0)

        self.boton_exportar = ctk.CTkButton(
            pie, text="Descargar clips", fg_color=ROJO, hover_color=ROJO_HOVER,
            height=44, width=200, font=ctk.CTkFont(size=15, weight="bold"),
            command=self._exportar)
        self.boton_exportar.pack(side="right", padx=20, pady=16)

    # -- Utilidades de interfaz ------------------------------------------

    def _ui(self, funcion, *args, **kwargs):
        """Ejecuta `funcion` en el hilo principal (seguro desde hilos)."""
        self._cola_ui.put((funcion, args, kwargs))

    def _procesar_cola(self):
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

    def _ir_paso(self, indice):
        for i, etiqueta in enumerate(self._etiquetas_pasos):
            if i == indice:
                etiqueta.configure(fg_color=ROJO, text_color="white")
            elif i < indice:
                etiqueta.configure(fg_color=VERDE, text_color="white")
            else:
                etiqueta.configure(fg_color=TARJETA, text_color=SILENCIO)

    def _estado(self, texto, progreso=None):
        self.etiqueta_estado.configure(text=texto)
        if progreso is not None:
            self.barra_progreso.set(min(1.0, max(0.0, progreso)))

    def _bloquear(self, bloqueado):
        self.ocupado = bloqueado
        estado = "disabled" if bloqueado else "normal"
        self.boton_analizar.configure(state=estado)
        self.boton_exportar.configure(state=estado)
        self.boton_seleccionar.configure(state=estado)

    # -- Acciones ----------------------------------------------------------

    def _elegir_archivo(self):
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

    def _elegir_salida(self):
        carpeta = filedialog.askdirectory(title="Carpeta de salida")
        if carpeta:
            self.carpeta_salida = carpeta
            self.entrada_salida.delete(0, "end")
            self.entrada_salida.insert(0, carpeta)

    def _asegurar_carpeta_salida(self):
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

    def _analizar(self):
        if self.ocupado:
            return
        ruta = self.entrada_archivo.get().strip()
        url = self.entrada_url.get().strip()
        if not ruta and not url:
            messagebox.showinfo(
                "ClipIA", "Elige un archivo de video o pega una URL de YouTube.")
            return
        self._asegurar_carpeta_salida()
        self._bloquear(True)
        self._ir_paso(1)
        threading.Thread(target=self._hilo_analizar, args=(ruta, url),
                         daemon=True).start()

    def _hilo_analizar(self, ruta, url):
        try:
            if url:
                self._ui(self._estado, "Descargando video de YouTube…", 0)
                carpeta = os.path.join(self.carpeta_salida, "descargas")
                ruta = core.descargar_youtube(
                    url, carpeta,
                    progreso=lambda p: self._ui(self._estado,
                                                "Descargando video de YouTube…",
                                                p))
                self._ui(self.entrada_archivo.delete, 0, "end")
                self._ui(self.entrada_archivo.insert, 0, ruta)
            if not os.path.isfile(ruta):
                raise FileNotFoundError("No se encontró el archivo: %s" % ruta)

            self.ruta_video = ruta
            self.duracion_video = core.obtener_duracion(ruta)
            self._ui(self.etiqueta_video.configure,
                     text="Video: %s · %s"
                     % (os.path.basename(ruta),
                        core.formato_hora(self.duracion_video)))

            self._ui(self._estado, "Transcribiendo audio con IA…", 0)
            self.segmentos = core.transcribir(
                ruta,
                progreso=lambda p: self._ui(self._estado,
                                            "Transcribiendo audio con IA…", p))
            if not self.segmentos:
                raise RuntimeError("No se detectó habla en el video.")

            self._ui(self._estado, "Buscando los mejores momentos…", 0.95)
            self.candidatos = core.detectar_momentos(
                self.segmentos, self.duracion_video, cantidad=10)
            if not self.candidatos:
                raise RuntimeError("No se encontraron momentos para clips.")

            self._ui(self._estado, "Generando miniaturas…", 0.98)
            self._generar_miniaturas()

            self._ui(self._mostrar_clips)
            self._ui(self._ir_paso, 2)
            self._ui(self._estado,
                     "Análisis listo: %d clips encontrados."
                     % len(self.candidatos), 1.0)
        except Exception as error:  # noqa: BLE001 - mostrar cualquier error
            detalle = "%s: %s" % (type(error).__name__, error)
            self._ui(self._estado, "Error: %s" % detalle, 0)
            self._ui(messagebox.showerror, "ClipIA", detalle)
            self._ui(self._ir_paso, 0)
        finally:
            self._ui(self._bloquear, False)

    def _generar_miniaturas(self):
        """Genera una miniatura vertical por clip (corre en el hilo)."""
        if self._dir_miniaturas:
            shutil.rmtree(self._dir_miniaturas, ignore_errors=True)
        self._dir_miniaturas = tempfile.mkdtemp(prefix="clipia_miniaturas_")
        for i, clip in enumerate(self.candidatos, start=1):
            ruta = os.path.join(self._dir_miniaturas, "clip%02d.jpg" % i)
            try:
                core.generar_miniatura(
                    self.ruta_video, (clip["start"] + clip["end"]) / 2, ruta)
                clip["miniatura"] = ruta
            except Exception:
                clip["miniatura"] = None

    def _mostrar_clips(self):
        for widget in self.lista_clips.winfo_children():
            widget.destroy()
        self.seleccion = []
        self._imagenes_miniaturas = []
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

            variable = tk.BooleanVar(value=True)
            self.seleccion.append(variable)
            titulo = "Clip %d · %s · %s – %s" % (
                i, core.formato_hora(clip["end"] - clip["start"]),
                core.formato_hora(clip["start"]),
                core.formato_hora(clip["end"]))
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

        self.etiqueta_conteo.configure(
            text="%d clips · %s de video"
            % (len(self.candidatos), core.formato_hora(self.duracion_video)))

    def _seleccionar_todo(self):
        if not self.seleccion:
            return
        todos = all(v.get() for v in self.seleccion)
        for variable in self.seleccion:
            variable.set(not todos)
        self.boton_seleccionar.configure(
            text="Quitar selección" if not todos else "Seleccionar todo")

    def _crear_clip_manual(self):
        if not self.ruta_video:
            messagebox.showinfo(
                "ClipIA", "Primero carga y analiza un video.")
            return

        def agregar(inicio, fin):
            self.candidatos.append({
                "start": inicio, "end": fin, "score": 0.0,
                "text": "Clip manual · %s – %s"
                        % (core.formato_hora(inicio), core.formato_hora(fin)),
            })
            self._mostrar_clips()

        DialogoClipManual(self, self.duracion_video, agregar)

    def _vista_previa(self, clip):
        if self.ocupado:
            messagebox.showinfo(
                "ClipIA", "Espera a que termine el trabajo en curso.")
            return
        if not self.ruta_video:
            return
        self._bloquear(True)
        self._estado("Generando vista previa…", 0)
        threading.Thread(
            target=self._hilo_vista_previa,
            args=(clip, self.ruta_video, self.seguir_rostros.get()),
            daemon=True).start()

    def _hilo_vista_previa(self, clip, ruta_video, seguir_rostros):
        try:
            rostros = None
            if seguir_rostros:
                rostros = core.detectar_rostros(
                    ruta_video, clip["start"], clip["end"],
                    progreso=lambda p: self._ui(
                        self._estado,
                        "Detectando rostros… (%d%%)" % int(p * 100), 0))
            tmp = tempfile.mkdtemp(prefix="clipia_vista_previa_")
            ruta = os.path.join(tmp, "vista_previa.mp4")
            core.generar_vista_previa(
                ruta_video, clip["start"], clip["end"], ruta, rostros=rostros,
                progreso=lambda p: self._ui(self._estado,
                                            "Generando vista previa…", p))
            self._ui(self._abrir_archivo, ruta)
            self._ui(self._estado, "Vista previa lista.", 1.0)
        except Exception as error:  # noqa: BLE001 - mostrar cualquier error
            detalle = "%s: %s" % (type(error).__name__, error)
            self._ui(self._estado, "Error: %s" % detalle, 0)
            self._ui(messagebox.showerror, "ClipIA", detalle)
        finally:
            self._ui(self._bloquear, False)

    @staticmethod
    def _abrir_archivo(ruta):
        """Abre un archivo con el programa predeterminado del sistema."""
        if sys.platform.startswith("win"):
            os.startfile(ruta)
        elif sys.platform == "darwin":
            subprocess.run(["open", ruta])
        else:
            subprocess.run(["xdg-open", ruta])

    def _exportar(self):
        if self.ocupado:
            return
        elegidos = [c for c, v in zip(self.candidatos, self.seleccion)
                    if v.get()]
        if not elegidos:
            messagebox.showinfo("ClipIA", "Selecciona al menos un clip.")
            return
        self._asegurar_carpeta_salida()
        self._bloquear(True)
        self._ir_paso(3)
        threading.Thread(
            target=self._hilo_exportar,
            args=(elegidos, self.ruta_video, list(self.segmentos),
                  self.seguir_rostros.get()),
            daemon=True).start()

    def _hilo_exportar(self, elegidos, ruta_video, segmentos,
                       seguir_rostros):
        try:
            os.makedirs(self.carpeta_salida, exist_ok=True)
            base = os.path.splitext(os.path.basename(ruta_video))[0]
            total = len(elegidos)
            for i, clip in enumerate(elegidos, start=1):
                nombre = "%s_clip%02d_%s-%s.mp4" % (
                    base, i, core.formato_hora(clip["start"]).replace(":", ""),
                    core.formato_hora(clip["end"]).replace(":", ""))
                ruta_ass = os.path.join(self.carpeta_salida, "clip_tmp.ass")
                core.generar_subtitulos_ass(
                    segmentos, clip["start"], clip["end"], ruta_ass)
                ruta_salida = os.path.join(self.carpeta_salida, nombre)

                rostros = None
                if seguir_rostros:
                    def progreso_rostros(p, i=i, total=total):
                        self._ui(
                            self._estado,
                            "Detectando rostros en el clip %d de %d… (%d%%)"
                            % (i, total, int(p * 100)), (i - 1) / total)
                    rostros = core.detectar_rostros(
                        ruta_video, clip["start"], clip["end"],
                        progreso=progreso_rostros)

                def progreso(p, i=i, total=total):
                    self._ui(self._estado,
                             "Exportando clip %d de %d…" % (i, total),
                             (i - 1 + p) / total)

                core.exportar_clip(ruta_video, clip["start"], clip["end"],
                                   ruta_ass, ruta_salida, progreso=progreso,
                                   rostros=rostros)
                if os.path.exists(ruta_ass):
                    os.remove(ruta_ass)
            self._ui(self._estado,
                     "Listo: %d clip(s) en %s" % (total, self.carpeta_salida),
                     1.0)
            self._ui(messagebox.showinfo, "ClipIA",
                     "%d clip(s) exportados en:\n%s"
                     % (total, self.carpeta_salida))
        except Exception as error:  # noqa: BLE001 - mostrar cualquier error
            detalle = "%s: %s" % (type(error).__name__, error)
            self._ui(self._estado, "Error: %s" % detalle, 0)
            self._ui(messagebox.showerror, "ClipIA", detalle)
        finally:
            self._ui(self._bloquear, False)


def main():
    app = AppClipIA()
    app.mainloop()


if __name__ == "__main__":
    main()
