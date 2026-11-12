import re
from pathlib import Path

from django.core.exceptions import ValidationError

EXTENSIONES_EVIDENCIA = {
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
    ".txt",
    ".jpg",
    ".jpeg",
    ".png",
    ".zip",
    ".rar",
}


def validar_archivo_evidencia(archivo):
    if archivo.size > 10 * 1024 * 1024:
        raise ValidationError("El archivo es demasiado grande. Tamaño máximo: 10 MB.")
    if Path(archivo.name).suffix.lower() not in EXTENSIONES_EVIDENCIA:
        raise ValidationError("Tipo de archivo no permitido. Usa documentos, imágenes o comprimidos compatibles.")


class ValidadorContraseñaOchoCarActualMayusNumEspecial:
    """Validador de contraseñas:

    Reglas:
    - Longitud mínima de 8 caracteres
    - Al menos un dígito o un carácter especial
    """

    def validar(self, password, user=None):
        if password is None:
            raise ValidationError("La contraseña es obligatoria.")

        if len(password) < 8:
            raise ValidationError("La contraseña debe tener al menos 8 caracteres.")

        # Debe contener mínimo un número o carácter especial
        has_digit = re.search(r"\d", password) is not None
        has_special = re.search(r"[^A-Za-z0-9]", password) is not None
        if not (has_digit or has_special):
            raise ValidationError("Debes ingresar por lo mínimo un carácter especial o un número.")

    def obtener_texto_ayuda(self):
        return "La contraseña debe tener al menos 8 caracteres y al menos un número o un carácter especial."

    validate = validar
    get_help_text = obtener_texto_ayuda
