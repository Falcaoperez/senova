"""Vistas de la app 'Gesicom'.

Incluye:
- Páginas públicas (home, contacto, ayuda)
- Gestión y listas de envíos de evidencia
- Reportes y exportación CSV
- Control de acceso por grupos/roles
"""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_POST

from .exportaciones import respuesta_csv
from .interfaz import render_panel
from .models import Envio
from .reportes import contexto_reportes, filas_evidencias, serie_trimestral
from .selectors import (
    _evidencias_context,
    _filtered_envios,
    _filtros,
    _home_url_for_user,
    _panel_context,
    _visible_envios,
)
from .utils import (
    calculate_stats,
    require_group,
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
    return render_panel(request, "reportes.html", contexto_reportes(request))


def _error_exportacion(request):
    form = _filtros(request)
    if form.is_valid():
        return None
    return render(
        request,
        "error_filtros.html",
        {"filtros_form": form, "volver": reverse("reportes") + "?" + request.GET.urlencode()},
        status=400,
    )


@login_required
def reportes_csv(request):
    error = _error_exportacion(request)
    return error if error is not None else respuesta_csv(filas_evidencias(request), "reportes.csv")


@login_required
def reportes_trimestrales_csv(request):
    error = _error_exportacion(request)
    if error is not None:
        return error
    serie = serie_trimestral(_filtered_envios(request), _filtros(request))
    filas = [["Trimestre", "Nuevas", "Aprobadas"], *[[f["etiqueta"], f["nuevas"], f["aprobadas"]] for f in serie]]
    return respuesta_csv(filas, "reportes_trimestrales.csv")


@login_required
def evidencia(request, pk=None):
    from .archivos import informacion_adjunto
    from .forms import EvidenciaForm
    from .services import ConflictoEvidencia, corregir_evidencia, recuperar_registro, registrar_o_recuperar

    envio = get_object_or_404(Envio, pk=pk, usuario=request.user) if pk is not None else None
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
    valido = form.is_valid() if request.method == "POST" else False
    if request.method == "POST" and envio is None and form.cleaned_data.get("solicitud"):
        try:
            previo = recuperar_registro(request.user, form.cleaned_data["solicitud"])
        except ValidationError as error:
            form.add_error(None, error)
            valido = False
        else:
            if previo:
                messages.info(
                    request, "Este formulario ya había sido enviado. Abrimos la evidencia registrada, sin duplicarla."
                )
                return redirect("ver_evidencia", pk=previo.envio.pk)
    if request.method == "POST" and valido:
        try:
            if envio:
                guardado = corregir_evidencia(request.user, envio.pk, form.cleaned_data)
                messages.success(request, "Corrección guardada. La evidencia vuelve a revisión.")
            else:
                resultado = registrar_o_recuperar(request.user, form.cleaned_data)
                guardado = resultado.envio
                if resultado.reutilizado:
                    messages.info(
                        request,
                        "Este formulario ya había sido enviado. Abrimos la evidencia registrada, sin duplicarla.",
                    )
                else:
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
            **(informacion_adjunto(envio) if envio else {}),
        },
        status=status,
    )


@login_required
def evidencias_list(request):
    return render_panel(request, "evidencias_list.html", _evidencias_context(request))


def tabla_instructor(request):
    return redirect("evidencias_list")


def _detalle_evidencia(request, envio, status=200):
    from django.core.paginator import Paginator

    from .archivos import informacion_adjunto

    info = informacion_adjunto(envio)
    archivo_url = reverse("archivo_evidencia", args=[envio.pk]) if info["archivo_disponible"] else None
    return render(
        request,
        "ver_evidencia.html",
        {
            "envio": envio,
            "archivo_url": archivo_url,
            **info,
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
    from pathlib import Path

    from django.http import FileResponse, Http404, HttpResponse

    from .adjuntos import texto_limitado, vista_adjunto
    from .archivos import archivos_visibles

    envio = get_object_or_404(archivos_visibles(request.user), pk=pk)
    if not envio.archivo_evidencia:
        raise Http404("El archivo no está disponible.")
    try:
        archivo = envio.archivo_evidencia.open("rb")
        nombre = Path(archivo.name).name
        tipo, mime = vista_adjunto(archivo, nombre)
        if request.GET.get("vista") == "texto":
            if tipo != "text":
                archivo.close()
                raise Http404("La vista de texto no está disponible para este archivo.")
            texto, truncado = texto_limitado(archivo)
            archivo.close()
            response = HttpResponse(texto, content_type="text/plain; charset=utf-8")
            response["X-Preview-Truncated"] = "1" if truncado else "0"
        else:
            inline = tipo in {"image", "pdf", "text", "video", "audio"} and request.GET.get("descargar") != "1"
            response = FileResponse(archivo, as_attachment=not inline, filename=nombre, content_type=mime)
    except FileNotFoundError:
        raise Http404("El archivo no está disponible.") from None
    except OSError:
        response = HttpResponse(
            "No se pudo abrir el adjunto. Inténtalo de nuevo más tarde.",
            status=503,
            content_type="text/plain; charset=utf-8",
        )
    response["X-Frame-Options"] = "SAMEORIGIN"
    response["Cache-Control"] = "private, no-store"
    return response


@login_required
def archivo_por_ruta(request, ruta):
    from django.http import Http404

    from .archivos import archivos_visibles

    envio = archivos_visibles(request.user).filter(archivo_evidencia=ruta).order_by("pk").first()
    if envio is None:
        raise Http404("El archivo no está disponible.")
    return archivo_evidencia(request, envio.pk)
