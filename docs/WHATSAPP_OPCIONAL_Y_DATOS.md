# WhatsApp opcional y compatibilidad de datos

## Interruptor general

Configuración incluye «Habilitar WhatsApp», separado de la preferencia de envío automático. Se conserva habilitado por defecto en instalaciones existentes. Su valor se guarda con la clave `whatsapp_habilitado` en la tabla `configuracion`; este ajuste no requiere una nueva migración de esquema.

Al desactivar:

- Se bloquean los envíos manuales y automáticos tanto en las rutas como en el transporte de Python y el procesador de pendientes.
- Los pendientes pasan a «Cancelado». Los envíos que estaban en curso quedan marcados para verificar su entrega; los mensajes ya aceptados no se pueden retirar.
- Se apaga el servicio Node mediante un POST local autenticado. Se cierra su conexión sin ejecutar `logout` ni borrar credenciales o la caché de mensajes. El bot espera los cambios de credenciales que ya estuvieran guardándose y sale del proceso tras responder.
- Se retiran los accesos del dashboard, recordatorios, reenvíos, enlaces manuales, estado de envío y ventanas de confirmación del préstamo. El interruptor sigue disponible en Configuración.
- Los pagos y comprobantes PDF/PNG continúan funcionando.

Al activar, se inicia de nuevo el bot en segundo plano y se conserva la preferencia previa de envío automático. Los recibos cancelados no se reenvían solos. La sesión puede reutilizarse mientras siga siendo válida en WhatsApp; una revocación o caducidad puede requerir vincular el teléfono otra vez.

El launcher respeta la preferencia guardada. El runtime usa el Node incluido en el distribuible cuando está disponible y deja su registro en `whatsapp-bot.log` dentro de la carpeta de datos. En pruebas no se inician ni apagan procesos reales vinculados. Si un proceso no puede apagarse, la integración continúa bloqueada y se muestra un aviso.

## Archivo de datos del usuario final

La aplicación usa SQLite. Tener más clientes, préstamos o pagos no impide por sí mismo utilizar su archivo; la compatibilidad depende también del esquema y la integridad.

Sí hubo cambios de estructura en la revisión anterior: se añadieron los meses y datos inmutables del comprobante, el identificador de operación y el estado de envío en los pagos; la relación del producto con su préstamo de origen; el historial de ventas y la auditoría. Se mantienen las columnas y los datos originales.

El arranque reconoce el esquema original compatible, crea un respaldo y aplica la migración `ce_20261017_01`. La restauración prepara y migra una copia antes de sustituir la base de la instalación. Los esquemas desconocidos, incompletos o con referencias rotas se rechazan.

Antes de entregar a un usuario con una base más reciente o con más registros, comprobar una copia de su archivo y comparar cantidades e importes. No sustituir su archivo original por la base de desarrollo. Si hay archivos de imágenes asociados, conservarlos junto con los datos. Un `.sql` de texto es un volcado de instrucciones y necesita conversión a SQLite; la restauración actual espera una base SQLite, no ejecuta un SQL arbitrario.

## Validación

Las regresiones comprueban apagado y encendido, cancelación de pendientes, ausencia de reenvío al activar, rutas antiguas bloqueadas, permisos y CSRF, conservación de pagos y comprobantes, persistencia entre instancias, arranque con Node incluido y cancelación de un arranque todavía sin puerto. Las pruebas Node verifican el apagado autenticado, cierre del servicio y conservación de sesión y mensajes, con envíos simulados.

No se restauró la base del usuario ni se enviaron mensajes reales para estas comprobaciones. El archivo adicional mencionado no se ha facilitado; su compatibilidad concreta sigue pendiente de revisar sobre una copia.
