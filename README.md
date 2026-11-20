# DESPERDICIO CERO

Aplicación local para gestionar alimentos disponibles, solicitudes de donación y entregas entre donantes y beneficiarios. Utiliza Flask y SQLite, con interfaz en español.

## Funcionalidades

- Registro e inicio de sesión con roles de donante y beneficiario; creación de administradores solo desde la base de datos.
- Gestión de publicaciones, filtros por texto/categoría/distrito y control de disponibilidad y vencimiento.
- Flujo de solicitud, aceptación/rechazo, entrega y confirmación de recepción.
- Alertas persistentes para alimentos próximos a vencer y solicitudes pendientes; se revisan cada seis horas y al abrir el centro de alertas.
- Panel según rol, directorio de usuarios para administración, indicadores y reportes Excel/PDF.
- API REST autenticada para alimentos, solicitudes y alertas.
- Sincronización de metadatos de conjuntos de datos desde el portal peruano de datos abiertos (CKAN).
- Interfaz institucional responsive, métricas calculadas desde SQLite y fotografías con alternativa gráfica local si falla la conexión.

Las cantidades permanecen asociadas a su unidad original. No se suman kilos, litros y unidades entre sí.

## Requisitos

- Windows 10/11
- Python 3.10 o posterior, disponible como `py` en la terminal
- Conexión a internet para instalar dependencias y sincronizar la fuente CKAN

## Inicio rápido

Haz doble clic en `iniciar-desperdicio-cero.bat`. El script crea `.venv` si falta, instala dependencias, prepara `.env` desde `.env.example` y abre el servidor local. Luego visita <http://127.0.0.1:5000>. Mantén abierta la ventana mientras uses el sistema; `Ctrl+C` detiene el servidor.

También puedes iniciarlo desde PowerShell:

```powershell
Set-Location "C:\Users\angel\Documents\VISUAL STUDIO\GESTION DE ALIMENTOS"
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python run.py
```

La base se crea en `instance/desperdicio_cero.db`. Conserva ese archivo para mantener tus datos. Para crear una cuenta de administración en una instalación local, ejecuta:

```powershell
python -c "from run import app; from app import db; from app.models import User; ctx=app.app_context(); ctx.push(); u=User(name='Administración',email='admin@local.test',role='administrador'); u.set_password('cambia-esta-clave'); db.session.add(u); db.session.commit()"
```

Usa un correo y contraseña propios y guarda la contraseña de forma segura. Para cargar datos ficticios marcados como demo: `python seed_demo.py`.

Puedes configurar los canales de contacto y redes opcionales en `.env` con `CONTACT_EMAIL`, `SOCIAL_INSTAGRAM_URL`, `SOCIAL_FACEBOOK_URL` y `SOCIAL_LINKEDIN_URL`. Si se dejan vacíos, no se muestran enlaces de contacto o redes.

## Fuentes de datos

La sincronización consultable en **Fuentes** usa la API CKAN pública de la [Plataforma Nacional de Datos Abiertos del Perú](https://www.datosabiertos.gob.pe/) y guarda metadatos deduplicados (nombre, organización, etiquetas y enlace). El portal ofrece recursos descargables por conjunto de datos; esta aplicación no descarga ni interpreta automáticamente cada CSV, por lo que sus resultados no se presentan como estadísticas procesadas.

El [Banco de Alimentos Perú](https://www.bancodealimentosperu.org/) publica información institucional y canales de contacto, pero no se identificó una API pública de datos de donaciones que permita sincronización automática. Por ello se deja como fuente/aliado informativo, sin extraer datos privados ni simular una conexión. La [API oficial de FAOSTAT](https://www.fao.org/faostat/en/docs/redoc-static.html) ofrece estadísticas agroalimentarias globales, pero sus dominios y dimensiones requieren consultas específicas; no se mezcla con el inventario operativo de la plataforma.

## API

- `GET /api/alimentos`, `GET /api/alimentos/<id>`
- `POST /api/alimentos`, `PUT /api/alimentos/<id>`, `DELETE /api/alimentos/<id>`
- `GET /api/solicitudes`, `POST /api/solicitudes`, `PUT /api/solicitudes/<id>/estado`
- `GET /api/alertas`, `PUT /api/alertas/<id>/leida`
- `GET /api/reportes/dashboard`
- `GET /api/fuentes`, `POST /api/fuentes/sincronizar` (administrador)

Las operaciones de escritura requieren sesión autenticada, rol permitido y token CSRF.
