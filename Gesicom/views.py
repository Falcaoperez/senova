"""Vistas de la app 'Gesicom'.

Incluye:
- Páginas públicas (home, contacto, ayuda)
- Gestión y listas de envíos de evidencia
- Reportes y exportación CSV
- Control de acceso por grupos/roles
"""

import csv
import datetime

from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_POST

from .models import Envio
from .selectors import _evidencias_context, _filtered_envios, _home_url_for_user, _panel_context, _visible_envios
from .utils import (
    calculate_stats,
    require_group,
    safe_csv_cell,
)


def home(request):
    is_basic = False
    if request.user.is_authenticated:
        is_basic = request.user.groups.filter(name="usuario").exists()
    return render(request, "home.html", {"is_basic_user": is_basic})


@require_group("usuario")
def role_usuario(request):
    return render(request, "panel_usuario.html", _panel_context(request.user, "Usuario"))


def nosotros(request):
    return render(request, "nosotros.html")


def contacto(request):
    return render(request, "contacto.html")


def ayuda(request):
    return render(request, "ayuda.html")


@require_group("instructor")
def role_instructor(request):
    return render(request, "panel_instructor.html", _panel_context(request.user, "Instructor"))


@require_group("investigador")
def role_investigador(request):
    return render(request, "panel_instructor.html", _panel_context(request.user, "Investigador"))


@require_group("dinamizador")
def role_dinamizador(request):
    return render(request, "panel_instructor.html", _panel_context(request.user, "Dinamizador"))


@require_group("coordinador")
def role_coordinador(request):
    return render(request, "panel_instructor.html", _panel_context(request.user, "Coordinador"))


def portal(request):
    return redirect("home")


def admin_menu(request):
    return redirect("admin_personalizado:dashboard")


@login_required
def proyecciones(request):
    consulta = _visible_envios(request.user)
    estadisticas_categoria, total_envios = calculate_stats(consulta, "tipo_evidencia")
    estadisticas_proyecto, _ = calculate_stats(consulta, "proyecto")
    estadisticas_categoria = [
        {"tipo_evidencia": s["field_value"], "total": s["total"], "porcentaje": s["porcentaje"]}
        for s in estadisticas_categoria
    ]
    estadisticas_proyecto = [
        {"proyecto": s["field_value"], "total": s["total"], "porcentaje": s["porcentaje"]}
        for s in estadisticas_proyecto
    ]
    context = {
        "total_envios": total_envios,
        "estadisticas_categoria": estadisticas_categoria,
        "estadisticas_proyecto": estadisticas_proyecto,
    }
    return render(request, "admin/proyecciones.html", context)


@login_required
def reportes(request):
    context = _evidencias_context(request, incluir_graficos=True)
    context["download_query"] = "?" + request.GET.urlencode() if request.GET else ""
    context["opciones_proyectos"] = [code for code, label in Envio.PROYECTO_CHOICES]
    return render(request, "reportes.html", context)


@login_required
def reportes_csv(request):
    consulta = _filtered_envios(request)
    respuesta = HttpResponse(content_type="text/csv")
    respuesta["Content-Disposition"] = 'attachment; filename="reportes.csv"'
    escritor = csv.writer(respuesta)
    escritor.writerow(["fecha_envio", "nombre", "proyecto", "tipo_evidencia", "link_evidencia", "observaciones"])
    for envio in consulta.order_by("fecha_envio"):
        escritor.writerow(
            [
                safe_csv_cell(value)
                for value in [
                    envio.fecha_envio.isoformat() if envio.fecha_envio else "",
                    envio.nombre,
                    envio.proyecto,
                    envio.tipo_evidencia,
                    envio.link_evidencia or "",
                    (envio.observaciones or "").replace("\r\n", " ").replace("\n", " "),
                ]
            ]
        )
    return respuesta


@login_required
def reportes_trimestrales_csv(request):
    try:
        num_quarters = int(request.GET.get("quarters", 4))
    except Exception:
        num_quarters = 4
    num_quarters = max(1, min(24, num_quarters))
    consulta = _filtered_envios(request)
    hoy = timezone.localdate()
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
    respuesta = HttpResponse(content_type="text/csv")
    respuesta["Content-Disposition"] = 'attachment; filename="reportes_trimestrales.csv"'
    escritor = csv.writer(respuesta)
    escritor.writerow(["Trimestre", "Nuevas", "Aprobadas"])
    for y, q in q_list:
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
        escritor.writerow([f"Q{q} {y}", nuevas, aprob])
    return respuesta


@login_required
def evidencia(request):
    home_url = _home_url_for_user(request.user)
    from notificaciones.services import plazos_para_usuario

    plazos = plazos_para_usuario(request.user)
    extra = {
        "home_url": home_url,
        "plazos_evidencia": plazos,
        "plazo_seleccionado": request.POST.get("plazo", request.GET.get("plazo", "")),
    }

    if request.method == "POST":
        nombre = request.POST.get("nombre", "").strip()
        proyecto = request.POST.get("proyecto", "").strip()
        tipos = request.POST.getlist("evidencias")
        tipo_evidencia = ", ".join(tipos) if tipos else "Sin especificar"
        enlace = (request.POST.get("linkArchivo") or request.POST.get("link_evidencia", "")).strip()
        archivo = request.FILES.get("archivo")
        observaciones = request.POST.get("observaciones", "").strip()
        errores = []
        plazo = None
        plazo_id = request.POST.get("plazo", "")
        if plazo_id:
            plazo = (
                plazos.filter(pk=int(plazo_id)).first()
                if plazo_id.isascii() and plazo_id.isdigit() and len(plazo_id) <= 18
                else None
            )
            if not plazo:
                errores.append("Selecciona un plazo disponible para tu cuenta.")
            elif plazo.proyecto and plazo.proyecto != proyecto:
                errores.append("El proyecto debe coincidir con el plazo seleccionado.")
        if not (enlace or archivo):
            errores.append("Debe proporcionar un enlace o adjuntar un archivo (al menos uno).")
        if not nombre:
            errores.append("El nombre es obligatorio.")
        if proyecto not in dict(Envio.PROYECTO_CHOICES):
            errores.append("Debe seleccionar un proyecto válido.")
        if enlace:
            from django.core.exceptions import ValidationError
            from django.core.validators import URLValidator

            try:
                URLValidator(schemes=["http", "https"])(enlace)
            except ValidationError:
                errores.append("Ingresa un enlace válido que empiece por http:// o https://.")
        if archivo and archivo.size > 10 * 1024 * 1024:
            errores.append("El archivo es demasiado grande. Tamaño máximo: 10MB.")
        if archivo:
            extensiones_permitidas = [
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
            ]
            nombre_archivo = archivo.name.lower()
            if not any(nombre_archivo.endswith(ext) for ext in extensiones_permitidas):
                errores.append(
                    f"Tipo de archivo no permitido. Extensiones permitidas: {', '.join(extensiones_permitidas)}"
                )
        if errores:
            return render(
                request,
                "formulario.html",
                {
                    "errores": errores,
                    "exito": False,
                    "nombre": nombre,
                    "proyecto": proyecto,
                    "tipos": tipos,
                    "enlace_archivo": enlace,
                    "observaciones": observaciones,
                    **extra,
                },
            )
        envio = Envio(
            usuario=request.user,
            plazo=plazo,
            limite_aplicado=plazo.fecha_limite if plazo else None,
            nombre=nombre,
            proyecto=proyecto,
            tipo_evidencia=tipo_evidencia,
            link_evidencia=enlace if enlace else None,
            archivo_evidencia=archivo,
            observaciones=observaciones,
        )
        envio.save()
        mensaje_exito = "Evidencia enviada correctamente"
        if archivo:
            mensaje_exito += f". Archivo guardado: {envio.archivo_evidencia.name}"
        return render(
            request,
            "formulario.html",
            {
                "exito": True,
                "mensaje_exito": mensaje_exito,
                **extra,
            },
        )
    return render(request, "formulario.html", extra)


@login_required
def evidencias_list(request):
    return render(request, "evidencias_list.html", _evidencias_context(request))


def tabla_instructor(request):
    return redirect("evidencias_list")


@login_required
def ver_evidencia(request, pk):
    envio = get_object_or_404(_visible_envios(request.user), pk=pk)
    archivo_url = None
    if envio.archivo_evidencia:
        archivo_url = reverse("archivo_evidencia", args=[envio.pk])
    from pathlib import Path

    suffix = Path(envio.archivo_evidencia.name or "").suffix.lower()
    kind = (
        "image"
        if suffix in {".jpg", ".jpeg", ".png", ".gif"}
        else "pdf"
        if suffix == ".pdf"
        else "text"
        if suffix == ".txt"
        else "office"
        if suffix in {".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".ods", ".odp"}
        else "video"
        if suffix in {".mp4", ".webm", ".ogg"}
        else "audio"
        if suffix in {".mp3", ".wav"}
        else "other"
    )
    return render(request, "ver_evidencia.html", {"envio": envio, "archivo_url": archivo_url, "preview_kind": kind})


@login_required
@sensitive_post_parameters()
def editar_perfil(request):
    from .forms import ProfileForm

    form = ProfileForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        from django.db import IntegrityError, transaction

        try:
            with transaction.atomic():
                user = form.save()
                if form.cambio_sensible:
                    from cuentas.correos import encolar_aviso_cambio, invalidar_recuperaciones

                    invalidar_recuperaciones(user)
                    encolar_aviso_cambio(user, form.correo_anterior)
        except IntegrityError:
            form.add_error("correo", "Ese correo o nombre de usuario ya está registrado.")
        else:
            if form.cleaned_data["contrasena"]:
                update_session_auth_hash(request, user)
                from cuentas.sesiones import cerrar_sesiones

                cerrar_sesiones(user, conservar=request.session.session_key)
            messages.success(request, "Perfil actualizado correctamente.")
            return redirect("editar_perfil")
    return render(request, "editar_perfil/editar.html", {"form": form})


@require_group("administrador", "coordinador", "dinamizador")
@require_POST
def set_aprobada(request, pk):
    from notificaciones.services import notificar_revision

    envio = get_object_or_404(_visible_envios(request.user), pk=pk)
    estado_anterior = (envio.aprobada, envio.rechazada)
    valor = request.POST.get("valor")
    if valor not in {"0", "1"}:
        return JsonResponse({"error": "Estado inválido"}, status=400)
    if valor == "1":
        envio.aprobada = True
        envio.rechazada = False
    else:
        envio.aprobada = False
        envio.rechazada = True
    envio.save()
    if estado_anterior != (envio.aprobada, envio.rechazada):
        notificar_revision(envio)
    messages.success(request, "Estado de evidencia actualizado.")
    next_url = request.POST.get("next") or request.META.get("HTTP_REFERER") or "/evidencias/"
    from django.utils.http import url_has_allowed_host_and_scheme

    if not url_has_allowed_host_and_scheme(next_url, {request.get_host()}, require_https=request.is_secure()):
        next_url = reverse("evidencias_list")
    return redirect(next_url)


def access_denied(request):
    return render(request, "access_denied.html", status=403)


@login_required
def actualizar_observaciones(request, envio_id):
    """Vista para actualizar observaciones de una evidencia. Solo administradores."""
    if request.method != "POST":
        return JsonResponse({"error": "Método no permitido"}, status=405)

    # Verificar que el usuario sea administrador o superusuario
    if not (request.user.is_superuser or request.user.groups.filter(name="administrador").exists()):
        return JsonResponse({"error": "No tienes permisos para editar observaciones"}, status=403)

    envio = get_object_or_404(Envio, id=envio_id)
    anterior = envio.observaciones or ""
    envio.observaciones = request.POST.get("observaciones", "").strip()
    envio.save(update_fields=["observaciones"])
    if anterior != envio.observaciones:
        from notificaciones.services import notificar_revision

        notificar_revision(envio)
    return JsonResponse({"success": True, "observaciones": envio.observaciones})


@login_required
def archivo_evidencia(request, pk):
    import mimetypes

    from django.http import FileResponse, Http404

    envio = get_object_or_404(_visible_envios(request.user), pk=pk)
    if not envio.archivo_evidencia:
        raise Http404("El archivo no está disponible.")
    try:
        archivo = envio.archivo_evidencia.open("rb")
    except FileNotFoundError:
        raise Http404("El archivo no está disponible.")
    from pathlib import Path

    nombre = Path(envio.archivo_evidencia.name).name
    extension = Path(nombre).suffix.lower()
    inline = (
        extension in {".pdf", ".jpg", ".jpeg", ".png", ".gif", ".txt", ".mp4", ".webm", ".ogg", ".mp3", ".wav"}
        and request.GET.get("descargar") != "1"
    )
    response = FileResponse(
        archivo,
        as_attachment=not inline,
        filename=nombre,
        content_type=mimetypes.guess_type(nombre)[0] or "application/octet-stream",
    )
    response["X-Frame-Options"] = "SAMEORIGIN"
    response["Cache-Control"] = "private, no-store"
    return response


@login_required
def archivo_por_ruta(request, ruta):
    envio = get_object_or_404(_visible_envios(request.user), archivo_evidencia=ruta)
    return archivo_evidencia(request, envio.pk)
