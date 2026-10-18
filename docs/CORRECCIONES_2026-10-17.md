# Correcciones y validación — 17 de octubre de 2026

Se corrigieron los doce hallazgos del análisis inicial y se incorporaron las mejoras de mantenimiento necesarias para utilizarlos sobre la base existente. Se mantiene el préstamo prendario a un mes calendario, la renovación desde el vencimiento anterior, la tasa guardada en cada préstamo, la venta de una unidad por operación y la posibilidad de recibir importes superiores al mínimo requerido.

## Resultado por hallazgo

| Hallazgo inicial | Corrección |
| --- | --- |
| Respaldo que omitía WAL | API de respaldo de SQLite, archivo temporal publicado solo al terminar y validación del esquema e integridad. |
| Restauración insegura | Verificación y migración de una copia, copia previa del estado actual y restauración mediante SQLite, coordinada con las peticiones y entregas. Invalida las sesiones anteriores. |
| Ventas parciales sin historial | Una fila por venta, con nombre, cantidad, fecha, precio y costo conservados. Los totales incluyen ventas parciales y no dependen de que se agote el stock. |
| Recibos que cambiaban | Datos del comprobante guardados con el pago y reutilizados en PDF, PNG y mensajes. |
| Bot expuesto sin autenticación | Escucha en loopback y clave compartida requerida en toda la API. Reconexión únicamente por POST autenticado. |
| Saldo descontado dos veces | El saldo exigible conserva el capital cuando el pago corresponde a intereses. |
| Meses impresos distintos de los renovados | Se guardan los meses aplicados. Un excedente se identifica como importe adicional y no inventa renovaciones. |
| Doble cobro por reintento | Identificador único por operación, comparación del contenido y devolución del comprobante original. Las ventas también reconocen reintentos. |
| Estados incompatibles | Liquidar libera las garantías; decomisar crea el producto vinculado y detiene intereses. Una garantía vendida no se puede reactivar ni liberar desde un cambio de estado. |
| Importes inválidos | Se rechazan NaN, infinitos, importes que redondean a cero, negativos y valores fuera del límite. |
| Tasa visual fija | Etiquetas, resúmenes y confirmaciones usan la tasa configurada. El máximo editable también proviene de configuración. |
| CI inconsistente | La misma normalización se aplica a búsquedas y escrituras, incluyendo reconocimiento de registros antiguos sin reescribir su identidad. |
| Pruebas con usuario heredado | Base y contexto independientes por prueba y contexto distinto por petición. Se comprueban administrador, cliente y anónimo sin compartir identidad. |

## Mejoras adicionales

- Se registra autor, fecha y valores anteriores y posteriores de ajustes de préstamos, clientes, stock y estados. Los cambios del préstamo aparecen en su línea de tiempo.
- Los envíos automáticos se guardan como pendientes antes de despacharlos. Su resultado queda visible en el historial. Los envíos interrumpidos requieren verificar la entrega antes de reintentarlos; no se reenvían a ciegas.
- La reserva de escritura de SQLite antes de leer saldo, correlativo o stock evita pérdidas de actualización entre dos instancias.
- Las peticiones normales pueden avanzar durante un envío lento de WhatsApp. La restauración espera a que terminen las operaciones activas y mantiene acceso exclusivo durante el reemplazo de datos.
- Los préstamos históricos rechazan fechas futuras. Los recordatorios de préstamos liquidados o decomisados ya no ofrecen renovaciones.
- El dashboard muestra 50 préstamos por página, carga pagos conjuntamente y conserva totales y gráfico del conjunto filtrado. Las respuestas antiguas de búsquedas se cancelan. El orden continúa funcionando después de actualizar la tabla.
- Los cambios manuales de estado se conservan como facultad administrativa y quedan registrados. Revertir un decomiso sin ventas retira su producto vinculado; si ya se vendió, se rechaza la reversión.
- Archivar productos con ventas conserva el historial. Los productos heredados con ventas sin detalle se distinguen de las operaciones nuevas y no se les inventan importes acumulados.
- Se añadieron migraciones versionadas, archivo de versiones de dependencias Python y comprobaciones automáticas para Windows/Linux y Node.js.
- El build genera una carpeta nueva, incluye los recursos de migración y el bot con su runtime, y excluye datos operativos y credenciales.
- Se comprobó la instalación vacía y la creación única del primer administrador. El acceso administrativo de la instalación actual se conserva.

## Migración aplicada

La revisión de esquema es `ce_20261017_01`, a partir de `f8a9b0c1d2e3`. Primero se migró una copia de la base operativa y se repitió la inicialización para comprobar que no duplicara datos. También se simuló un fallo de migración para verificar que se reviertan las modificaciones del esquema.

Después se migró la base operativa con respaldo previo en:

`pre_migracion_2026-10-17_10-03-28_979046.db`, en la carpeta de respaldos local

Se compararon huellas de todas las columnas originales de las seis tablas de negocio antes y después. Sus valores permanecieron idénticos:

| Registro | Cantidad conservada |
| --- | ---: |
| Usuarios | 899 |
| Préstamos | 1.166 |
| Pagos | 1.942 |
| Artículos | 1.166 |
| Productos | 0 |
| Configuraciones | 3 |

Los campos nuevos de comprobantes se completaron con la información conservada, identificando expresamente el carácter histórico. No se modificaron importes, estados, fechas originales, identidades ni contraseñas. La comparación de Alembic contra los modelos produjo cero diferencias de esquema.

La evidencia resumida está en [VALIDACION_MIGRACION_2026-10-17.json](VALIDACION_MIGRACION_2026-10-17.json).

## Validación

- 170 pruebas Python aprobadas, sin las advertencias originales de identidad de SQLAlchemy.
- 13 pruebas Node aprobadas: autenticación de API, escucha local, validación, envío simulado y recuperación de mensajes después de reconectar o reiniciar.
- `pip check` sin incompatibilidades y sintaxis Python/Node verificada.
- Regresiones de dos instancias concurrentes: dos pagos independientes avanzan dos meses; dos ventas simultáneas de la última unidad producen una sola venta.
- Concurrencia dentro de la instalación: un envío lento no bloquea el dashboard; el mantenimiento espera las operaciones activas y conserva la exclusividad.
- Navegador con datos ficticios: login, búsqueda, orden después de actualizar la tabla, paginación, resumen al 15%, renovación y ventas parciales.
- Renovación ficticia: capital Bs. 1.000, interés Bs. 150, saldo posterior Bs. 1.000.
- Dos ventas ficticias de Bs. 120 y Bs. 150, costo unitario Bs. 80: total Bs. 270 y ganancia Bs. 110, con ambas operaciones en el historial.
- Ejecutable de consola compilado y comprobado con `--smoke-test`: creación del esquema, carga de plantillas y generación de PNG/PDF correctas.
- Ejecutable final sin consola compilado y comprobado: `--smoke-test` correcto; Node incluido carga Baileys y la API local. Se verificó que el distribuible no incluya la base operativa ni claves locales.

Distribuible comprobado: `dist/20261017-130031-384/CasaEmpeno/CasaEmpeno.exe` (archivo local, excluido de Git). Es una instalación nueva sin datos de clientes; para operar sobre los datos del proyecto, utilizar el launcher habitual o configurar su carpeta de datos.

Capturas de la comprobación con datos ficticios:

`build/qa-cobro.png` (captura local, excluida de Git).

`build/qa-ventas.png` (captura local, excluida de Git).

## Límites de los datos históricos

Los pagos anteriores no guardaban los meses renovados ni el vencimiento resultante de cada operación. Se conservan sus importes y fechas, pero los comprobantes históricos indican que el plazo original no está registrado. Las operaciones nuevas conservan esos datos de forma inmutable. No es posible recuperar precios de ventas que la versión anterior sobrescribió; la base actual no tenía productos al aplicar la migración.

WhatsApp se validó mediante simulaciones y carga de sus dependencias; no se enviaron mensajes reales ni se alteró la sesión vinculada del usuario. El comportamiento con una cuenta real debe comprobarse al utilizar el bot en la operación habitual.

## Incidencia de WhatsApp: «Esperando el mensaje»

El usuario observó este aviso tanto en el teléfono vinculado como en el destinatario. Se confirmó que el bot estaba conectado y que la aplicación había registrado el envío como aceptado. Ese resultado no confirma que los teléfonos hayan podido descifrarlo.

Se encontró que el socket no proporcionaba `getMessage`. En Baileys 6.7.24, el valor por defecto devuelve `undefined`, lo que impide recuperar el contenido cuando WhatsApp pide repetir un mensaje por problemas de cifrado. Es un fallo confirmado del código; los registros anteriores no permiten descartar problemas adicionales de claves o sincronización.

Se añadió una caché local de mensajes salientes, conservando el contenido protobuf y las claves de la imagen para que el protocolo recupere el mismo identificador. Se mantiene entre reconexiones y reinicios, limita su tamaño a 8 MiB y 512 mensajes, y solo permite recuperar mensajes de los últimos siete días. Se almacena junto a la sesión del bot y no se incluye en el distribuible. Los fallos de disco no convierten un mensaje ya enviado en un error de envío desde la aplicación.

Siete pruebas nuevas verifican texto e imagen, conservación tras reiniciar, caducidad y límites, mensajes desconocidos, exclusión de mensajes recibidos y fallos de disco o caché dañada. Se actualizó el bot del distribuible y se reinició únicamente el proceso local de WhatsApp. Volvió a estado `connected` sin solicitar QR; la web siguió respondiendo correctamente. No se reenviaron mensajes reales durante esta comprobación.

Los mensajes enviados antes de esta corrección no están en la caché nueva. Si siguen bloqueados, se debe reenviar el comprobante del pago existente, sin registrar otro pago. La entrega y visualización real requieren comprobarse en ambos teléfonos.
