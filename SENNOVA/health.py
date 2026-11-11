from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.http import require_GET


@require_GET
def health(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        cache.get("gesicom:health")
    except Exception:
        return JsonResponse({"estado": "no disponible"}, status=503)
    return JsonResponse({"estado": "ok"})
