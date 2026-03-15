from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """Obtiene un item de un diccionario 1"""
    if isinstance(dictionary, dict):
        return dictionary.get(key, 0)
    return 0
