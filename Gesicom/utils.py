"""Utilidades y funciones auxiliares para la app Gesicom."""

import datetime
import calendar
from functools import wraps
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Count
from django.db.models.functions import TruncMonth


def is_admin_or_group(user, group_names):
    """Verifica si el usuario es superuser o pertenece a alguno de los grupos.
    
    Args:
        user: Usuario a verificar
        group_names: Lista o string con nombre(s) de grupo
    
    Returns:
        bool: True si cumple con el criterio
    """
    if user.is_superuser or user.groups.filter(name='administrador').exists():
        return True
    
    if isinstance(group_names, str):
        group_names = [group_names]
    
    return user.groups.filter(name__in=group_names).exists()


def require_group(*group_names):
    """Decorador que requiere que el usuario pertenezca a un grupo específico.
    
    Usage:
        @require_group('instructor')
        def my_view(request):
            pass
        
        @require_group('coordinador', 'dinamizador')
        def my_view(request):
            pass
    """
    def decorator(view_func):
        @login_required
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if is_admin_or_group(request.user, list(group_names)):
                return view_func(request, *args, **kwargs)
            return render(request, 'access_denied.html')
        return wrapper
    return decorator


def parse_month(s):
    """Convierte string 'YYYY-MM' a datetime.date del primer día del mes.
    
    Args:
        s: String en formato 'YYYY-MM'
    
    Returns:
        datetime.date o None si hay error
    """
    try:
        year, month = map(int, s.split('-'))
        return datetime.date(year, month, 1)
    except (ValueError, AttributeError, TypeError):
        return None


def get_end_date_of_month(date):
    """Devuelve el último día del mes de una fecha.
    
    Args:
        date: datetime.date
    
    Returns:
        datetime.date con el último día del mes, o None si date es None
    """
    if not date:
        return None
    last_day = calendar.monthrange(date.year, date.month)[1]
    return datetime.date(date.year, date.month, last_day)


def apply_date_filters(queryset, start_str, end_str, date_field='fecha_envio'):
    """Aplica filtros de fecha inicio/fin a un queryset.
    
    Args:
        queryset: Django QuerySet
        start_str: String 'YYYY-MM' para fecha inicio
        end_str: String 'YYYY-MM' para fecha fin
        date_field: Nombre del campo de fecha en el modelo (default: 'fecha_envio')
    
    Returns:
        QuerySet filtrado
    """
    start_date = parse_month(start_str) if start_str else None
    end_date = parse_month(end_str) if end_str else None
    
    if end_date:
        end_date = get_end_date_of_month(end_date)
    
    if start_date:
        queryset = queryset.filter(**{f'{date_field}__gte': start_date})
    if end_date:
        queryset = queryset.filter(**{f'{date_field}__lte': end_date})
    
    return queryset


def calculate_stats(queryset, value_field, count_field='id'):
    """Calcula estadísticas (totales y porcentajes) agrupadas por un campo.
    
    Args:
        queryset: Django QuerySet
        value_field: Campo por el cual agrupar (ej: 'tipo_evidencia')
        count_field: Campo a contar (default: 'id')
    
    Returns:
        Lista de dicts con: 'field_value', 'total', 'porcentaje'
    """
    total_count = queryset.count()
    
    stats_qs = (
        queryset.values(value_field)
        .annotate(total=Count(count_field))
        .order_by('-total', value_field)
    )
    
    stats = [
        {
            'field_value': item[value_field] or 'Sin especificar',
            'total': item['total'],
            'porcentaje': round((item['total'] / total_count) * 100, 2) if total_count else 0,
        }
        for item in stats_qs
    ]
    
    return stats, total_count


def calculate_monthly_stats(queryset, date_field='fecha_envio'):
    """Calcula estadísticas mensuales.
    
    Args:
        queryset: Django QuerySet
        date_field: Campo de fecha (default: 'fecha_envio')
    
    Returns:
        Tupla (stats_list, total_count)
    """
    total_count = queryset.count()
    
    monthly_qs = (
        queryset.annotate(month=TruncMonth(date_field))
        .values('month')
        .annotate(total=Count('id'))
        .order_by('month')
    )
    
    stats = [
        {
            'month': item['month'],
            'total': item['total'],
            'porcentaje': round((item['total'] / total_count) * 100, 2) if total_count else 0,
        }
        for item in monthly_qs
    ]
    
    return stats, total_count

def is_admin_or_group(user, group_names):
    """Devuelve True si el usuario es administrador o pertenece a un grupo.

    Args:
        user: Django User
        group_names: Lista de nombres de grupos

    Returns:
        True si el usuario es administrador o pertenece a uno de los grupos.
    """
    return user.is_superuser or user.groups.filter(name__in=group_names).exists()
