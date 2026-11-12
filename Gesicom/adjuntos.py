"""Formatos de adjuntos y vistas limitadas, sin ejecutar ni extraer su contenido."""

import codecs
import io
import struct
import warnings
import zipfile
from contextlib import contextmanager
from pathlib import Path

from django.core.exceptions import ValidationError
from PIL import Image, UnidentifiedImageError

MAX_ARCHIVO = 10 * 1024 * 1024
MAX_PIXELES = 25_000_000
MAX_TEXTO_VISTA = 64 * 1024
OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
OFFICE_XML = {".docx": "word/document.xml", ".xlsx": "xl/workbook.xml", ".pptx": "ppt/presentation.xml"}
FORMATOS = {
    ".pdf": ("PDF", "application/pdf"),
    ".doc": ("Word", "application/msword"),
    ".docx": ("Word", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    ".xls": ("Excel", "application/vnd.ms-excel"),
    ".xlsx": ("Excel", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    ".ppt": ("PowerPoint", "application/vnd.ms-powerpoint"),
    ".pptx": ("PowerPoint", "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
    ".txt": ("Texto", "text/plain"),
    ".jpg": ("JPEG", "image/jpeg"),
    ".jpeg": ("JPEG", "image/jpeg"),
    ".png": ("PNG", "image/png"),
    ".zip": ("ZIP", "application/zip"),
    ".rar": ("RAR", "application/vnd.rar"),
}
EXTENSIONES_EVIDENCIA = set(FORMATOS)


@contextmanager
def conservar_posicion(archivo):
    posicion = archivo.tell()
    try:
        yield
    finally:
        archivo.seek(posicion)


def codificacion_texto(muestra):
    for marca, codificacion in [
        (codecs.BOM_UTF32_LE, "utf-32"),
        (codecs.BOM_UTF32_BE, "utf-32"),
        (codecs.BOM_UTF16_LE, "utf-16"),
        (codecs.BOM_UTF16_BE, "utf-16"),
        (codecs.BOM_UTF8, "utf-8-sig"),
    ]:
        if muestra.startswith(marca):
            return codificacion
    try:
        codecs.getincrementaldecoder("utf-8")().decode(muestra, final=False)
        return "utf-8"
    except UnicodeDecodeError:
        return "cp1252"


def es_texto(muestra):
    try:
        texto = codecs.getincrementaldecoder(codificacion_texto(muestra))().decode(muestra, final=False)
    except UnicodeError:
        return False
    return not any((ord(c) < 32 and c not in "\t\r\n\f") or ord(c) == 127 for c in texto)


def _validar_office_xml(archivo, extension):
    archivo.seek(0, io.SEEK_END)
    size = archivo.tell()
    archivo.seek(max(0, size - 65557))
    fin = archivo.read(65557)
    offset = fin.rfind(b"PK\x05\x06")
    if offset < 0 or len(fin) - offset < 22:
        raise ValueError
    _, disco, inicio, entradas_disco, entradas, tamano_directorio, _, comentario = struct.unpack_from(
        "<4s4H2IH", fin, offset
    )
    if (
        disco
        or inicio
        or entradas_disco != entradas
        or entradas > 5000
        or tamano_directorio > 2 * 1024 * 1024
        or len(fin) - offset != 22 + comentario
    ):
        raise ValueError
    archivo.seek(0)
    with zipfile.ZipFile(archivo) as documento:
        elementos = documento.infolist()
        if len(elementos) > 5000 or any(p.flag_bits & 1 for p in elementos):
            raise ValueError
        nombres = {p.filename for p in elementos}
        if not {"[Content_Types].xml", OFFICE_XML[extension]}.issubset(nombres):
            raise ValueError


def validar_archivo_evidencia(archivo):
    if archivo.size > MAX_ARCHIVO:
        raise ValidationError("El archivo es demasiado grande. Tamaño máximo: 10 MB.")
    if not archivo.size:
        raise ValidationError("El archivo está vacío. Selecciona un documento con contenido.")
    extension = Path(archivo.name).suffix.lower()
    if extension not in FORMATOS:
        raise ValidationError("Tipo de archivo no permitido. Usa documentos, imágenes o comprimidos compatibles.")
    try:
        with conservar_posicion(archivo):
            archivo.seek(0)
            muestra = archivo.read(MAX_TEXTO_VISTA)
            if extension in {".jpg", ".jpeg", ".png"}:
                archivo.seek(0)
                with warnings.catch_warnings():
                    warnings.simplefilter("error", Image.DecompressionBombWarning)
                    with Image.open(archivo) as imagen:
                        esperado = "PNG" if extension == ".png" else "JPEG"
                        if imagen.format != esperado:
                            raise ValueError
                        if imagen.width * imagen.height > MAX_PIXELES:
                            raise ValidationError(
                                "La imagen supera los 25 millones de píxeles. Reduce su resolución antes de adjuntarla."
                            )
                        imagen.verify()
            elif extension == ".pdf":
                if not muestra.startswith(b"%PDF-"):
                    raise ValueError
            elif extension in {".doc", ".xls", ".ppt"}:
                if not muestra.startswith(OLE):
                    raise ValueError
            elif extension in OFFICE_XML:
                _validar_office_xml(archivo, extension)
            elif extension == ".zip":
                archivo.seek(0)
                if not zipfile.is_zipfile(archivo):
                    raise ValueError
            elif extension == ".rar":
                if not muestra.startswith((b"Rar!\x1a\x07\x00", b"Rar!\x1a\x07\x01\x00")):
                    raise ValueError
            elif extension == ".txt" and not es_texto(muestra):
                raise ValueError
    except (
        ValueError,
        OSError,
        SyntaxError,
        UnidentifiedImageError,
        zipfile.BadZipFile,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ):
        raise ValidationError(
            "El contenido no corresponde al formato del archivo o está dañado. Guarda una copia válida y vuelve a seleccionarla; los documentos de Office deben estar sin contraseña."
        ) from None


def vista_adjunto(archivo, nombre):
    """Los formatos históricos desconocidos se entregan como descarga."""
    extension = Path(nombre).suffix.lower()
    with conservar_posicion(archivo):
        archivo.seek(0)
        muestra = archivo.read(MAX_TEXTO_VISTA)
    mime = FORMATOS.get(extension, ("Archivo", "application/octet-stream"))[1]
    tipo = "other"
    if extension == ".pdf" and muestra.startswith(b"%PDF-"):
        tipo = "pdf"
    elif extension in {".jpg", ".jpeg"} and muestra.startswith(b"\xff\xd8\xff"):
        tipo = "image"
    elif extension == ".png" and muestra.startswith(b"\x89PNG\r\n\x1a\n"):
        tipo = "image"
    elif extension == ".gif" and muestra.startswith((b"GIF87a", b"GIF89a")):
        tipo, mime = "image", "image/gif"
    elif extension == ".txt" and es_texto(muestra):
        tipo, mime = "text", "text/plain; charset=" + codificacion_texto(muestra)
    elif extension in {".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".ods", ".odp"}:
        tipo = "office"
    elif extension == ".mp4" and muestra[4:8] == b"ftyp":
        tipo, mime = "video", "video/mp4"
    elif extension == ".webm" and muestra.startswith(b"\x1aE\xdf\xa3"):
        tipo, mime = "video", "video/webm"
    elif extension == ".ogg" and muestra.startswith(b"OggS"):
        tipo, mime = "video", "video/ogg"
    elif extension == ".wav" and muestra.startswith(b"RIFF") and muestra[8:12] == b"WAVE":
        tipo, mime = "audio", "audio/wav"
    elif extension == ".mp3" and (
        muestra.startswith(b"ID3") or muestra[:2] in {b"\xff\xfb", b"\xff\xfa", b"\xff\xf3", b"\xff\xf2"}
    ):
        tipo, mime = "audio", "audio/mpeg"
    if tipo == "other" and extension in {
        ".pdf",
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".txt",
        ".mp4",
        ".webm",
        ".ogg",
        ".wav",
        ".mp3",
    }:
        mime = "application/octet-stream"
    return tipo, mime


def texto_limitado(archivo):
    archivo.seek(0)
    data = archivo.read(MAX_TEXTO_VISTA + 1)
    truncado = len(data) > MAX_TEXTO_VISTA
    muestra = data[:MAX_TEXTO_VISTA]
    texto = codecs.getincrementaldecoder(codificacion_texto(muestra))(errors="replace").decode(
        muestra, final=not truncado
    )
    return texto, truncado
