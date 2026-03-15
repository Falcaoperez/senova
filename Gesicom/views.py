"""Vistas de la app 'Gesicom'.

Incluye:
- Páginas públicas (home, contacto, ayuda)
- Gestión y listas de envíos de evidencia
- Reportes y exportación CSV
- Control de acceso por grupos/roles
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator
from django.db.models import Q, Count
from django.contrib.auth import logout
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from .models import Envio
from .utils import (
    require_group, is_admin_or_group, apply_date_filters,
    calculate_stats, calculate_monthly_stats
)
from django.http import HttpResponse
import csv
import datetime
import json
from django.views.decorators.http import require_POST
from django.contrib import messages

@login_required
def editar_perfil(request):
    user = request.user

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        first_name = request.POST.get('nombre', '').strip()
        last_name = request.POST.get('apellido', '').strip()
        email = request.POST.get('correo', '').strip()
        password = request.POST.get('contrasena', '').strip()

        # Actualiza los datos del usuario
        user.username = username
        user.first_name = first_name
        user.last_name = last_name
        user.email = email

        if password:
            if len(password) >= 8:
                user.set_password(password)
                # Mantiene la sesión del usuario después de cambiar la contraseña
                update_session_auth_hash(request, user)
            else:
                messages.error(request, 'La contraseña debe tener al menos 8 caracteres.')
                return render(request, 'editar_perfil/editar.html', {'user': user})

        user.save()
        messages.success(request, 'Perfil actualizado correctamente.')
        # Redirige siempre al inicio después de guardar
        return redirect('home')

    return render(request, 'editar_perfil/editar.html', {'user': user})

def index(request):
    return render(request, 'home.html')


def home(request):
    is_basic = False
    if request.user.is_authenticated:
        is_basic = request.user.groups.filter(name='usuario').exists()
    return render(request, 'home.html', {'is_basic_user': is_basic})


@require_group('usuario')
def role_usuario(request):
    return render(request, 'home.html', {'is_basic_user': True})


def nosotros(request):
    return render(request, 'nosotros.html')


def contacto(request):
    return render(request, 'contacto.html')


def ayuda(request):
    return render(request, 'ayuda.html')


def logout_view(request):
    logout(request)
    return redirect('login')


@require_group('instructor')
def role_instructor(request):
    return render(request, 'panel_instructor.html')  # ← CAMBIO


@require_group('investigador')
def role_investigador(request):
    return render(request, 'roles/investigador.html')


@require_group('dinamizador')
def role_dinamizador(request):
    return render(request, 'roles/dinamizador.html')


@require_group('coordinador')
def role_coordinador(request):
    return render(request, 'roles/coordinador.html')


def portal(request):
    return redirect('home')


def admin_menu(request):
    return redirect('admin_personalizado:dashboard')

def proyecciones(request):
    consulta = Envio.objects.all()
    estadisticas_categoria, total_envios = calculate_stats(consulta, 'tipo_evidencia')
    estadisticas_proyecto, _ = calculate_stats(consulta, 'proyecto')
    estadisticas_categoria = [
        {'tipo_evidencia': s['field_value'], 'total': s['total'], 'porcentaje': s['porcentaje']}
        for s in estadisticas_categoria
    ]
    estadisticas_proyecto = [
        {'proyecto': s['field_value'], 'total': s['total'], 'porcentaje': s['porcentaje']}
        for s in estadisticas_proyecto
    ]
    context = {
        'total_envios': total_envios,
        'estadisticas_categoria': estadisticas_categoria,
        'estadisticas_proyecto': estadisticas_proyecto,
    }
    return render(request, 'admin/proyecciones.html', context)


def reportes(request):
    proyecto = request.GET.get('proyecto', '')
    inicio = request.GET.get('start', '')
    fin = request.GET.get('end', '')
    consulta = Envio.objects.all()
    if proyecto:
        consulta = consulta.filter(proyecto=proyecto)
    consulta = apply_date_filters(consulta, inicio, fin)
    estadisticas_categoria, total_envios = calculate_stats(consulta, 'tipo_evidencia')
    estadisticas_categoria = [
        {'tipo_evidencia': s['field_value'], 'total': s['total'], 'porcentaje': s['porcentaje']}
        for s in estadisticas_categoria
    ]
    estadisticas_mensuales, _ = calculate_monthly_stats(consulta)
    opcion_proyectos = [p for p, _ in Envio.PROYECTO_CHOICES]
    context = {
        'proyecto': proyecto,
        'start': inicio,
        'end': fin,
        'opciones_proyectos': opcion_proyectos,
        'estadisticas_categoria': estadisticas_categoria,
        'estadisticas_mensuales': estadisticas_mensuales,
    }
    return render(request, 'admin/reportes.html', context)


def reportes_csv(request):
    proyecto = request.GET.get('proyecto', '')
    inicio = request.GET.get('start', '')
    fin = request.GET.get('end', '')
    consulta = Envio.objects.all()
    if proyecto:
        consulta = consulta.filter(proyecto=proyecto)
    consulta = apply_date_filters(consulta, inicio, fin)
    respuesta = HttpResponse(content_type='text/csv')
    respuesta['Content-Disposition'] = 'attachment; filename="reportes.csv"'
    escritor = csv.writer(respuesta)
    escritor.writerow(['fecha_envio', 'nombre', 'proyecto', 'tipo_evidencia', 'link_evidencia', 'observaciones'])
    for envio in consulta.order_by('fecha_envio'):
        escritor.writerow([
            envio.fecha_envio.isoformat() if envio.fecha_envio else '',
            envio.nombre,
            envio.proyecto,
            envio.tipo_evidencia,
            envio.link_evidencia or '',
            (envio.observaciones or '').replace('\r\n', ' ').replace('\n', ' '),
        ])
    return respuesta


def reportes_trimestrales_csv(request):
    proyecto = request.GET.get('proyecto', '')
    inicio = request.GET.get('start', '')
    fin = request.GET.get('end', '')
    try:
        num_quarters = int(request.GET.get('quarters', 4))
    except Exception:
        num_quarters = 4
    num_quarters = max(1, min(24, num_quarters))
    consulta = Envio.objects.all()
    if proyecto:
        consulta = consulta.filter(proyecto=proyecto)
    consulta = apply_date_filters(consulta, inicio, fin)
    hoy = datetime.date.today()
    current_year = hoy.year
    current_quarter = (hoy.month - 1) // 3 + 1
    q_list = []
    y = current_year
    q = current_quarter
    for _ in range(num_quarters):
        q_list.insert(0, (y, q))
        q -= 1
        if q == 0:
            q = 4
            y -= 1
    respuesta = HttpResponse(content_type='text/csv')
    respuesta['Content-Disposition'] = 'attachment; filename="reportes_trimestrales.csv"'
    escritor = csv.writer(respuesta)
    escritor.writerow(['Trimestre', 'Nuevas', 'Aprobadas'])
    for (y, q) in q_list:
        start_month = (q - 1) * 3 + 1
        start_date = datetime.date(y, start_month, 1)
        end_month = start_month + 2
        if end_month == 12:
            end_day = 31
        else:
            next_month = end_month + 1
            end_day = (datetime.date(y, next_month, 1) - datetime.timedelta(days=1)).day
        end_date = datetime.date(y, end_month, end_day)
        nuevas = consulta.filter(fecha_envio__gte=start_date, fecha_envio__lte=end_date).count()
        aprob = consulta.filter(fecha_envio__gte=start_date, fecha_envio__lte=end_date, aprobada=True).count()
        escritor.writerow([f'Q{q} {y}', nuevas, aprob])
    return respuesta


def _home_url_for_user(user):
    """Devuelve la URL del panel de inicio correspondiente al rol del usuario."""
    if user.is_superuser:
        return reverse('admin_personalizado:dashboard')
    if user.groups.filter(name='instructor').exists():
        return reverse('role_instructor')
    if user.groups.filter(name='investigador').exists():
        return reverse('role_investigador')
    if user.groups.filter(name='dinamizador').exists():
        return reverse('role_dinamizador')
    if user.groups.filter(name='coordinador').exists():
        return reverse('role_coordinador')
    if user.groups.filter(name='usuario').exists():
        # En urls.py el nombre de esta ruta es 'usuario'
        return reverse('usuario')
    return reverse('home')


@login_required
def evidencia(request):
    home_url = _home_url_for_user(request.user)

    if request.method == 'POST':
        nombre = request.POST.get('nombre', '').strip()
        proyecto = request.POST.get('proyecto', '').strip()
        tipos = request.POST.getlist('evidencias')
        tipo_evidencia = ', '.join(tipos) if tipos else 'Sin especificar'
        enlace = request.POST.get('linkArchivo', '').strip()
        archivo = request.FILES.get('archivo')
        observaciones = request.POST.get('observaciones', '').strip()
        errores = []
        if not (enlace or archivo):
            errores.append('Debe proporcionar un enlace o adjuntar un archivo (al menos uno).')
        if not nombre:
            errores.append('El nombre es obligatorio.')
        if not proyecto:
            errores.append('Debe seleccionar el proyecto.')
        if archivo and archivo.size > 10 * 1024 * 1024:
            errores.append('El archivo es demasiado grande. Tamaño máximo: 10MB.')
        if archivo:
            extensiones_permitidas = ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
                                     '.txt', '.jpg', '.jpeg', '.png', '.zip', '.rar']
            nombre_archivo = archivo.name.lower()
            if not any(nombre_archivo.endswith(ext) for ext in extensiones_permitidas):
                errores.append(f'Tipo de archivo no permitido. Extensiones permitidas: {", ".join(extensiones_permitidas)}')
        if errores:
            return render(request, 'formulario.html', {
                'errores': errores,
                'exito': False,
                'nombre': nombre,
                'proyecto': proyecto,
                'tipos': tipos,
                'enlace_archivo': enlace,
                'observaciones': observaciones,
                'home_url': home_url,
            })
        envio = Envio(
            usuario=request.user,
            nombre=nombre,
            proyecto=proyecto,
            tipo_evidencia=tipo_evidencia,
            link_evidencia=enlace if enlace else None,
            archivo_evidencia=archivo,
            observaciones=observaciones,
        )
        envio.save()
        mensaje_exito = 'Evidencia enviada correctamente'
        if archivo:
            mensaje_exito += f'. Archivo guardado: {envio.archivo_evidencia.name}'
        return render(request, 'formulario.html', {
            'exito': True,
            'mensaje_exito': mensaje_exito,
            'home_url': home_url,
        })
    return render(request, 'formulario.html', {'home_url': home_url})


@login_required
def evidencias_list(request):
    home_url = _home_url_for_user(request.user)
    consulta = Envio.objects.select_related('usuario').all()
    proyecto = request.GET.get('proyecto', '')
    inicio = request.GET.get('start', '')
    fin = request.GET.get('end', '')
    if proyecto:
        consulta = consulta.filter(proyecto=proyecto)
    consulta = apply_date_filters(consulta, inicio, fin)
    termino_busqueda = (request.GET.get('q') or '').strip()
    if termino_busqueda:
        consulta = consulta.filter(
            Q(nombre__icontains=termino_busqueda) |
            Q(tipo_evidencia__icontains=termino_busqueda) |
            Q(observaciones__icontains=termino_busqueda)
        )
    orden = request.GET.get('order', 'fecha_envio')
    direccion = request.GET.get('dir', 'desc')
    permitidos = {'fecha_envio', 'nombre', 'proyecto', 'tipo_evidencia'}
    if orden in permitidos:
        criterio_orden = orden if direccion == 'asc' else f'-{orden}'
        consulta = consulta.order_by(criterio_orden)
    else:
        consulta = consulta.order_by('-fecha_envio')
    paginador = Paginator(consulta, 10)
    numero_pagina = request.GET.get('page')
    objeto_pagina = paginador.get_page(numero_pagina)
    total_envios = consulta.count()
    hoy = datetime.date.today()
    hace_30 = hoy - datetime.timedelta(days=30)
    hace_60 = hoy - datetime.timedelta(days=60)
    nuevas_30d = consulta.filter(fecha_envio__gte=hace_30).count()
    nuevas_prev_30d = consulta.filter(fecha_envio__gte=hace_60, fecha_envio__lt=hace_30).count()
    aprobadas = consulta.filter(aprobada=True).count()
    rechazadas = consulta.filter(rechazada=True).count()
    aprobadas_30d = consulta.filter(aprobada=True, fecha_envio__gte=hace_30).count()
    aprobadas_prev_30d = consulta.filter(aprobada=True, fecha_envio__gte=hace_60, fecha_envio__lt=hace_30).count()

    def pct_change(current, previous):
        try:
            if previous == 0:
                return None if current == 0 else 100.0
            return round(((current - previous) / previous) * 100, 1)
        except Exception:
            return None

    pct_nuevas = pct_change(nuevas_30d, nuevas_prev_30d)
    pct_aprobadas = pct_change(aprobadas_30d, aprobadas_prev_30d)
    pct_total = pct_change(nuevas_30d, nuevas_prev_30d)
    pct_nuevas_abs = abs(pct_nuevas) if pct_nuevas is not None else None
    pct_aprobadas_abs = abs(pct_aprobadas) if pct_aprobadas is not None else None
    pct_total_abs = abs(pct_total) if pct_total is not None else None
    proyectos_guardados = list(Envio.objects.values_list('proyecto', flat=True).distinct())
    choice_map = {c[0]: c[1] for c in Envio.PROYECTO_CHOICES}
    categorias_labels = []
    categorias_data = []
    for code, label in Envio.PROYECTO_CHOICES:
        if code and code in proyectos_guardados:
            categorias_labels.append(label)
            categorias_data.append(consulta.filter(proyecto=code).count())
    try:
        num_quarters = int(request.GET.get('quarters', 4))
    except Exception:
        num_quarters = 4
    num_quarters = max(1, min(12, num_quarters))
    trimestres_labels = []
    datos_trimestrales_nuevas = []
    datos_trimestrales_aprobadas = []
    current_year = hoy.year
    current_quarter = (hoy.month - 1) // 3 + 1
    q_list = []
    y = current_year
    q = current_quarter
    for _ in range(num_quarters):
        q_list.insert(0, (y, q))
        q -= 1
        if q == 0:
            q = 4
            y -= 1
    for (y, q) in q_list:
        start_month = (q - 1) * 3 + 1
        start_date = datetime.date(y, start_month, 1)
        end_month = start_month + 2
        if end_month == 12:
            end_day = 31
        else:
            next_month = end_month + 1
            end_day = (datetime.date(y, next_month, 1) - datetime.timedelta(days=1)).day
        end_date = datetime.date(y, end_month, end_day)
        trimestres_labels.append(f"Q{q} {y}")
        datos_trimestrales_nuevas.append(consulta.filter(fecha_envio__gte=start_date, fecha_envio__lte=end_date).count())
        datos_trimestrales_aprobadas.append(consulta.filter(fecha_envio__gte=start_date, fecha_envio__lte=end_date, aprobada=True).count())
    top_users_qs = consulta.values('usuario__first_name', 'usuario__last_name', 'usuario__username').annotate(total=Count('id')).order_by('-total')[:6]
    usuarios_labels = []
    usuarios_data = []
    for u in top_users_qs:
        name = u.get('usuario__first_name') or u.get('usuario__username') or 'Usuario'
        if u.get('usuario__last_name'):
            name = f"{name} {u.get('usuario__last_name')}"
        usuarios_labels.append(name)
        usuarios_data.append(u['total'])
    proyectos_guardados = list(Envio.objects.values_list('proyecto', flat=True).distinct())
    opciones_proyectos = [(p, choice_map.get(p, p)) for p in proyectos_guardados if p]
    context = {
        'envios': objeto_pagina,
        'proyecto': proyecto,
        'order': orden,
        'dir': direccion,
        'start': inicio,
        'end': fin,
        'opciones_proyectos': opciones_proyectos,
        'total_envios': total_envios,
        'nuevas_30d': nuevas_30d,
        'aprobadas': aprobadas,
        'rechazadas': rechazadas,
        'categorias_labels_json': json.dumps(categorias_labels, ensure_ascii=False),
        'categorias_data_json': json.dumps(categorias_data),
        'trimestres_labels_json': json.dumps(trimestres_labels, ensure_ascii=False),
        'datos_trimestrales_nuevas_json': json.dumps(datos_trimestrales_nuevas),
        'datos_trimestrales_aprobadas_json': json.dumps(datos_trimestrales_aprobadas),
        'usuarios_labels_json': json.dumps(usuarios_labels, ensure_ascii=False),
        'usuarios_data_json': json.dumps(usuarios_data),
        'pct_nuevas': pct_nuevas,
        'pct_aprobadas': pct_aprobadas,
        'pct_total': pct_total,
        'pct_nuevas_abs': pct_nuevas_abs,
        'pct_aprobadas_abs': pct_aprobadas_abs,
        'pct_total_abs': pct_total_abs,
        'aprobadas_30d': aprobadas_30d,
        'home_url': home_url,
    }
    return render(request, 'evidencias_list.html', context)


def instructor_table(request):
    return render(request, 'instructor_table.html')


@login_required
def ver_evidencia(request, pk):
    envio = get_object_or_404(Envio, pk=pk)
    archivo_url = None
    if envio.archivo_evidencia:
        archivo_url = request.build_absolute_uri(envio.archivo_evidencia.url)
    return render(request, 'ver_evidencia.html', {'envio': envio, 'archivo_url': archivo_url})


@login_required
def editar_perfil(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        nombre = request.POST.get('nombre')
        apellido = request.POST.get('apellido')
        correo = request.POST.get('correo')
        contrasena = request.POST.get('contrasena')

        user = request.user
        
        # Verificar si el nuevo username ya existe (y no es el del usuario actual)
        from django.contrib.auth.models import User
        if username != user.username and User.objects.filter(username=username).exists():
            messages.error(request, 'El nombre de usuario ya está en uso.')
            return redirect('editar_perfil')

        user.username = username
        user.first_name = nombre
        user.last_name = apellido
        user.email = correo
        
        if contrasena and len(contrasena) == 8:
            user.set_password(contrasena)
            user.save()
            from django.contrib.auth import update_session_auth_hash
            update_session_auth_hash(request, user)
        else:
            user.save()
            
        messages.success(request, 'Perfil actualizado correctamente.')
        return redirect('editar_perfil')

    return render(request, 'editar_perfil/editar.html')


@require_POST
def set_aprobada(request, pk):
    envio = get_object_or_404(Envio, pk=pk)
    valor = request.POST.get('valor')
    if valor == '1':
        envio.aprobada = True
        envio.rechazada = False
    else:
        envio.aprobada = False
        envio.rechazada = True
    envio.save()
    messages.success(request, 'Estado de evidencia actualizado.')
    next_url = request.POST.get('next') or request.META.get('HTTP_REFERER') or '/evidencias/'
    return redirect(next_url)


def access_denied(request):
    return render(request, 'access_denied.html')


def exportar_csv(request):
    consulta = Envio.objects.select_related('usuario').all().order_by('-fecha_envio')
    respuesta = HttpResponse(content_type='text/csv')
    respuesta['Content-Disposition'] = 'attachment; filename="envios.csv"'
    escritor = csv.writer(respuesta)
    escritor.writerow(['fecha_envio', 'nombre', 'proyecto', 'tipo_evidencia', 'link_evidencia', 'observaciones'])
    for envio in consulta:
        escritor.writerow([
            envio.fecha_envio.isoformat() if envio.fecha_envio else '',
            envio.nombre,
            envio.proyecto,
            envio.tipo_evidencia,
            envio.link_evidencia or '',
            (envio.observaciones or '').replace('\r\n', ' ').replace('\n', ' '),
        ])
    return respuesta