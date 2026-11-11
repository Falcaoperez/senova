from urllib.parse import urlsplit

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, F, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from Gesicom.utils import require_group

from .forms import NovedadForm, PlazoReporteForm, PreferenciasForm
from .models import (
    CorreoPendiente,
    Notificacion,
    Novedad,
    PlazoReporte,
    PreferenciasNotificacion,
)
from .services import anunciar_plazo, plazos_para_usuario, publicar_novedad


@login_required
def bandeja(request):
    avisos = Notificacion.objects.filter(usuario=request.user)
    solo_pendientes = request.GET.get("estado") == "pendiente"
    if solo_pendientes:
        avisos = avisos.filter(leida_en__isnull=True)
    preferencias, _ = PreferenciasNotificacion.objects.get_or_create(usuario=request.user)
    form = PreferenciasForm(instance=preferencias)
    return render(
        request,
        "notificaciones/bandeja.html",
        {
            "avisos": Paginator(avisos, 20).get_page(request.GET.get("page")),
            "solo_pendientes": solo_pendientes,
            "preferencias_form": form,
        },
    )


@login_required
@require_POST
def abrir(request, pk):
    aviso = get_object_or_404(Notificacion, pk=pk, usuario=request.user)
    if not aviso.leida_en:
        aviso.leida_en = timezone.now()
        aviso.save(update_fields=["leida_en"])
    link = aviso.enlace or reverse("notificaciones:bandeja")
    if link.startswith("//") or (urlsplit(link).scheme not in ["", "https", "http"]):
        link = reverse("notificaciones:bandeja")
    return redirect(link)


@login_required
@require_POST
def marcar_todas(request):
    total = Notificacion.objects.filter(usuario=request.user, leida_en__isnull=True).update(leida_en=timezone.now())
    messages.success(request, f"{total} notificaciones marcadas como leídas.")
    return redirect("notificaciones:bandeja")


@login_required
@require_POST
def preferencias(request):
    instance, _ = PreferenciasNotificacion.objects.get_or_create(usuario=request.user)
    form = PreferenciasForm(request.POST, instance=instance)
    if form.is_valid():
        form.save()
        messages.success(request, "Preferencias de correo actualizadas.")
    return redirect("notificaciones:bandeja")


@login_required
def resumen(request):
    return JsonResponse(
        {"pendientes": Notificacion.objects.filter(usuario=request.user, leida_en__isnull=True).count()}
    )


@login_required
def mis_plazos(request):
    plazos = plazos_para_usuario(request.user, pendientes=False)
    entregas = (
        request.user.envios.exclude(plazo=None)
        .values("plazo_id")
        .annotate(
            a_tiempo=Count("pk", filter=Q(limite_aplicado__isnull=True) | Q(registrado_en__lte=F("limite_aplicado")))
        )
        .order_by()
    )
    entregas = list(entregas)
    cumplidos = {row["plazo_id"] for row in entregas}
    tardios = {row["plazo_id"] for row in entregas if row["a_tiempo"] == 0}
    return render(
        request,
        "notificaciones/mis_plazos.html",
        {"plazos": Paginator(plazos, 20).get_page(request.GET.get("page")), "cumplidos": cumplidos, "tardios": tardios},
    )


@require_group("administrador")
def novedades_admin(request):
    return render(
        request,
        "notificaciones/novedades_admin.html",
        {
            "novedades": Paginator(Novedad.objects.select_related("creada_por"), 20).get_page(request.GET.get("page")),
            "correos_pendientes": CorreoPendiente.objects.filter(estado__in=["pendiente", "procesando"]).count(),
            "correos_error": CorreoPendiente.objects.filter(estado="error").count(),
            "trabajador_activo": cache.get("notificaciones:trabajador"),
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
            request, f"Novedad publicada para {total} usuarios. Los avisos por correo se procesarán en segundo plano."
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
        },
    )


@require_group("administrador")
def plazos_admin(request):
    plazos = PlazoReporte.objects.prefetch_related("grupos").order_by("-activo", "fecha_limite")
    return render(
        request, "notificaciones/plazos_admin.html", {"plazos": Paginator(plazos, 25).get_page(request.GET.get("page"))}
    )


@require_group("administrador")
def editar_plazo(request, pk=None):
    plazo = get_object_or_404(PlazoReporte, pk=pk) if pk else None
    fecha_anterior = plazo.fecha_limite if plazo else None
    form = PlazoReporteForm(request.POST or None, instance=plazo)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            plazo = form.save(commit=False)
            if not plazo.pk:
                plazo.creado_por = request.user
            elif plazo.fecha_limite != fecha_anterior:
                plazo.version += 1
            plazo.save()
            form.save_m2m()
            if plazo.activo:
                anunciar_plazo(plazo)
        messages.success(request, "Plazo guardado. Los usuarios destinatarios recibirán la notificación.")
        return redirect("notificaciones:plazos_admin")
    return render(
        request,
        "notificaciones/formulario_admin.html",
        {
            "form": form,
            "heading": "Un plazo claro, un equipo conectado.",
            "description": "Define la entrega y la anticipación del recordatorio.",
            "submit_label": "Guardar plazo",
        },
    )


@require_group("administrador")
@require_POST
def reintentar_correos(request):
    count = CorreoPendiente.objects.filter(estado="error").update(
        estado="pendiente", intentos=0, proximo_intento=timezone.now(), bloqueado_hasta=None
    )
    messages.success(request, f"{count} correos vuelven a la cola de envío.")
    return redirect("notificaciones:novedades_admin")
