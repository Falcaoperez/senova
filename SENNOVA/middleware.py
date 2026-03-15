from django.http import JsonResponse
from django.core.cache import cache
from django.utils.deprecation import MiddlewareMixin
import time


class MiddlewareLimiteVelocidad(MiddlewareMixin):
    INTENTOS_LIMITE_VELOCIDAD = 5
    VENTANA_LIMITE_VELOCIDAD = 300
    
    def procesar_solicitud(self, request):
        if request.path in ['/login/', '/register/']:
            ip = self._obtener_ip_cliente(request)
            rate_limit_key = f'rate_limit:{request.path}:{ip}'
            
            attempts = cache.get(rate_limit_key, 0)
            
            if attempts >= self.INTENTOS_LIMITE_VELOCIDAD:
                return JsonResponse(
                    {'error': 'Demasiados intentos. Intenta más tarde.'},
                    status=429
                )
            
            if request.method == 'POST':
                cache.set(rate_limit_key, attempts + 1, self.VENTANA_LIMITE_VELOCIDAD)
        
        return None
    
    @staticmethod
    def _obtener_ip_cliente(request):
        x_reenviado_para = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_reenviado_para:
            ip = x_reenviado_para.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
