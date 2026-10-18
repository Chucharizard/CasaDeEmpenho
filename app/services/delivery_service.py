"""Entrega persistente de recibos; los fallos requieren un reintento explícito."""
import logging
import threading
from datetime import timedelta

from flask import current_app

from app import db
from app.models import Pago
from app.services import pdf_service, whatsapp_service
from app.services.receipt_service import build_receipt_data
from app.utils import get_bolivia_time

logger = logging.getLogger(__name__)


def send_receipt(pago_id, force=False):
    with current_app.extensions['database_lock']:
        pago = db.session.get(Pago, pago_id)
        if not pago:
            return {'success': False, 'error': 'Pago no encontrado.'}
        if pago.whatsapp_estado == 'enviando':
            return {'success': False, 'error': 'El envío de este recibo está en curso.'}
        if pago.whatsapp_estado == 'enviado' and not force:
            return {'success': True, 'message': 'El recibo ya fue enviado.'}
        previous_state = pago.whatsapp_estado
        claimed = Pago.query.filter_by(id=pago.id, whatsapp_estado=previous_state).update({
            Pago.whatsapp_estado: 'enviando',
            Pago.whatsapp_ultimo_intento: get_bolivia_time(),
            Pago.whatsapp_intentos: Pago.whatsapp_intentos + 1,
            Pago.whatsapp_error: None,
        }, synchronize_session=False)
        if not claimed:
            db.session.rollback()
            return {'success': False, 'error': 'Otro proceso está gestionando este recibo.'}
        db.session.commit()
        db.session.refresh(pago)
        try:
            telefono = pago.prestamo.telefono_whatsapp
            if not telefono:
                result = {'success': False, 'error': 'El cliente no tiene teléfono registrado.', 'error_code': 'phone'}
            elif not whatsapp_service.esta_conectado():
                result = {'success': False, 'error': 'El bot de WhatsApp no está conectado.', 'error_code': 'disconnected'}
            else:
                image = pdf_service.generar_comprobante_imagen(build_receipt_data(pago))
                result = whatsapp_service.enviar_imagen(telefono, image.getvalue(), '🧾 Comprobante de pago - Panda | Casa de Empeño')
        except Exception:
            logger.exception('No se pudo completar el envío del recibo %s', pago_id)
            result = {'success': False, 'error': 'No se pudo completar el envío. Verifica WhatsApp antes de reintentar.'}
        pago.whatsapp_estado = 'enviado' if result.get('success') else 'error'
        pago.whatsapp_error = None if result.get('success') else result.get('error', 'Error de envío')
        pago.whatsapp_ultimo_intento = get_bolivia_time()
        db.session.commit()
        return result


def start_delivery_worker(app):
    if app.config.get('TESTING') or app.extensions.get('delivery_worker'):
        return
    stop = threading.Event()
    def run():
        while not stop.is_set():
            try:
                with app.app_context(), app.extensions['database_lock']:
                    # Un envío reciente puede pertenecer a otra instancia activa.
                    Pago.query.filter(Pago.whatsapp_estado == 'enviando',
                                      Pago.whatsapp_ultimo_intento < get_bolivia_time() - timedelta(minutes=5)).update({
                        Pago.whatsapp_estado: 'incierto',
                        Pago.whatsapp_error: 'Se interrumpió el envío. Verifica WhatsApp antes de reintentar.',
                    })
                    db.session.commit()
                    ids = [p.id for p in Pago.query.filter_by(whatsapp_estado='pendiente').order_by(Pago.id).limit(10)]
                for pago_id in ids:
                    if stop.is_set():
                        return
                    with app.app_context():
                        send_receipt(pago_id)
            except Exception:
                logger.exception('Error al procesar entregas pendientes')
            stop.wait(30)
    thread = threading.Thread(target=run, name='recibos-pendientes', daemon=True)
    app.extensions['delivery_worker'] = (thread, stop)
    thread.start()
