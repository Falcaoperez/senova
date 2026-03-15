import re
from django.core.exceptions import ValidationError


class ValidadorContraseñaOchoCarActualMayusNumEspecial:
    """Validador de contraseñas:

    Reglas:
    - Exactamente 8 caracteres
    - Al menos una letra mayúscula
    - Al menos un dígito o un carácter especial
    """

    def validar(self, password, user=None):
        if password is None:
            raise ValidationError("La contraseña es obligatoria.")

        if len(password) != 8:
            raise ValidationError("La contraseña debe tener exactamente 8 caracteres.")

        # Debe contener al menos una letra mayúscula
        if not re.search(r"[A-Z]", password):
            raise ValidationError("Debe contener al menos una letra mayúscula.")

        # Debe contener mínimo un número o carácter especial
        has_digit = re.search(r"\d", password) is not None
        has_special = re.search(r"[^A-Za-z0-9]", password) is not None
        if not (has_digit or has_special):
            raise ValidationError("Debe contener mínimo un número o un carácter especial.")

    def obtener_texto_ayuda(self):
        return (
            "La contraseña debe tener exactamente 8 caracteres, "
            "al menos una mayúscula y mínimo un número o un carácter especial."
        )
