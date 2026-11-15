"""Tests del instalador (Fase 4): spec de PyInstaller, script Inno
Setup, workflow de build, flag --version, PATH del instalador y
modelo YuNet empaquetado.

El build real de Windows NO se puede probar en este servidor (Linux):
estos tests validan todo lo validable aquí (sintaxis, estructura y
rutas referenciadas). El build de GitHub Actions es la prueba real.
"""
import hashlib
import os
import subprocess
import sys
from unittest import mock

import yaml

import main as app_mod
from clipia import __version__, rostros

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _leer(relativa: str) -> str:
    with open(os.path.join(RAIZ, relativa), encoding="utf-8") as archivo:
        return archivo.read()


# --- Spec de PyInstaller ---------------------------------------------------

def test_spec_es_python_valido_y_one_folder():
    fuente = _leer("clipia.spec")
    compile(fuente, "clipia.spec", "exec")  # sintaxis
    assert "exclude_binaries=True" in fuente  # one-folder
    assert "COLLECT" in fuente
    assert "console=False" in fuente  # app de ventana
    assert 'name="ClipIA"' in fuente
    assert 'collect_submodules("yt_dlp")' in fuente
    assert 'collect_data_files("tkinterdnd2")' in fuente
    assert 'collect_data_files("certifi")' in fuente
    assert "upx=False" in fuente


# --- Script Inno Setup -----------------------------------------------------

def test_iss_tiene_secciones_y_version():
    contenido = _leer("instalador/clipia.iss")
    for seccion in ("[Setup]", "[Files]", "[Icons]", "[Run]",
                    "[Languages]"):
        assert seccion in contenido
    assert '#define AppVersion "2.0.0"' in contenido
    assert "OutputBaseFilename=ClipIA-Setup-{#AppVersion}" in contenido
    assert 'Source: "..\\dist\\ClipIA\\*"' in contenido
    assert "PrivilegesRequired=lowest" in contenido
    assert "ArchitecturesAllowed=x64" in contenido
    assert "Spanish.isl" in contenido
    assert "{localappdata}\\Programs\\ClipIA" in contenido


def test_iss_tiene_finales_de_linea_crlf():
    with open(os.path.join(RAIZ, "instalador", "clipia.iss"),
              "rb") as archivo:
        datos = archivo.read()
    assert b"\r\n" in datos
    assert datos.replace(b"\r\n", b"").count(b"\n") == 0


# --- Workflow de build -----------------------------------------------------

def test_build_yml_valido_y_referencia_archivos():
    flujo = yaml.safe_load(_leer(".github/workflows/build.yml"))
    # PyYAML (YAML 1.1) lee la clave `on` como el booleano True.
    disparadores = flujo[True]
    assert "v*" in disparadores["push"]["tags"]
    assert "workflow_dispatch" in disparadores
    job = flujo["jobs"]["build-windows"]
    assert job["runs-on"] == "windows-latest"
    pasos = " ".join(str(p.get("run", "")) for p in job["steps"])
    assert "pyinstaller==6.22.3" in pasos
    assert "pyinstaller clipia.spec" in pasos
    assert "ffmpeg-release-essentials.zip" in pasos
    assert "face_detection_yunet_2023mar.onnx" in pasos
    assert rostros.SHA256_MODELO_YUNET in pasos
    assert rostros.URL_MODELO_YUNET in pasos
    assert "ISCC.exe" in pasos
    assert "ClipIA.exe --version" in pasos
    assert "upload-artifact" in str(job["steps"])
    # Los archivos referenciados existen en el repo.
    for relativa in ("clipia.spec", "instalador/clipia.iss",
                     "requirements.txt", "main.py"):
        assert os.path.isfile(os.path.join(RAIZ, relativa)), relativa


# --- .gitignore ------------------------------------------------------------

def test_gitignore_no_ignora_el_spec_pero_si_las_salidas():
    contenido = _leer(".gitignore")
    assert "*.spec" not in contenido  # el spec es código fuente
    assert "dist/" in contenido
    assert "build/" in contenido
    assert "instalador/Output/" in contenido


# --- Versión coherente -----------------------------------------------------

def test_version_coherente_en_paquete_iss_y_workflow():
    assert __version__ == "2.0.0"
    assert '"2.0.0"' in _leer("instalador/clipia.iss")
    assert "ClipIA-Setup-2.0.0" in _leer(".github/workflows/build.yml")


def test_flag_version_imprime_y_sale_sin_ventana():
    """`python main.py --version` imprime la versión y sale sin
    abrir ventana (lo usa la prueba de humo del build)."""
    resultado = subprocess.run(
        [sys.executable, os.path.join(RAIZ, "main.py"), "--version"],
        capture_output=True, text=True, timeout=120)
    assert resultado.returncode == 0
    assert resultado.stdout.strip() == "ClipIA 2.0.0"


# --- PATH del instalador ---------------------------------------------------

def test_preparar_ruta_ejecutable_anade_la_carpeta_en_frozen(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", "/tmp/app/ClipIA.exe")
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    app_mod._preparar_ruta_ejecutable()
    assert os.environ["PATH"].startswith("/tmp/app" + os.pathsep)


def test_preparar_ruta_ejecutable_no_duplica_ni_toca_sin_frozen(
        monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    app_mod._preparar_ruta_ejecutable()
    assert os.environ["PATH"] == "/usr/bin:/bin"


# --- Modelo YuNet empaquetado ----------------------------------------------

def test_modelo_yunet_empaquetado_se_usa_sin_descargar(
        tmp_path, monkeypatch):
    """Con el modelo junto al .exe (y SHA correcto), no se descarga
    nada: ni siquiera se toca la red."""
    contenido = b"modelo yunet falso"
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    modelo = app_dir / rostros.NOMBRE_MODELO_YUNET
    modelo.write_bytes(contenido)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(app_dir / "ClipIA.exe"))
    monkeypatch.setattr(rostros, "SHA256_MODELO_YUNET",
                        hashlib.sha256(contenido).hexdigest())
    with mock.patch("urllib.request.urlopen",
                    side_effect=AssertionError("no debe usar la red")):
        assert rostros.descargar_modelo_yunet() == str(modelo)


def test_modelo_yunet_empaquetado_sin_frozen_es_none(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert rostros.ruta_modelo_yunet_empaquetado() is None
