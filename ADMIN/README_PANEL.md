# Panel de Administración de Usuarios

## 🎨 Nuevo Diseño Implementado

Se ha creado una interfaz moderna para el panel de administración de usuarios, basada en el diseño solicitado con paleta de colores verde salvia.

## 📋 Características

### Interfaz Principal
- **Header**: Logo SENA y título del panel, con perfil de usuario y botón de cerrar sesión
- **Sidebar**: Navegación lateral con secciones:
  - 🏠 Inicio
  - 👥 Usuarios (vista principal)
  - ⚙️ Configuración
  - 🔔 Notificaciones (con contador)
- **Contenido Principal**: Tabla de usuarios con funcionalidad completa

### Funcionalidades

#### 1. Búsqueda en Tiempo Real
- Busca por nombre, correo o ID
- Filtrado instantáneo sin recargar la página

#### 2. Gestión de Usuarios
- Ver lista completa de usuarios
- Editar roles mediante dropdown
- Activar/desactivar usuarios
- Acceso rápido a detalles de usuario

#### 3. Edición de Roles
- Dropdown por usuario para cambiar roles
- Opciones: Autor, Editor, Administrador
- Guardado masivo con botón "Guardar"

#### 4. Acciones por Usuario
- ✏️ Editar: Acceso a página de detalles
- 🗑️ Activar/Desactivar: Toggle de estado

## 🚀 Cómo Usar

### Acceder al Panel

1. Inicia el servidor:
```bash
cd "PRoyecto django/Proyecto-html"
python manage.py runserver
```

2. Visita: `http://127.0.0.1:8000/administrador/`

3. Debes estar autenticado como administrador o tener el grupo "administrador"

### Crear Usuarios de Prueba

Si necesitas usuarios de prueba, ejecuta:

```bash
python manage.py crear_usuarios_prueba
```

Esto creará 8 usuarios con:
- Contraseña: `Sena2024`
- Diferentes roles (Autor, Editor, Administrador)
- Estados variados (activos e inactivos)

### Usuarios de Prueba Creados

| ID  | Nombre           | Email              | Rol            | Estado   |
|-----|------------------|--------------------|----------------|----------|
| 101 | María Rodríguez  | maria.r@email.com  | Autor          | Activo   |
| 102 | Juan Pérez       | juan.p@email.com   | Autor          | Activo   |
| 103 | María Folaia     | pun.c@email.com    | Editor         | Activo   |
| 104 | María Hérez      | juan.g@email.com   | Editor         | Inactivo |
| 105 | Cntry Marco      | enm.e@email.com    | Administrador  | Inactivo |
| 106 | Lan Rorez        | con.n@email.com    | Administrador  | Inactivo |
| 107 | Mary Diolez      | man.v@email.com    | Editor         | Inactivo |
| 108 | Lisra Cargez     | con.p@email.com    | Autor          | Inactivo |

## 📂 Archivos Creados

### Templates
- `ADMIN/templates/admin_personalizado/base_modern.html` - Template base con diseño moderno
- `ADMIN/templates/admin_personalizado/gestionar_usuarios_modern.html` - Vista de lista de usuarios

### Vistas
- Actualizada: `ADMIN/views.py` función `gestionar_usuarios()`
  - Ahora soporta POST para guardar cambios de roles
  - Pasa grupos disponibles al contexto

### Comandos
- `ADMIN/management/commands/crear_usuarios_prueba.py` - Comando para crear datos de prueba

## 🎨 Paleta de Colores

- **Verde Salvia Principal**: `#6b8e6b`
- **Verde Salvia Claro**: `#d4e5d4`
- **Hover Verde**: `#5a7a5a`
- **Activo Verde**: `#d1f4d1`
- **Texto Principal**: `#374151`
- **Texto Secundario**: `#6b7280`
- **Bordes**: `#e5e7eb`

## 🔧 Personalización

### Cambiar Roles Disponibles

Edita los grupos en Django Admin o mediante código:

```python
from django.contrib.auth.models import Group

# Crear nuevo rol
Group.objects.get_or_create(name='nuevo_rol')
```

### Agregar Campos a la Tabla

1. Edita `gestionar_usuarios_modern.html`
2. Añade columna en `<thead>` y `<tbody>`
3. Actualiza el contexto en `views.py` si necesitas datos adicionales

### Cambiar Colores

Modifica las variables CSS en `base_modern.html`:
- Busca `#6b8e6b` y reemplaza con tu color principal
- Busca `#d4e5d4` y reemplaza con tu color secundario

## 📱 Responsive

El diseño es completamente responsive:
- **Desktop**: Sidebar fijo a la izquierda
- **Mobile**: Sidebar apilado arriba, tabla con scroll horizontal

## 🔒 Seguridad

- Requiere autenticación (`@login_required`)
- Requiere rol de administrador (`@user_passes_test`)
- Protección CSRF en formularios
- Validación de permisos en cada acción

## 🐛 Solución de Problemas

### "Acceso denegado"
- Verifica que tu usuario tenga el grupo "administrador" o sea superusuario
- Crea un admin: `python manage.py crear_admin --username admin --email admin@example.com --password Admin123`

### "Template no encontrado"
- Verifica que ADMIN esté en INSTALLED_APPS
- Confirma que la ruta del template sea correcta

### "Los cambios no se guardan"
- Verifica que el formulario tenga `method="POST"`
- Confirma que hay CSRF token en el formulario
- Revisa los mensajes de error en la consola del navegador

## 📝 Próximas Mejoras

- [ ] Paginación de usuarios
- [ ] Filtros avanzados (por rol, estado, fecha de registro)
- [ ] Exportación a CSV/Excel
- [ ] Importación masiva de usuarios
- [ ] Log de cambios en usuarios
- [ ] Envío de emails de bienvenida
