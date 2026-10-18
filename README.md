# Panda · Casa de Empeño

Aplicación local de gestión de préstamos prendarios, garantías, inventario y comprobantes. El punto de entrada es `launcher.py`.

## Ejecutar el proyecto

En PowerShell, desde la carpeta del proyecto:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
npm ci --prefix whatsapp-bot
.\.venv\Scripts\python.exe launcher.py
```

Entorno comprobado: Python 3.14 y Node.js 24. El launcher inicia el servicio local de WhatsApp y abre la aplicación. El acceso principal es administrativo. Una instalación nueva permite crear su primer administrador desde el formulario de acceso, únicamente en el equipo local; esa opción se cierra al existir un administrador.

La base actual del proyecto ya está migrada. En futuras actualizaciones, el arranque verifica el esquema y guarda un respaldo antes de aplicar una migración pendiente. Una base con versión desconocida se rechaza sin intentar transformarla.

## Datos y configuración

- Por defecto, base de datos, archivos subidos y claves locales se conservan junto al proyecto o ejecutable.
- `CASAEMPENO_DATA_DIR` permite elegir una carpeta de datos distinta. Mantenerla entre versiones conserva las claves, sesiones de la instalación y base de datos.
- La configuración opcional se lee del archivo `.env` junto al proyecto o ejecutable.
- `.env.example` contiene un ejemplo sin credenciales. Las bases, claves, sesiones de WhatsApp, archivos subidos y comprobantes generados están excluidos de Git.
- Los respaldos usan la ubicación configurada en `BACKUP_DIR`; si no se especifica, se conserva la ubicación habitual de Respaldo en OneDrive o `RespaldoCasaEmpeno`.
- La API del bot escucha únicamente en `127.0.0.1:3001` y comparte una clave local con Python. Las claves y la sesión vinculada de WhatsApp no forman parte del repositorio ni del distribuible.
- En Configuración, «Habilitar WhatsApp» apaga o inicia el bot y oculta sus acciones. Al desactivarlo se cancelan los envíos pendientes y se conserva la sesión. La preferencia de envío automático se mantiene por separado. Ver [WhatsApp opcional y datos](docs/WHATSAPP_OPCIONAL_Y_DATOS.md).
- `CLIENT_ACCESS_ENABLED` permanece desactivado en la instalación administrativa. Esto no impide gestionar clientes y sus préstamos desde administración.

Para restaurar, seleccionar un respaldo en Configuración y confirmar con la contraseña del administrador. El archivo se verifica y migra en una copia antes de restaurarlo. Se guarda una copia del estado anterior y se cierran las sesiones existentes; después de restaurar se inicia sesión con las credenciales conservadas en ese respaldo.

## Pruebas

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest
npm test --prefix whatsapp-bot
```

Las pruebas usan bases aisladas y envíos simulados. Incluyen respaldos con WAL, restauración, rollback de migraciones, pagos y ventas concurrentes entre dos instancias, recibos históricos y permisos con CSRF activo.

## Distribuir y actualizar

```powershell
.\build_exe_sin_consola.ps1
```

Cada build crea una carpeta nueva bajo `dist`, con el ejecutable, migraciones, recursos y el bot con Node.js y sus dependencias. No borra instalaciones anteriores ni incluye la base operativa. Conservar la carpeta completa del distribuible, no solo el `.exe`.

Para una instalación existente, mantener su carpeta de datos mediante `CASAEMPENO_DATA_DIR` o utilizar el respaldo y la restauración de la aplicación. En un equipo nuevo se crea una base vacía; los datos de clientes no se distribuyen dentro del programa.

El ejecutable admite `--smoke-test` para comprobar esquema, plantillas y generación de PDF/PNG sin abrir el navegador ni iniciar WhatsApp. Para esa comprobación se debe elegir una carpeta de datos temporal con `CASAEMPENO_DATA_DIR` y una carpeta de respaldo temporal con `BACKUP_DIR`. En la versión sin consola, el resultado queda en `casa_empeno.log` dentro de la carpeta de datos.

Las correcciones de integridad están en [CORRECCIONES_2026-10-17.md](docs/CORRECCIONES_2026-10-17.md), las mejoras visuales en [DISENO_2026-10-17.md](docs/DISENO_2026-10-17.md) y la revisión general en [REVISION_GENERAL_2026-10-18.md](docs/REVISION_GENERAL_2026-10-18.md).
