from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
import datetime

User = get_user_model()


class PasswordResetToken(models.Model):
    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name='password_reset_tokens')
    token = models.CharField(max_length=255, unique=True, db_index=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    expira_en = models.DateTimeField(db_index=True)
    utilizado = models.BooleanField(default=False)
    
    class Meta:
        verbose_name = "Token de Restablecimiento"
        verbose_name_plural = "Tokens de Restablecimiento"
        ordering = ['-creado_en']
        indexes = [
            models.Index(fields=['token']),
            models.Index(fields=['expira_en', 'utilizado']),
        ]
    
    def __str__(self):
        return f"Token para {self.usuario.email}"
    
    def es_valido(self):
        return not self.utilizado and timezone.now() < self.expira_en
    
    @classmethod
    def crear_para_usuario(cls, user):
        from django.contrib.auth.tokens import default_token_generator
        token = default_token_generator.make_token(user)
        expira_en = timezone.now() + datetime.timedelta(hours=1)
        
        cls.objects.filter(usuario=user, utilizado=False).delete()
        
        return cls.objects.create(
            usuario=user,
            token=token,
            expira_en=expira_en
        )
