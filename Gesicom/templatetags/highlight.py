from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe
import re

register = template.Library()


@register.filter
def highlight(value, query):
    """Envuelve las coincidencias de 'query' en 'value' con <mark>.

    Búsqueda case-insensitive; escapa el texto original y marca el resultado
    como seguro para poder renderizar el HTML de marcado.
    """
    if not value or not query:
        return value
    try:
        pattern = re.compile(re.escape(str(query)), re.IGNORECASE)
        escaped = escape(str(value))
        result = pattern.sub(lambda m: f"<mark>{m.group(0)}</mark>", escaped)
        return mark_safe(result)
    except Exception:
        return value
