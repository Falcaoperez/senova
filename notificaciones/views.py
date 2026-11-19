from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods, require_POST, require_safe

from cuentas.forms import ConfirmarPasswordForm
from Gesicom.exportaciones import respuesta_csv
from Gesicom.interfaz import render_panel
from Gesicom.utils import require_group

from .acceso import destino_notificacion
from .bandeja import cambiar_lectura, regreso_bandeja
from .calendario import cuadricula_mensual
from .exportaciones import filas_seguimiento
from .forms import (
    FiltrosAgendaForm,
    FiltrosBandejaForm,
    FiltrosNovedadesForm,
    FiltrosPlazosAdminForm,
    FiltrosSeguimientoForm,
    NovedadForm,
    PlazoReporteForm,
    PreferenciasForm,
)
from .icalendar import respuesta_calendario
from .models import CorreoPendiente, Notificacion, PlazoReporte, PreferenciasNotificacion
from .novedades import pagina_novedades
from .plazos import ConflictoPlazo, archivar_plazo, guardar_plazo, recordar_pendientes
from .publicacion import publicar_o_recuperar, recuperar_publicacion
from .resumen import resumen_de_peticion
from .selectors import (
    agenda_filtrada,
    avisos_filtrados,
    plazos_administracion,
    resumen_agenda,
    resumen_seguimiento,
    seguimiento_filtrado,
)


@login_required
@require_safe
def bandeja(request):
    preferencias, _ = PreferenciasNotificacion.objects.get_or_create(usuario=request.user)
    filtros = FiltrosBandejaForm(request.GET)
    return render_panel(
        request,
        "notificaciones/bandeja.html",
        {
            "avisos": Paginator(avisos_filtrados(request.user, filtros), 20).get_page(request.GET.get("page")),
            "sin_leer": resumen_de_peticion(request)["pendientes"],
            "preferencias_form": PreferenciasForm(instance=preferencias),
            "tipos": Notificacion.Tipo.choices,
            "q": request.GET.get("q", "")[:100],
            "estado": request.GET.get("estado", ""),
            "tipo": request.GET.get("tipo", ""),
            "aviso_id": request.GET.get("aviso", ""),
            "desde": request.GET.get("desde", "")[:10],
            "hasta": request.GET.get("hasta", "")[:10],
            "filtros_form": filtros,
            "mensaje_filtros": "No se muestran ni marcan resultados hasta corregir los filtros.",
        },
    )


@login_required
@require_POST
def abrir(request, pk):
    aviso = get_object_or_404(
        Notificacion.objects.select_related("usuario", "plazo", "novedad"), pk=pk, usuario=request.user
    )
    Notificacion.objects.filter(pk=pk, leida_en__isnull=True).update(leida_en=timezone.now())
    destino, motivo = destino_notificacion(aviso)
    if motivo:
        messages.info(request, motivo)
    return redirect(destino or reverse("notificaciones:bandeja"))


@login_required
@require_POST
def lectura(request, pk=None):
    try:
        total = cambiar_lectura(
            request.user, [str(pk)] if pk is not None else request.POST.getlist("avisos"), request.POST.get("accion")
        )
    except ValidationError as error:
        return _respuesta_lectura(request, " ".join(error.messages), status=400)
    except Http404:
        if request.headers.get("X-Inbox-Action") == "1":
            return _respuesta_lectura(request, "No se pudo actualizar la selección de avisos.", status=404)
        raise
    return _respuesta_lectura(request, f"{total} notificaciones actualizadas.", total=total)


def _respuesta_lectura(request, mensaje, *, total=0, status=200):
    if request.headers.get("X-Inbox-Action") == "1":
        response = JsonResponse(
            {"mensaje": mensaje, "actualizados": total} if status == 200 else {"error": mensaje}, status=status
        )
        response["Cache-Control"] = "private, no-store"
        return response
    if status == 200:
        messages.success(request, mensaje)
    else:
        messages.error(request, mensaje)
    return redirect(regreso_bandeja(request.POST.get("next")))


@login_required
@require_POST
def marcar_todas(request):
    alcance = request.POST.get("alcance", "todas")
    filtros = FiltrosBandejaForm(request.POST if alcance == "filtradas" else {})
    if alcance not in {"todas", "filtradas"} or not filtros.is_valid():
        return _respuesta_lectura(request, "Revisa los filtros antes de marcar los resultados como leídos.", status=400)
    total = avisos_filtrados(request.user, filtros).filter(leida_en__isnull=True).update(leida_en=timezone.now())
    return _respuesta_lectura(request, f"{total} notificaciones marcadas como leídas.", total=total)


@login_required
@require_POST
def preferencias(request):
    instance, _ = PreferenciasNotificacion.objects.get_or_create(usuario=request.user)
    form = PreferenciasForm(request.POST, instance=instance)
    if form.is_valid():
        form.save()
        messages.success(request, "Preferencias de correo actualizadas.")
    else:
        messages.error(request, "Revisa las preferencias de correo.")
    return redirect(regreso_bandeja(request.POST.get("next")))


@login_required
@require_safe
def resumen(request):
    detalle = request.GET.get("detalle") == "1"
    resumen = resumen_de_peticion(request, recientes=detalle)
    datos = {"pendientes": resumen["pendientes"]}
    if detalle:
        datos["recientes"] = [
            {
                "id": aviso.pk,
                "titulo": aviso.titulo,
                "fecha": date_format(timezone.localtime(aviso.creada_en), "d M · H:i"),
                "leida": aviso.leida_en is not None,
                "abrir_url": reverse("notificaciones:abrir", args=[aviso.pk]),
            }
            for aviso in resumen["recientes"]
        ]
    return JsonResponse(datos)


@login_required
@require_safe
def mis_plazos(request):
    form = FiltrosAgendaForm(request.GET)
    valido = form.is_valid()
    if valido and form.mes_automatico:
        return redirect(reverse("notificaciones:mis_plazos") + form.consulta_url())
    consulta = agenda_filtrada(request.user, form)
    datos = form.cleaned_data
    vista = datos.get("vista") or "lista"
    mes = datos.get("mes") or ""
    actual = timezone.localdate().strftime("%Y-%m")
    calendario = cuadricula_mensual(consulta, form.fecha_mes()) if valido and vista == "calendario" else {}
    return render_panel(
        request,
        "notificaciones/mis_plazos.html",
        {
            "plazos": Paginator(consulta, 20).get_page(request.GET.get("page")) if vista != "calendario" else None,
            "agenda": resumen_agenda(request.user),
            "proyectos": PlazoReporte.PROYECTOS,
            "q": request.GET.get("q", "")[:100],
            "estado": request.GET.get("estado", ""),
            "proyecto": request.GET.get("proyecto", ""),
            "plazo_id": request.GET.get("plazo", ""),
            "filtros_form": form,
            "mensaje_filtros": "No se muestran ni exportan plazos hasta corregir los filtros.",
            "vista": vista,
            "mes": request.GET.get("mes", "")[:7],
            "mes_actual": actual,
            "url_lista": form.consulta_url(vista="lista"),
            "url_calendario": form.consulta_url(vista="calendario", mes=mes or actual),
            "url_exportar": reverse("notificaciones:calendario_ics") + form.consulta_url() if valido else None,
            **calendario,
        },
    )


@login_required
@require_safe
def calendario_ics(request):
    form = FiltrosAgendaForm(request.GET)
    if not form.is_valid():
        return render(
            request,
            "error_filtros.html",
            {
                "filtros_form": form,
                "volver": reverse("notificaciones:mis_plazos") + form.consulta_url(),
                "seccion_error": "GESICOM / MIS PLAZOS",
                "regreso_error": reverse("notificaciones:mis_plazos"),
            },
            status=400,
        )
    return respuesta_calendario(agenda_filtrada(request.user, form), form.cleaned_data["mes"])


@require_group("administrador")
@require_safe
def novedades_admin(request):
    form = FiltrosNovedadesForm(request.GET)
    pagina = pagina_novedades(form, request.GET.get("page"))

    def enlace(numero):
        return reverse("notificaciones:novedades_admin") + form.consulta_url(pagina=numero)

    cola = CorreoPendiente.objects.aggregate(
        pendientes=Count("pk", filter=Q(estado__in=["pendiente", "procesando"])),
        errores=Count("pk", filter=Q(estado="error")),
        cancelados=Count("pk", filter=Q(estado="cancelado")),
    )
    return render_panel(
        request,
        "notificaciones/novedades_admin.html",
        {
            "novedades": pagina,
            "correos_pendientes": cola["pendientes"],
            "correos_error": cola["errores"],
            "correos_cancelados": cola["cancelados"],
            "trabajador_activo": cache.get("notificaciones:trabajador"),
            "filtros_form": form,
            "mensaje_filtros": "No se muestran novedades hasta corregir los filtros.",
            "url_anterior": enlace(pagina.previous_page_number()) if pagina.has_previous() else None,
            "url_siguiente": enlace(pagina.next_page_number()) if pagina.has_next() else None,
        },
    )


@require_group("administrador")
@require_http_methods(["GET", "HEAD", "POST"])
def crear_novedad(request):
    form = NovedadForm(request.POST if request.method == "POST" else None, usuario=request.user)
    reutilizado = (
        "Este formulario ya había sido enviado. Conservamos la publicación original sin generar avisos nuevos."
    )
    if request.method == "POST":
        valido = form.is_valid()
        if codigo := form.cleaned_data.get("solicitud"):
            try:
                previo = recuperar_publicacion(request.user, codigo)
            except ValidationError as error:
                form.add_error(None, error)
                valido = False
            else:
                if previo:
                    messages.info(request, reutilizado)
                    return redirect("notificaciones:novedades_admin")
        if valido:
            try:
                resultado = publicar_o_recuperar(request.user, form.cleaned_data)
            except ValidationError as error:
                form.add_error(None, error)
            else:
                if resultado.reutilizado:
                    messages.info(request, reutilizado)
                else:
                    messages.success(
                        request,
                        f"Novedad publicada para {resultado.nuevos_avisos} usuarios. Los correos se procesarán en segundo plano.",
                    )
                return redirect("notificaciones:novedades_admin")
    return render(
        request,
        "notificaciones/formulario_admin.html",
        {
            "form": form,
            "heading": "Compartamos lo que está pasando.",
            "description": "Publica una novedad y notifícala a la comunidad.",
            "submit_label": "Publicar novedad",
            "volver": reverse("notificaciones:novedades_admin"),
            "ayuda_publicacion": "Si la conexión se interrumpe, puedes reenviar este mismo formulario: se recuperará la publicación ya aceptada.",
            "nuevo_formulario": reverse("notificaciones:crear_novedad") if form.errors else None,
        },
    )


@require_group("administrador")
@require_safe
def plazos_admin(request):
    form = FiltrosPlazosAdminForm(request.GET)
    return render_panel(
        request,
        "notificaciones/plazos_admin.html",
        {
            "plazos": Paginator(plazos_administracion(form), 25).get_page(request.GET.get("page")),
            "q": request.GET.get("q", "")[:100],
            "proyecto": request.GET.get("proyecto", ""),
            "estado": request.GET.get("estado", ""),
            "proyectos": form.fields["proyecto"].choices[1:],
            "filtros_form": form,
            "mensaje_filtros": "No se muestran plazos hasta corregir los filtros.",
        },
    )


@require_group("administrador")
def editar_plazo(request, pk=None):
    plazo = get_object_or_404(PlazoReporte, pk=pk) if pk is not None else None
    form = PlazoReporteForm(request.POST if request.method == "POST" else None, instance=plazo)
    conflicto = False
    if request.method == "POST" and form.is_valid():
        try:
            _, total, cambio = guardar_plazo(request.user, form.cleaned_data, pk=pk)
        except ConflictoPlazo as error:
            form.add_error(None, error)
            conflicto = True
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(
                request, f"Plazo guardado. Se prepararon {total} avisos." if cambio else "El plazo no tiene cambios."
            )
            return redirect("notificaciones:plazos_admin")
    conflicto = conflicto or form.has_error("__all__", "conflicto")
    return render(
        request,
        "notificaciones/formulario_admin.html",
        {
            "form": form,
            "heading": "Un plazo claro, un equipo conectado.",
            "description": "Define la entrega y la anticipación del recordatorio. Las entregas previas conservan su fecha original.",
            "submit_label": "Guardar plazo",
            "volver": reverse("notificaciones:plazos_admin"),
            "conflicto": conflicto,
        },
        status=409 if conflicto else 200,
    )


@require_group("administrador")
@require_safe
def seguimiento_plazo(request, pk):
    plazo = get_object_or_404(PlazoReporte.objects.prefetch_related("grupos"), pk=pk)
    form = FiltrosSeguimientoForm(request.GET)
    return render_panel(
        request,
        "notificaciones/seguimiento_plazo.html",
        {
            "plazo": plazo,
            "seguimiento": resumen_seguimiento(plazo),
            "destinatarios": Paginator(seguimiento_filtrado(plazo, form), 25).get_page(request.GET.get("page")),
            "q": request.GET.get("q", "")[:100],
            "estado": request.GET.get("estado", ""),
            "filtros_form": form,
            "url_exportar": reverse("notificaciones:seguimiento_csv", args=[pk]) + form.consulta_url()
            if form.is_valid()
            else None,
            "mensaje_filtros": "No se muestran ni exportan destinatarios hasta corregir los filtros.",
        },
    )


@require_group("administrador")
@require_safe
def seguimiento_csv(request, pk):
    plazo = get_object_or_404(PlazoReporte, pk=pk)
    form = FiltrosSeguimientoForm(request.GET)
    if not form.is_valid():
        regreso = reverse("notificaciones:seguimiento_plazo", args=[pk])
        return render(
            request,
            "error_filtros.html",
            {
                "filtros_form": form,
                "volver": regreso,
                "regreso_error": regreso,
                "regreso_texto": "Volver al seguimiento",
                "seccion_error": "GESICOM / ADMINISTRACIÓN / SEGUIMIENTO",
            },
            status=400,
        )
    return respuesta_csv(filas_seguimiento(seguimiento_filtrado(plazo, form)), f"seguimiento-plazo-{plazo.pk}.csv")


@require_group("administrador")
@require_POST
@sensitive_post_parameters("contrasena_actual")
def accion_plazo(request, pk, accion):
    actual = get_user_model().objects.get(pk=request.user.pk)
    if not ConfirmarPasswordForm(request.POST, usuario=actual).is_valid():
        messages.error(request, "Confirma tu contraseña actual para realizar esta acción.")
    else:
        try:
            if accion == "recordar":
                total = recordar_pendientes(actual, pk, request.POST.get("revision_actual"))
                messages.success(
                    request, f"Se prepararon {total} recordatorios adicionales. Los avisos existentes no se duplican."
                )
            elif accion == "archivar":
                archivar_plazo(actual, pk, request.POST.get("revision_actual"))
                messages.success(request, "Plazo archivado. Se cancelaron los correos pendientes de ese plazo.")
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
    return redirect("notificaciones:seguimiento_plazo", pk=pk)


@require_group("administrador")
@require_POST
def reintentar_correos(request):
    count = CorreoPendiente.objects.filter(estado="error").update(
        estado="pendiente", intentos=0, proximo_intento=timezone.now(), bloqueado_hasta=None
    )
    messages.success(request, f"{count} correos vuelven a la cola de envío.")
    return redirect("notificaciones:novedades_admin")
