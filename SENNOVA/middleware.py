from django.http import JsonResponse
from django.core.cache import cache
from django.utils.deprecation import MiddlewareMixin
import time


class RateLimitMiddleware(MiddlewareMixin):
    RATE_LIMIT_ATTEMPTS = 5
    RATE_LIMIT_WINDOW = 300
    
    def process_request(self, request):
        if request.path in ['/login/', '/register/']:
            ip = self._get_client_ip(request)
            rate_limit_key = f'rate_limit:{request.path}:{ip}'
            
            attempts = cache.get(rate_limit_key, 0)
            
            if attempts >= self.RATE_LIMIT_ATTEMPTS:
                return JsonResponse(
                    {'error': 'Demasiados intentos. Intenta más tarde.'},
                    status=429
                )
            
            if request.method == 'POST':
                cache.set(rate_limit_key, attempts + 1, self.RATE_LIMIT_WINDOW)
        
        return None
    
    @staticmethod
    def _get_client_ip(request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
