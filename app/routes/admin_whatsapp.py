"""
Rutas de administración para la integración con WhatsApp Bot.
Panel de escaneo de QR, estado de conexión, y envío manual de prueba.
"""
from flask import flash, jsonify, redirect, render_template, request, url_for
from flask_login import login_required

from app.routes.admin_shared import admin, admin_required
from app.services import whatsapp_service


@admin.route('/whatsapp')
@login_required
@admin_required
def whatsapp_panel():
    """Panel principal de WhatsApp: estado y QR."""
    from app.models import Configuracion
    estado = whatsapp_service.obtener_estado()
    whatsapp_auto_envio = Configuracion.get_valor('whatsapp_auto_envio', 'true') == 'true'
    return render_template(
        'admin/whatsapp_panel.html',
        estado=estado,
        whatsapp_auto_envio=whatsapp_auto_envio,
    )


@admin.route('/whatsapp/toggle-auto', methods=['POST'])
@login_required
@admin_required
def whatsapp_toggle_auto():
    """Habilita o deshabilita el envío 100% automático desde el panel de WhatsApp."""
    from app.models import Configuracion
    auto_envio = 'true' if request.form.get('whatsapp_auto_envio') == 'on' else 'false'
    Configuracion.set_valor('whatsapp_auto_envio', auto_envio)
    if auto_envio == 'true':
        flash('Modo de WhatsApp: Envío 100% automático activado al registrar pagos.', 'success')
    else:
        flash('Modo de WhatsApp: Confirmación manual activada (se preguntará con ventana emergente al cobrar).', 'info')
    return redirect(url_for('admin.whatsapp_panel'))


@admin.route('/whatsapp/estado')
@login_required
@admin_required
def whatsapp_estado():
    """Endpoint AJAX para consultar el estado en tiempo real."""
    estado = whatsapp_service.obtener_estado()
    return jsonify(estado)


@admin.route('/whatsapp/qr-data')
@login_required
@admin_required
def whatsapp_qr_data():
    """Endpoint AJAX para obtener el QR como Data URI."""
    data = whatsapp_service.obtener_qr_data()
    return jsonify(data)


@admin.route('/whatsapp/cerrar-sesion', methods=['POST'])
@login_required
@admin_required
def whatsapp_cerrar_sesion():
    """Cierra la sesión de WhatsApp (desvincula el número)."""
    resultado = whatsapp_service.cerrar_sesion()
    if resultado.get('success'):
        flash('Sesión de WhatsApp cerrada exitosamente.', 'success')
    else:
        flash(f'Error al cerrar sesión: {resultado.get("error", "Desconocido")}', 'danger')
    return redirect(url_for('admin.whatsapp_panel'))


@admin.route('/whatsapp/enviar-prueba', methods=['POST'])
@login_required
@admin_required
def whatsapp_enviar_prueba():
    """Envía un mensaje de prueba al número indicado."""
    telefono = request.form.get('telefono', '').strip()
    if not telefono:
        flash('Ingresa un número de teléfono para la prueba.', 'warning')
        return redirect(url_for('admin.whatsapp_panel'))

    resultado = whatsapp_service.enviar_texto(
        telefono,
        '🧾 *Mensaje de Prueba - Casa de Empeño*\n\n'
        '¡Hola! Este es un mensaje de prueba para verificar que el sistema de envío '
        'automático de recibos por WhatsApp está funcionando correctamente.\n\n'
        '✅ Si recibes este mensaje, el sistema está operativo.'
    )

    if resultado.get('success'):
        flash(f'✅ Mensaje de prueba enviado a +{telefono} exitosamente.', 'success')
    else:
        flash(f'❌ Error al enviar: {resultado.get("error", "Desconocido")}', 'danger')

    return redirect(url_for('admin.whatsapp_panel'))


@admin.route('/whatsapp/reenviar-recibo/<int:pago_id>', methods=['POST'])
@login_required
@admin_required
def whatsapp_reenviar_recibo(pago_id):
    """Reenvía el comprobante de pago por WhatsApp directamente a través del bot."""
    from app import db
    from app.models.prestamo import Pago
    from app.services.pdf_service import generar_comprobante_imagen

    pago = db.session.get(Pago, pago_id)
    if not pago or not pago.prestamo:
        flash('Pago no encontrado.', 'danger')
        return redirect(request.referrer or url_for('admin.dashboard'))

    prestamo = pago.prestamo
    telefono = prestamo.telefono_whatsapp
    if not telefono:
        flash('El cliente no tiene un número de celular registrado.', 'warning')
        return redirect(request.referrer or url_for('admin.ver_prestamo', prestamo_id=prestamo.id))

    if not whatsapp_service.esta_conectado():
        flash('El bot de WhatsApp no está conectado. Escanea el código QR primero.', 'warning')
        return redirect(url_for('admin.whatsapp_panel'))

    # Generar la imagen del recibo
    usuario = prestamo.usuario
    articulos_desc = ", ".join(a.nombre for a in prestamo.articulos) if prestamo.articulos else 'Garantía prendaria'
    meses_pagados = 1
    if pago.tipo_pago == 'interes' and prestamo.interes_un_mes > 0:
        meses_pagados = max(1, int(round(pago.monto_pagado / prestamo.interes_un_mes)))

    img_buffer = generar_comprobante_imagen({
        'numero_recibo': f"REC-{pago.id:05d}",
        'fecha_pago': pago.fecha_pago,
        'numero_documento': prestamo.numero_documento,
        'numero_prestamo': prestamo.numero_prestamo,
        'nombre_cliente': usuario.nombre if usuario else 'N/A',
        'ci_cliente': usuario.ci if usuario else 'N/A',
        'telefono_cliente': usuario.telefono if (usuario and usuario.telefono) else 'No registrado',
        'articulos_descripcion': articulos_desc,
        'tipo_pago': pago.tipo_pago,
        'meses_pagados': meses_pagados,
        'monto_pagado': pago.monto_pagado,
        'monto_prestado': prestamo.monto_prestado,
        'fecha_vencimiento': prestamo.fecha_finalizacion,
    })

    if not img_buffer:
        flash('Error al generar la imagen del recibo.', 'danger')
        return redirect(request.referrer or url_for('admin.ver_prestamo', prestamo_id=prestamo.id))

    tipo_label = 'Pago Total (Liquidación)' if pago.tipo_pago == 'total' else 'Pago de Interés'
    caption = f'🧾 Comprobante de {tipo_label} - Casa de Empeño'

    resultado = whatsapp_service.enviar_imagen(telefono, img_buffer.getvalue(), caption)
    if resultado.get('success'):
        flash(f'✅ Comprobante de pago enviado directamente al WhatsApp del cliente (+{telefono}).', 'success')
    else:
        flash(f'❌ Error al enviar por WhatsApp: {resultado.get("error", "Desconocido")}', 'danger')

    return redirect(request.referrer or url_for('admin.ver_prestamo', prestamo_id=prestamo.id))

