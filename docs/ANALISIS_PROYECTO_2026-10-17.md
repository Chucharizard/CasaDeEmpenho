# Revisión del proyecto Casa de Empeño

Fecha: 17 de octubre de 2026. Revisión sobre el commit `744e82c`.

Este documento conserva el diagnóstico inicial. Las correcciones posteriores y su validación están en [CORRECCIONES_2026-10-17.md](CORRECCIONES_2026-10-17.md).

## Alcance y resultado

Se revisaron modelos, rutas, plantillas, pruebas, configuración, arranque, generación de documentos y bot de WhatsApp. Se ejecutaron las pruebas existentes y reproducciones adicionales con SQLite en memoria o archivos temporales y datos ficticios. La base operativa se consultó en modo de solo lectura. No se ejecutaron respaldos ni restauraciones sobre ella, no se inició el bot y no se enviaron mensajes.

La aplicación tiene una base aprovechable: módulos separados por función, controles de administrador, contraseñas con hash, protección CSRF en ejecución normal, claves persistentes fuera de Git, recursos visuales locales y una suite de pruebas. Conviene corregir problemas de consistencia y conservación de información antes de incorporar más funciones o rediseñar la interfaz.

Esta revisión no modifica el código de la aplicación ni sus datos. El único archivo añadido al repositorio es este informe.

## Regla de negocio tomada como referencia

- Un préstamo prendario entrega capital a un cliente y registra una garantía. Puede registrarse con fecha actual o anterior.
- El plazo inicial es un mes calendario. La tasa proviene de configuración y se conserva en el préstamo.
- El pago de intereses renueva el vencimiento desde su fecha anterior por los meses elegidos.
- El cálculo vigente de intereses pendientes depende del vencimiento y de los pagos previos. No se propone sustituirlo por amortización ni interés compuesto.
- La liquidación exige cubrir el importe calculado y finaliza el préstamo. Las rutas aceptan importes superiores al mínimo exigido.
- Los estados disponibles son activo, retención, finalizado y decomisado.
- El decomiso a inventario crea un producto con una unidad y utiliza el capital prestado como costo de compra.
- El inventario permite compras, publicación para venta y ventas de una unidad por operación.
- Los comprobantes pueden descargarse y enviarse por WhatsApp, con envío automático o confirmación previa.

Las recomendaciones siguientes buscan que pantallas, registros y comprobantes representen esas operaciones de forma coherente. Las decisiones sobre excepciones administrativas y excedentes se distinguen de los errores técnicos.

## Comprobaciones realizadas

| Comprobación | Resultado |
| --- | --- |
| Suite existente | 129 pruebas aprobadas; 88 advertencias; 53,96 segundos |
| Dependencias Python instaladas, `pip check` | Sin requisitos incompatibles detectados |
| Sintaxis del bot, `node --check` | Correcta |
| SQLite operativa, `PRAGMA quick_check` | `ok` |
| SQLite operativa, `PRAGMA foreign_key_check` | Sin referencias rotas |
| Volumen actual | 899 usuarios, 1.166 préstamos, 1.942 pagos y 1.166 artículos |
| Estados de los préstamos actuales | 1.024 finalizados y 142 en retención |
| Inventario actual | 0 productos; el defecto de ventas se reprodujo con datos ficticios |
| Artículos de préstamos finalizados aún marcados como empeñados en la base actual | 0; la ruta actual sí produce esa inconsistencia en registros nuevos |

Estos resultados no equivalen a una conciliación contable completa, una auditoría de vulnerabilidades de dependencias o una validación visual en navegador. Tampoco se construyó ni ejecutó el paquete distribuible.

## Hallazgos prioritarios

P1 indica alta prioridad por pérdida de información, documentos inconsistentes o exposición de operaciones. P2 indica un defecto que conviene resolver en el siguiente bloque de mantenimiento. Las prioridades expresan impacto del código; no afirman que todos los escenarios ya hayan ocurrido en los datos actuales.

### 1. P1 — El respaldo puede omitir operaciones ya confirmadas

La conexión SQLite activa WAL, pero el respaldo usa `shutil.copyfile` únicamente sobre el archivo `.db`. Una operación confirmada puede seguir en el archivo WAL y quedar fuera de la copia.

**Reproducción:** con WAL activo y una inserción confirmada después de un checkpoint, el origen tenía una fila y el respaldo obtenido por el mismo procedimiento tenía cero. El experimento utilizó archivos temporales.

La copia previa a restaurar usa el mismo mecanismo. La restauración tampoco verifica que el archivo elegido sea una base íntegra y compatible antes de reemplazar la actual. Además, estas rutas usan `Config.SQLITE_DB_PATH` directamente, aunque la aplicación se haya creado con otra URI de base de datos.

**Corrección propuesta:** usar la API de respaldo de SQLite; comprobar integridad y esquema del archivo antes de restaurarlo; coordinar la restauración con las conexiones abiertas; obtener las rutas de la configuración efectiva de la aplicación. Verificar una restauración completa sobre una copia antes de trabajar con datos reales.

Referencias: [WAL](../app/__init__.py), [respaldo](../app/routes/admin_config.py), [restauración](../app/routes/admin_config.py).

### 2. P1 — Las ventas de varias unidades pierden su historial e importes

Cada venta decrementa stock y sobrescribe `producto.precio` y `fecha_venta`. No crea un registro independiente de venta. Los totales consideran solo productos cuyo stock llegó a cero y suman un precio por producto.

**Reproducción:** producto con dos unidades, costo unitario de Bs. 80. Primera venta a Bs. 120: el resumen mostró Bs. 0 vendidos. Segunda venta a Bs. 150: mostró Bs. 150 vendidos y Bs. 70 de ganancia. Las operaciones sumaban Bs. 270 y la ganancia era Bs. 110.

**Corrección propuesta:** registrar cada venta con cantidad, precio y costo aplicados, fecha y producto; calcular los resúmenes desde esas operaciones. Mantener el stock como existencia. No reconstruir importes históricos suponiendo que todas las unidades se vendieron al último precio conocido.

Referencias: [venta](../app/routes/admin_inventory.py), [resumen](../app/routes/admin_inventory.py). El resumen de configuración repite este cálculo.

### 3. P1 — Un comprobante antiguo cambia después de nuevas operaciones

Para reimprimir un pago se toman el vencimiento, capital, tasa y datos del cliente del estado actual del préstamo. Los meses pagados se deducen dividiendo el importe histórico entre la cuota actual.

**Reproducción:** el mismo pago `REC-00001` se preparó inicialmente con vencimiento 17/12/2026. Después de otra renovación, reimprimir ese pago lo preparó con vencimiento 17/01/2027. La captura se realizó sobre los datos enviados al generador, sin modificar documentos reales.

**Corrección propuesta:** guardar con el pago los meses efectivamente aplicados y el vencimiento resultante, junto con los datos necesarios para reproducir el comprobante emitido. PDF, imagen y WhatsApp deben usar esa información histórica. Para pagos antiguos sin esos campos, indicar la limitación o recuperar evidencia existente; no inventar valores exactos.

Referencias: [datos para PDF](../app/routes/admin_loans.py), [vencimiento utilizado](../app/routes/admin_loans.py), [reenvío](../app/routes/admin_whatsapp.py).

### 4. P1 — La API del bot permite operaciones sin autenticación y no limita la escucha a localhost

El servidor registra envío de texto, envío de imágenes, QR, reconexión y cierre de sesión sin un control de autenticación. `app.listen(PORT, callback)` no especifica una dirección local. Se verificaron las rutas y parámetros de escucha ejecutando el módulo con dependencias simuladas; el valor predeterminado de escucha del Node instalado se comprobó con un servidor efímero y fue `::`.

**Impacto:** si el servicio está iniciado y el firewall permite conexiones desde la red, sus operaciones pueden invocarse sin pasar por el login de Flask. La autenticación de las rutas Flask no protege el puerto 3001.

En la comprobación local no se observó un listener activo en el puerto 3001. No se probó acceso remoto ni se enviaron mensajes.

**Corrección propuesta:** escuchar explícitamente en `127.0.0.1`, configurar el mismo destino en Python y exigir un secreto compartido para las llamadas al bot. Convertir reconexión en una operación POST autenticada.

Referencias: [middleware actual](../whatsapp-bot/server.js), [envío](../whatsapp-bot/server.js), [escucha](../whatsapp-bot/server.js).

### 5. P2 — El saldo mostrado descuenta otra vez los intereses pagados

`monto_liquidacion_actual` ya contempla los intereses que siguen pendientes. `monto_pendiente_estimado` le resta además todos los pagos anteriores, incluidos los de interés. La pantalla muestra ambos resultados.

**Reproducción:** préstamo de Bs. 1.000 al 10%; pagar Bs. 100 de interés deja la liquidación en Bs. 1.000 y el saldo mostrado en Bs. 900. El pago de intereses no amortizó capital.

La ruta de liquidación exige el importe de `monto_liquidacion_actual`; no se observó que este defecto de presentación permitiera liquidar por Bs. 900.

**Corrección propuesta:** definir una única fuente para el saldo exigible conforme a la lógica vigente y distinguir los intereses históricos cobrados del capital pendiente. La prueba actual solo comprueba que el saldo disminuya; necesita un resultado exacto para este caso.

Referencias: [saldo](../app/models/prestamo.py), [presentación](../app/templates/admin/ver_prestamo.html), [prueba actual](../tests/test_modelos.py).

### 6. P2 — Importe recibido y meses renovados pueden contradecir el comprobante

La renovación usa los meses elegidos en el formulario, mientras el recibo los calcula a partir del importe recibido. La ruta acepta importes superiores al interés requerido.

**Reproducción:** cuota de Bs. 100; ingresar Bs. 200 eligiendo un mes extiende el vencimiento un mes, pero el comprobante informa dos.

**Corrección propuesta:** persistir los meses aplicados y utilizarlos en todos los comprobantes. Mantener explícita la aceptación actual de excedentes; definir cómo representarlos sin deducir automáticamente una renovación que no ocurrió.

Referencias: [meses aplicados](../app/routes/admin_loans.py), [extensión](../app/routes/admin_loans.py), [meses impresos](../app/routes/admin_loans.py).

### 7. P2 — Reenviar un formulario de interés registra otro cobro

No existe un identificador de operación que permita reconocer el reintento de una solicitud ya procesada.

**Reproducción:** enviar dos veces el mismo formulario de Bs. 100 por un mes produjo dos pagos y dos meses de extensión. Una repetición por doble clic o reintento puede representar un solo cobro físico.

**Corrección propuesta:** asignar un identificador único a cada operación y validar su unicidad en la transacción. Deshabilitar el botón durante el envío ayuda, pero el servidor también debe reconocer los reintentos. Dos pagos intencionales deben seguir siendo posibles mediante dos operaciones diferentes.

Referencia: [registro de pagos](../app/routes/admin_loans.py).

### 8. P2 — Préstamo, garantía e inventario pueden quedar en estados incompatibles

La liquidación cambia el préstamo a finalizado, pero no actualiza el artículo. El cambio manual a decomisado tampoco actualiza la garantía ni crea un producto. La alerta indica que pasó al inventario, aunque esa transición manual no lo hace. Además, el cálculo de intereses excluye finalizados, pero continúa para decomisados, contrario al texto del modal.

**Reproducciones:** liquidación total dejó la garantía como `empenado`; cambio manual a decomisado dejó cero productos y la garantía empeñada; un préstamo decomisado de Bs. 1.000 al 10% siguió calculando Bs. 400 de intereses al avanzar la fecha simulada.

**Corrección propuesta:** concentrar cada transición y sus efectos en una operación consistente. Si los cambios manuales son una excepción necesaria del negocio, conservarlos con motivo e historial y mostrar sus efectos reales. No eliminar esa facultad administrativa sin definir su uso.

Referencias: [liquidación](../app/routes/admin_loans.py), [cambio manual](../app/routes/admin_loans.py), [intereses](../app/models/prestamo.py), [texto del modal](../app/templates/admin/ver_prestamo.html).

### 9. P2 — La validación monetaria acepta infinito, NaN y valores que terminan en cero

El validador comprueba positividad antes de redondear y no comprueba que el número sea finito.

**Reproducción:** `inf` y `nan` pasan el validador; `0.001` se devuelve como `0.0`. Un POST de liquidación con `monto=inf` finalizó el préstamo y persistió infinito como monto pagado. Esto se probó directamente contra la ruta con datos ficticios; el navegador puede impedir algunas entradas, pero no sustituye la validación del servidor.

**Corrección propuesta:** rechazar números no finitos, validar el mínimo después de cuantizar y fijar límites razonables. Evaluar centavos enteros o Decimal de forma gradual, con pruebas que conserven los redondeos acordados.

Referencia: [validador](../app/routes/admin_shared.py).

### 10. P2 — La pantalla anuncia siempre 10%, aunque la configuración cambie

Ambos formularios de préstamo y sus confirmaciones tienen tasas y multiplicadores fijos del 10%. El servidor utiliza la tasa configurada.

**Reproducción:** configurar 15% mantuvo `INTERES_MENSUAL = 10` y el rótulo de 10% en el formulario; el préstamo creado sí guardó 15%. Para Bs. 1.000, el resumen promete Bs. 1.100 y la liquidación inicial corresponde a Bs. 1.150.

**Corrección propuesta:** pasar la tasa efectiva desde el servidor a etiquetas, cálculos y confirmaciones. El formulario de edición también tiene un máximo HTML fijo de 25%, aunque el límite sea configurable.

Referencias: [nuevo préstamo](../app/templates/admin/nuevo_prestamo.html), [confirmación](../app/templates/admin/nuevo_prestamo.html), [préstamo anterior](../app/templates/admin/prestamo_anterior.html).

### 11. P2 — La normalización del CI no se aplica en las búsquedas

El modelo guarda CI en mayúsculas, pero login, activación y búsquedas consultan el texto sin normalizarlo igual.

**Reproducción:** un usuario guardado como `ABC123` no se encontró con `abc123` y no pudo iniciar sesión con esa variante. En la creación de otro préstamo puede intentarse insertar un cliente que ya existe y fallar por unicidad al convertir el CI a mayúsculas.

**Corrección propuesta:** compartir la misma normalización al consultar y al guardar. No cambiar el formato de negocio del CI.

Referencias: [modelo](../app/models/usuario.py), [login](../app/routes/auth.py), [cliente de préstamo](../app/routes/admin_loans.py).

### 12. P2 — El contexto compartido de las pruebas puede conservar un usuario autenticado

El fixture mantiene un contexto de aplicación abierto durante toda la sesión. La limpieza elimina filas, pero no crea un contexto nuevo para cada petición ni elimina la caché de usuario de Flask-Login.

**Reproducción con el mismo patrón del fixture:** una petición autenticada al dashboard devolvió 200; un cliente nuevo, sin cookie de sesión, también obtuvo 200 dentro de ese contexto compartido. Al limpiar la caché `_login_user`, el cliente anónimo volvió a recibir el 302 esperado.

Este resultado corresponde al entorno de pruebas: no demuestra un bypass de autenticación en la aplicación ejecutada normalmente. Sí reduce la confianza en las pruebas de permisos. Las advertencias de identidad de SQLAlchemy también son consistentes con un aislamiento insuficiente de sesión.

**Corrección propuesta:** aislar contextos y sesiones entre pruebas y peticiones. Añadir comprobaciones de administrador, usuario normal y anónimo dentro de una misma prueba. Ejecutar pruebas específicas con CSRF activo, pues `TESTING=True` lo omite.

Referencias: [contexto de sesión](../tests/conftest.py), [limpieza](../tests/conftest.py), [CSRF en pruebas](../app/__init__.py).

## Mejoras posteriores y puntos de alcance

- **Rendimiento:** el dashboard carga todos los resultados y puede consultar pagos por cada préstamo vigente. Con 31 préstamos ficticios se midieron 35 SELECT, 31 de ellos a pagos. Añadir paginación y carga conjunta o agregación de pagos conservando los totales globales. No se midió la latencia de la base operativa.
- **Historial administrativo:** registrar quién modificó capital, tasa, vencimiento, estado o stock, con valores previos y motivo. Actualmente editar un registro también altera los datos con los que se reconstruye su historia.
- **Entrega de WhatsApp:** guardar estados pendiente/enviado/fallido y permitir reintentos identificables. El envío automático usa un hilo daemon y registra fallos en logs; cerrar la aplicación o perder conexión puede dejar un pago confirmado sin comprobante enviado.
- **Código de comprobantes:** concentrar la preparación de datos del recibo, hoy repetida en PDF, PNG, envío automático y reenvío manual. Hacerlo después de definir los datos históricos que debe conservar cada pago.
- **Migraciones y distribución:** Flask-Migrate está instalado y la base contiene `alembic_version`, pero no hay un directorio de migraciones versionado en el repositorio. `create_all()` no actualiza tablas existentes. Los scripts de build incluyen la base operativa y no empaquetan el bot; el launcher espera una carpeta externa y Node instalado. Preparar un proceso de actualización que conserve datos y una prueba de instalación en una carpeta limpia. El resultado del ejecutable no se validó en esta revisión.
- **Acceso de clientes:** hay activación y actualización de perfil, pero un usuario normal que inicia sesión es redirigido al dashboard administrativo y después al login. El panel existente requiere administrador. Si la aplicación es exclusivamente administrativa, puede ser funcionalidad residual; no se recomienda crear un portal sin que forme parte del alcance del negocio.
- **Calidad continua:** incorporar una comprobación automática que ejecute las pruebas corregidas. `pip check` solo confirma compatibilidad declarada de paquetes instalados: no reemplaza una auditoría de vulnerabilidades ni una instalación reproducible.

## Orden de trabajo recomendado

1. **Conservar y verificar la información:** corregir respaldo/restauración y aislamiento de pruebas. Aceptación: una escritura pendiente en WAL aparece en el respaldo y un archivo inválido nunca reemplaza la base.
2. **Asegurar los cobros y documentos:** unificar saldo, persistir meses y vencimiento del pago, bloquear reintentos y validar importes. Aceptación: un recibo conserva sus datos después de nuevas renovaciones y un reintento no duplica cobros.
3. **Sincronizar estados y tasas:** actualizar garantías con las transiciones, definir las excepciones manuales y mostrar la tasa configurada. Aceptación: pantalla, estado y cálculo coinciden en cada transición permitida.
4. **Registrar ventas completas y proteger el bot:** movimientos independientes de venta, resúmenes conciliables y API local autenticada. Si se utiliza WhatsApp en red, adelantar su protección al primer bloque. Resolver el historial de ventas antes de comenzar a operar inventario con varias unidades.
5. **Preparar mantenimiento:** migraciones, instalación, paginación, historial administrativo y seguimiento de envíos.

La estructura actual permite introducir estas mejoras por etapas. Cada etapa debe conservar los cálculos y flujos de negocio aceptados, salvo las contradicciones documentadas, y demostrar con ejemplos exactos qué comportamiento corrige.
