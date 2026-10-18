"""
Rutas de administración para la integración con WhatsApp Bot.
Panel de escaneo de QR, estado de conexión, y envío manual de prueba.
"""
from flask import flash, jsonify, redirect, render_template, request, url_for
from flask_login import login_required
from app.utils import local_redirect_target

from app.routes.admin_shared import admin, admin_required
from app.services import whatsapp_service


def whatsapp_required(function):
    from functools import wraps
    @wraps(function)
    def wrapped(*args, **kwargs):
        if not whatsapp_service.esta_habilitado():
            if request.endpoint in {'admin.whatsapp_estado', 'admin.whatsapp_qr_data'}:
                return jsonify(whatsapp_service.deshabilitado()), 403
            flash('WhatsApp está deshabilitado. Puedes activarlo desde Configuración.', 'info')
            return redirect(url_for('admin.configuracion', _anchor='whatsapp'))
        return function(*args, **kwargs)
    return wrapped


@admin.route('/whatsapp')
@login_required
@admin_required
@whatsapp_required
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
@whatsapp_required
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
@whatsapp_required
def whatsapp_estado():
    """Endpoint AJAX para consultar el estado en tiempo real."""
    estado = whatsapp_service.obtener_estado()
    return jsonify(estado)


@admin.route('/whatsapp/qr-data')
@login_required
@admin_required
@whatsapp_required
def whatsapp_qr_data():
    """Endpoint AJAX para obtener el QR como Data URI."""
    data = whatsapp_service.obtener_qr_data()
    return jsonify(data)


@admin.route('/whatsapp/cerrar-sesion', methods=['POST'])
@login_required
@admin_required
@whatsapp_required
def whatsapp_cerrar_sesion():
    """Cierra la sesión de WhatsApp (desvincula el número)."""
    resultado = whatsapp_service.cerrar_sesion()
    if resultado.get('success'):
        flash('Sesión de WhatsApp cerrada exitosamente.', 'success')
    else:
        flash(f'Error al cerrar sesión: {resultado.get("error", "Desconocido")}', 'danger')
    return redirect(url_for('admin.whatsapp_panel'))


@admin.route('/whatsapp/reconectar', methods=['POST'])
@login_required
@admin_required
@whatsapp_required
def whatsapp_reconectar():
    result = whatsapp_service.reconectar()
    flash('Reconexión iniciada. Espera el nuevo QR.' if result.get('success') else 'No se pudo reconectar el bot.', 'info' if result.get('success') else 'warning')
    return redirect(url_for('admin.whatsapp_panel'))


@admin.route('/whatsapp/enviar-prueba', methods=['POST'])
@login_required
@admin_required
@whatsapp_required
def whatsapp_enviar_prueba():
    """Envía un mensaje de prueba al número indicado."""
    telefono = request.form.get('telefono', '').strip()
    if not telefono:
        flash('Ingresa un número de teléfono para la prueba.', 'warning')
        return redirect(url_for('admin.whatsapp_panel'))

    resultado = whatsapp_service.enviar_texto(
        telefono,
        '🧾 *Mensaje de Prueba - Panda | Casa de Empeño*\n\n'
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
@whatsapp_required
def whatsapp_reenviar_recibo(pago_id):
    """Reenvía el comprobante de pago por WhatsApp directamente a través del bot."""
    from app import db
    from app.models.prestamo import Pago

    pago = db.session.get(Pago, pago_id)
    if not pago or not pago.prestamo:
        flash('Pago no encontrado.', 'danger')
        return redirect(local_redirect_target(request.referrer, url_for('admin.dashboard'), origin=request.host_url))

    prestamo = pago.prestamo
    from app.services.delivery_service import send_receipt
    resultado = send_receipt(pago.id, force=True)
    if resultado.get('success'):
        flash('Comprobante de pago enviado directamente al WhatsApp del cliente.', 'success')
    else:
        flash(resultado.get('error', 'No se pudo enviar el comprobante.'), 'warning')
        if resultado.get('error_code') == 'disconnected':
            return redirect(url_for('admin.whatsapp_panel'))
    return redirect(url_for('admin.ver_prestamo', prestamo_id=prestamo.id))
