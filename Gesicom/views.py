"""Vistas de la app 'Gesicom'.

Incluye:
- Páginas públicas (home, contacto, ayuda)
- Gestión y listas de envíos de evidencia
- Reportes y exportación CSV
- Control de acceso por grupos/roles
"""

import csv
import datetime

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
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
    return render(request, "ayuda.html", {"pin_minutos": settings.PASSWORD_RESET_PIN_MINUTES})


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
def evidencia(request, pk=None):
    from .forms import EvidenciaForm
    from .services import ConflictoEvidencia, corregir_evidencia, registrar_evidencia

    envio = get_object_or_404(Envio, pk=pk, usuario=request.user) if pk else None
    if envio and envio.aprobada:
        raise PermissionDenied("Una evidencia aprobada no se puede corregir.")
    form = EvidenciaForm(
        request.POST if request.method == "POST" else None,
        request.FILES or None,
        usuario=request.user,
        envio=envio,
        initial={"plazo": request.GET.get("plazo", "")},
    )
    status = 200
    if request.method == "POST" and form.is_valid():
        try:
            if envio:
                guardado = corregir_evidencia(request.user, envio.pk, form.cleaned_data)
                messages.success(request, "Corrección guardada. La evidencia vuelve a revisión.")
            else:
                guardado = registrar_evidencia(request.user, form.cleaned_data)
                messages.success(request, "Evidencia enviada correctamente")
            return redirect("ver_evidencia", pk=guardado.pk)
        except ConflictoEvidencia as error:
            form.add_error(None, error)
            status = 409
        except ValidationError as error:
            form.add_error(None, error)
    return render(
        request,
        "formulario.html",
        {
            "form": form,
            "envio": envio,
            "home_url": _home_url_for_user(request.user),
            "errores": [str(error) for errors in form.errors.values() for error in errors],
            "exito": False,
        },
        status=status,
    )


@login_required
def evidencias_list(request):
    return render(request, "evidencias_list.html", _evidencias_context(request))


def tabla_instructor(request):
    return redirect("evidencias_list")


def _detalle_evidencia(request, envio, status=200):
    from pathlib import Path

    from django.core.paginator import Paginator

    archivo_url = reverse("archivo_evidencia", args=[envio.pk]) if envio.archivo_evidencia else None
    suffix = Path(envio.archivo_evidencia.name or "").suffix.lower()
    tipos = {
        "image": {".jpg", ".jpeg", ".png", ".gif"},
        "pdf": {".pdf"},
        "text": {".txt"},
        "office": {".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".ods", ".odp"},
        "video": {".mp4", ".webm", ".ogg"},
        "audio": {".mp3", ".wav"},
    }
    kind = next((tipo for tipo, extensiones in tipos.items() if suffix in extensiones), "other")
    return render(
        request,
        "ver_evidencia.html",
        {
            "envio": envio,
            "archivo_url": archivo_url,
            "preview_kind": kind,
            "puede_corregir": request.user.pk == envio.usuario_id and not envio.aprobada,
            "historial": Paginator(envio.historial.select_related("actor"), 20).get_page(request.GET.get("page")),
        },
        status=status,
    )


@login_required
def ver_evidencia(request, pk):
    return _detalle_evidencia(request, get_object_or_404(_visible_envios(request.user), pk=pk))


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
    from django.utils.http import url_has_allowed_host_and_scheme

    from .services import ConflictoEvidencia, revisar_evidencia

    if request.POST.get("valor") not in {"0", "1"}:
        return JsonResponse({"error": "Estado inválido"}, status=400)
    try:
        envio, cambiado = revisar_evidencia(
            request.user, pk, request.POST["valor"] == "1", version=request.POST.get("version")
        )
    except ConflictoEvidencia as error:
        messages.error(request, " ".join(error.messages))
        return _detalle_evidencia(request, get_object_or_404(_visible_envios(request.user), pk=pk), status=409)
    messages.success(request, "Estado de evidencia actualizado." if cambiado else "La evidencia ya tenía ese estado.")
    next_url = request.POST.get("next") or request.META.get("HTTP_REFERER") or reverse("evidencias_list")
    if not url_has_allowed_host_and_scheme(next_url, {request.get_host()}, require_https=request.is_secure()):
        next_url = reverse("evidencias_list")
    return redirect(next_url)


def access_denied(request):
    return render(request, "access_denied.html", status=403)


@login_required
@require_POST
def actualizar_observaciones(request, envio_id):
    from .services import ConflictoEvidencia, observar_evidencia

    try:
        envio = observar_evidencia(
            request.user, envio_id, request.POST.get("observaciones", "").strip(), version=request.POST.get("version")
        )
    except PermissionDenied:
        return JsonResponse({"error": "No tienes permisos para editar observaciones"}, status=403)
    except ConflictoEvidencia as error:
        return JsonResponse({"error": " ".join(error.messages)}, status=409)
    except ValidationError as error:
        return JsonResponse({"error": " ".join(error.messages)}, status=400)
    return JsonResponse({"success": True, "observaciones": envio.observaciones, "version": envio.version})


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
