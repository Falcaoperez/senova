from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_POST, require_safe

from cuentas.forms import ConfirmarPasswordForm
from Gesicom.exportaciones import respuesta_csv
from Gesicom.interfaz import render_panel
from Gesicom.utils import require_group

from .acceso import destino_notificacion
from .bandeja import cambiar_lectura, regreso_bandeja
from .forms import NovedadForm, PlazoReporteForm, PreferenciasForm
from .models import CorreoPendiente, Notificacion, Novedad, PlazoReporte, PreferenciasNotificacion
from .plazos import ConflictoPlazo, archivar_plazo, guardar_plazo, recordar_pendientes
from .resumen import resumen_de_peticion
from .selectors import agenda_filtrada, avisos_filtrados, resumen_agenda, resumen_seguimiento, seguimiento_filtrado
from .services import publicar_novedad


@login_required
def bandeja(request):
    preferencias, _ = PreferenciasNotificacion.objects.get_or_create(usuario=request.user)
    return render_panel(
        request,
        "notificaciones/bandeja.html",
        {
            "avisos": Paginator(avisos_filtrados(request.user, request.GET), 20).get_page(request.GET.get("page")),
            "sin_leer": resumen_de_peticion(request)["pendientes"],
            "preferencias_form": PreferenciasForm(instance=preferencias),
            "tipos": Notificacion.Tipo.choices,
            "q": request.GET.get("q", "")[:100],
            "estado": request.GET.get("estado", ""),
            "tipo": request.GET.get("tipo", ""),
            "aviso_id": request.GET.get("aviso", ""),
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
        messages.success(request, f"{total} notificaciones actualizadas.")
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    return redirect(regreso_bandeja(request.POST.get("next")))


@login_required
@require_POST
def marcar_todas(request):
    params = request.POST if request.POST.get("alcance") == "filtradas" else {}
    total = avisos_filtrados(request.user, params).filter(leida_en__isnull=True).update(leida_en=timezone.now())
    messages.success(request, f"{total} notificaciones marcadas como leídas.")
    return redirect(regreso_bandeja(request.POST.get("next")))


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
def mis_plazos(request):
    return render_panel(
        request,
        "notificaciones/mis_plazos.html",
        {
            "plazos": Paginator(agenda_filtrada(request.user, request.GET), 20).get_page(request.GET.get("page")),
            "agenda": resumen_agenda(request.user),
            "proyectos": PlazoReporte.PROYECTOS,
            "q": request.GET.get("q", "")[:100],
            "estado": request.GET.get("estado", ""),
            "proyecto": request.GET.get("proyecto", ""),
            "plazo_id": request.GET.get("plazo", ""),
        },
    )


@require_group("administrador")
def novedades_admin(request):
    novedades = Novedad.objects.select_related("creada_por").annotate(
        destinatarios_total=Count("notificacion", distinct=True),
        leidas_total=Count("notificacion", distinct=True, filter=Q(notificacion__leida_en__isnull=False)),
        enviados_total=Count("notificacion", distinct=True, filter=Q(notificacion__correo__estado="enviado")),
    )
    q = request.GET.get("q", "").strip()[:100]
    if q:
        novedades = novedades.filter(Q(titulo__icontains=q) | Q(contenido__icontains=q))
    cola = CorreoPendiente.objects.aggregate(
        pendientes=Count("pk", filter=Q(estado__in=["pendiente", "procesando"])),
        errores=Count("pk", filter=Q(estado="error")),
        cancelados=Count("pk", filter=Q(estado="cancelado")),
    )
    return render_panel(
        request,
        "notificaciones/novedades_admin.html",
        {
            "novedades": Paginator(novedades.order_by("-publicada_en", "-pk"), 20).get_page(request.GET.get("page")),
            "correos_pendientes": cola["pendientes"],
            "correos_error": cola["errores"],
            "correos_cancelados": cola["cancelados"],
            "trabajador_activo": cache.get("notificaciones:trabajador"),
            "q": q,
        },
    )


@require_group("administrador")
def crear_novedad(request):
    form = NovedadForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            novedad = form.save(commit=False)
            novedad.creada_por = request.user
            novedad.save()
            form.save_m2m()
            total = publicar_novedad(novedad)
        messages.success(
            request, f"Novedad publicada para {total} usuarios. Los correos se procesarán en segundo plano."
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
        },
    )


@require_group("administrador")
def plazos_admin(request):
    plazos = PlazoReporte.objects.prefetch_related("grupos").order_by("-activo", "fecha_limite", "pk")
    q = request.GET.get("q", "").strip()[:100]
    if q:
        plazos = plazos.filter(Q(titulo__icontains=q) | Q(descripcion__icontains=q))
    proyecto, estado = request.GET.get("proyecto", ""), request.GET.get("estado", "")
    if proyecto:
        plazos = plazos.filter(proyecto=proyecto)
    if estado == "archivado":
        plazos = plazos.filter(activo=False)
    elif estado in {"programado", "vencido"}:
        plazos = plazos.filter(activo=True)
        plazos = (
            plazos.filter(fecha_limite__lte=timezone.now())
            if estado == "vencido"
            else plazos.filter(fecha_limite__gt=timezone.now())
        )
    return render_panel(
        request,
        "notificaciones/plazos_admin.html",
        {
            "plazos": Paginator(plazos, 25).get_page(request.GET.get("page")),
            "q": q,
            "proyecto": proyecto,
            "estado": estado,
            "proyectos": PlazoReporte.PROYECTOS,
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
def seguimiento_plazo(request, pk):
    plazo = get_object_or_404(PlazoReporte.objects.prefetch_related("grupos"), pk=pk)
    return render_panel(
        request,
        "notificaciones/seguimiento_plazo.html",
        {
            "plazo": plazo,
            "seguimiento": resumen_seguimiento(plazo),
            "destinatarios": Paginator(seguimiento_filtrado(plazo, request.GET), 25).get_page(request.GET.get("page")),
            "q": request.GET.get("q", "")[:100],
            "estado": request.GET.get("estado", ""),
        },
    )


@require_group("administrador")
def seguimiento_csv(request, pk):
    plazo = get_object_or_404(PlazoReporte, pk=pk)
    usuarios = seguimiento_filtrado(plazo, request.GET)

    def filas():
        yield ["Usuario", "Nombre", "Correo", "Entrega", "Última entrega (Colombia)", "Última revisión"]
        for usuario in usuarios.iterator(chunk_size=500):
            entrega = "Pendiente" if not usuario.entregado else "A tiempo" if usuario.a_tiempo else "Fuera de plazo"
            revision = (
                ""
                if not usuario.entregado
                else "Aprobada"
                if usuario.ultima_aprobada
                else "Rechazada"
                if usuario.ultima_rechazada
                else "En revisión"
            )
            fecha = (
                timezone.localtime(usuario.ultima_entrega).strftime("%Y-%m-%d %H:%M:%S")
                if usuario.ultima_entrega
                else ""
            )
            yield [usuario.username, usuario.get_full_name(), usuario.email, entrega, fecha, revision]

    return respuesta_csv(filas(), f"seguimiento-plazo-{plazo.pk}.csv")


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
