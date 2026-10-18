# Revisión general de Panda · 18 de octubre de 2026

Se revisaron el estado de Git, modelos, acceso, rutas administrativas, pagos, ventas, respaldos, migraciones, comprobantes, JavaScript, arranque y dependencias. La revisión conserva las reglas de negocio existentes y reúne los cambios funcionales y visuales descritos en los documentos del 17 de octubre.

## Correcciones de esta pasada

- Las redirecciones de respaldo, recibo inexistente, perfil y rechazo CSRF validan el destino. Conservan las rutas del mismo origen, incluyendo búsquedas, y rechazan sitios externos, puertos distintos, barras invertidas, caracteres de control y direcciones malformadas. Un destino inválido ya no provoca un error de análisis de URL.
- Los avisos de puesta en venta y cambio de estado completan el vocabulario «En venta» solicitado para la interfaz. Se mantienen los valores internos y las rutas existentes.
- Git excluye también `output/`, las variantes privadas de `.env` y `whatsapp-auth/`, usado al configurar una carpeta de datos. Se añade `.env.example` sin credenciales.
- README y documentos de revisión enlazan los archivos del repositorio mediante rutas relativas. Los comprobantes de muestra, capturas y ejecutables locales siguen fuera de Git.
- El lockfile del bot descarga `libsignal` por HTTPS, conservando exactamente su commit. La dirección SSH anterior podía pedir credenciales al instalar en otro equipo o en CI.

## Comprobaciones

- 217 pruebas Python aprobadas en la suite completa y 18 de redirecciones tras el último ajuste: 218 casos distintos comprobados.
- 13 pruebas Node aprobadas: autenticación de API, validación, escucha local, envío simulado y recuperación de mensajes.
- Instalación limpia del bot con `npm ci` en una carpeta temporal: 178 paquetes instalados, cero vulnerabilidades y las mismas 13 pruebas aprobadas.
- `pip check`: sin incompatibilidades. `npm audit`: cero vulnerabilidades reportadas por el registro al ejecutar la revisión.
- Sintaxis de los módulos JavaScript del bot y de apariencia, notificaciones y clientes verificada.
- Arranque `launcher.py --smoke-test` con carpeta de datos temporal: `SMOKE_TEST_OK`. Creación de esquema, compilación de plantillas y generación de comprobantes PDF/PNG correctas.
- Base operativa consultada mediante SQLite en modo de solo lectura: `quick_check` correcto, cero referencias rotas y esquema `ce_20261017_01`. No se restauró ni migró la base operativa durante esta revisión.
- Revisión de archivos candidatos al commit: sin bases, claves locales, sesiones de WhatsApp ni archivos de más de 10 MiB. La búsqueda de patrones de credenciales no encontró coincidencias.

Las pruebas de operaciones usan bases aisladas y datos ficticios. No se enviaron mensajes reales durante esta revisión.

## Publicación y límites

El remoto confirmado por el usuario es `https://github.com/Chucharizard/CasaDeEmpenho`. Sus ramas `master` y `main` tienen historiales separados del proyecto reconstruido. La revisión se prepara en `codex/revision-general-panda`, conservando las ramas publicadas y sin forzar su historial.

Esta publicación contiene código fuente y recursos. El ejecutable local generado el 17 de octubre precede a las últimas mejoras visuales y de recibos; no se ha recompilado en esta pasada. La comprobación de arranque corresponde al código fuente actual.

La revisión visual anterior está documentada por separado; esta pasada no incluye una nueva prueba interactiva del navegador. La entrega y visualización real de mensajes de WhatsApp en ambos teléfonos sigue requiriendo su comprobación durante el uso normal, como se describe en el informe de correcciones.
