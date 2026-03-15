from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from Gesicom.models import Envio
from datetime import date, timedelta
import random


class Command(BaseCommand):
    help = 'Crea evidencias de prueba para usuarios existentes'

    def handle(self, *args, **options):
        # Tipos de evidencia posibles
        tipos_evidencia = [
            'Planeacion',
            'Ejecucion',
            'Evaluacion',
            'Informe Final',
            'Planeacion, Ejecucion',
            'Evaluacion, Informe Final',
        ]

        # Proyectos disponibles
        proyectos = ['LEM', 'GIVIT', 'ACAF', 'DEPOS', 'IFPI', 'TUGA']

        # Enlaces de ejemplo
        enlaces_ejemplo = [
            'https://drive.google.com/ejemplo1',
            'https://docs.google.com/ejemplo2',
            'https://github.com/ejemplo3',
            '',  # Sin enlace
        ]

        # Observaciones de ejemplo
        observaciones_ejemplo = [
            'Documento completo con todos los requisitos',
            'Primera version del proyecto',
            'Revision y aprobacion pendiente',
            'Material actualizado',
            '',
        ]

        # Obtener usuarios activos
        usuarios = User.objects.filter(is_active=True)

        if not usuarios.exists():
            self.stdout.write(self.style.WARNING('No hay usuarios activos. Crea usuarios primero.'))
            return

        evidencias_creadas = 0

        for usuario in usuarios:
            # Crear entre 2 y 5 evidencias por usuario
            num_evidencias = random.randint(2, 5)

            for i in range(num_evidencias):
                # Calcular fecha (últimos 30 días)
                dias_atras = random.randint(0, 30)
                fecha = date.today() - timedelta(days=dias_atras)

                # Crear la evidencia
                evidencia = Envio.objects.create(
                    usuario=usuario,
                    nombre=f'Evidencia {i+1} - {usuario.username}',
                    proyecto=random.choice(proyectos),
                    tipo_evidencia=random.choice(tipos_evidencia),
                    link_evidencia=random.choice(enlaces_ejemplo) or None,
                    observaciones=random.choice(observaciones_ejemplo),
                    fecha_envio=fecha
                )

                evidencias_creadas += 1

                self.stdout.write(
                    self.style.SUCCESS(
                        f'Evidencia creada: {evidencia.nombre} - Usuario: {usuario.username}'
                    )
                )

        self.stdout.write(
            self.style.SUCCESS(
                f'\nProceso completado: {evidencias_creadas} evidencias de prueba creadas para {usuarios.count()} usuarios.'
            )
        )
