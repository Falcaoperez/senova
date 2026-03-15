from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
import datetime

User = get_user_model()


class PasswordResetToken(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='password_reset_tokens')
    token = models.CharField(max_length=255, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)
    used = models.BooleanField(default=False)
    
    class Meta:
        verbose_name = "Token de Restablecimiento"
        verbose_name_plural = "Tokens de Restablecimiento"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['token']),
            models.Index(fields=['expires_at', 'used']),
        ]
    
    def __str__(self):
        return f"Token para {self.user.email}"
    
    def is_valid(self):
        return not self.used and timezone.now() < self.expires_at
    
    @classmethod
    def create_for_user(cls, user):
        from django.contrib.auth.tokens import default_token_generator
        token = default_token_generator.make_token(user)
        expires_at = timezone.now() + datetime.timedelta(hours=1)
        
        cls.objects.filter(user=user, used=False).delete()
        
        return cls.objects.create(
            user=user,
            token=token,
            expires_at=expires_at
        )
