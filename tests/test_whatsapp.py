"""
Pruebas para el módulo de integración con WhatsApp Bot.
"""
from unittest.mock import patch
from io import BytesIO
from app.utils import get_bolivia_time
from app import db
from app.models.prestamo import Pago


def test_whatsapp_panel_acceso(admin_client):
    """Verifica que el panel de WhatsApp cargue correctamente para el admin."""
    with patch('app.services.whatsapp_service.obtener_estado') as mock_status:
        mock_status.return_value = {'status': 'connected', 'linkedNumber': '59172880325', 'hasQR': False}
        res = admin_client.get('/admin/whatsapp')
        assert res.status_code == 200
        assert b'WhatsApp Bot' in res.data


def test_whatsapp_estado_endpoint(admin_client):
    """Verifica el endpoint AJAX que consulta el estado del bot."""
    with patch('app.services.whatsapp_service.obtener_estado') as mock_status:
        mock_status.return_value = {'status': 'qr_pending', 'linkedNumber': None, 'hasQR': True}
        res = admin_client.get('/admin/whatsapp/estado')
        assert res.status_code == 200
        data = res.get_json()
        assert data['status'] == 'qr_pending'
        assert data['hasQR'] is True


def test_whatsapp_qr_data_endpoint(admin_client):
    """Verifica el endpoint AJAX que retorna el QR como Data URI."""
    with patch('app.services.whatsapp_service.obtener_qr_data') as mock_qr:
        mock_qr.return_value = {'qr': 'data:image/png;base64,mockqrdata', 'status': 'qr_pending'}
        res = admin_client.get('/admin/whatsapp/qr-data')
        assert res.status_code == 200
        data = res.get_json()
        assert 'data:image/png;base64' in data['qr']


def test_whatsapp_enviar_prueba(admin_client):
    """Verifica el envío de mensaje de prueba."""
    with patch('app.services.whatsapp_service.enviar_texto') as mock_enviar:
        mock_enviar.return_value = {'success': True, 'message': 'Mensaje enviado'}
        res = admin_client.post('/admin/whatsapp/enviar-prueba', data={'telefono': '72880325'}, follow_redirects=True)
        assert res.status_code == 200
        mock_enviar.assert_called_once()


def test_whatsapp_reenviar_recibo_bot_no_conectado(admin_client, prestamo_prendario):
    """Verifica manejo cuando el bot no está conectado al intentar reenviar recibo."""
    prestamo_prendario.usuario.telefono = '72880325'
    db.session.add(prestamo_prendario.usuario)
    pago = Pago(
        prestamo_id=prestamo_prendario.id,
        tipo_pago='interes',
        monto_pagado=50.0,
        fecha_pago=get_bolivia_time(),
    )
    db.session.add(pago)
    db.session.commit()

    with patch('app.services.whatsapp_service.esta_conectado') as mock_conn:
        mock_conn.return_value = False
        res = admin_client.post(f'/admin/whatsapp/reenviar-recibo/{pago.id}', follow_redirects=False)
        assert res.status_code == 302
        assert '/admin/whatsapp' in res.location


def test_whatsapp_reenviar_recibo_exitoso(admin_client, prestamo_prendario):
    """Verifica envío exitoso de recibo por WhatsApp mediante el bot."""
    prestamo_prendario.usuario.telefono = '72880325'
    db.session.add(prestamo_prendario.usuario)
    pago = Pago(
        prestamo_id=prestamo_prendario.id,
        tipo_pago='interes',
        monto_pagado=50.0,
        fecha_pago=get_bolivia_time(),
    )
    db.session.add(pago)
    db.session.commit()

    with patch('app.services.whatsapp_service.esta_conectado') as mock_conn, \
         patch('app.services.whatsapp_service.enviar_imagen') as mock_send, \
         patch('app.services.pdf_service.generar_comprobante_imagen') as mock_img:
        mock_conn.return_value = True
        mock_send.return_value = {'success': True, 'message': 'Imagen enviada'}
        buf = BytesIO(b'fake_png_data')
        mock_img.return_value = buf

        res = admin_client.post(f'/admin/whatsapp/reenviar-recibo/{pago.id}', follow_redirects=True)
        assert res.status_code == 200
        mock_send.assert_called_once()
        assert 'enviado directamente' in res.data.decode('utf-8')


def test_whatsapp_toggle_auto_panel(admin_client):
    """Verifica que se pueda alternar el modo auto-envío desde el panel de WhatsApp."""
    from app.models.configuracion import Configuracion
    res = admin_client.post('/admin/whatsapp/toggle-auto', data={'whatsapp_auto_envio': 'on'}, follow_redirects=True)
    assert res.status_code == 200
    assert Configuracion.get_valor('whatsapp_auto_envio') == 'true'

    res = admin_client.post('/admin/whatsapp/toggle-auto', data={}, follow_redirects=True)
    assert res.status_code == 200
    assert Configuracion.get_valor('whatsapp_auto_envio') == 'false'


def test_whatsapp_toggle_auto_configuracion(admin_client):
    """Verifica que se pueda alternar el modo auto-envío desde la pantalla de configuración."""
    from app.models.configuracion import Configuracion
    res = admin_client.post('/admin/configuracion', data={
        'accion': 'cambiar_whatsapp',
        'whatsapp_auto_envio': 'on',
    }, follow_redirects=True)
    assert res.status_code == 200
    assert Configuracion.get_valor('whatsapp_auto_envio') == 'true'


def test_registrar_pago_con_auto_desactivado_guarda_en_sesion(admin_client, prestamo_prendario):
    """Verifica que si auto-envío está desactivado, al registrar pago se guarde en sesión para preguntar con ventana emergente."""
    from app.models.configuracion import Configuracion
    Configuracion.set_valor('whatsapp_auto_envio', 'false')

    with patch('app.routes.admin_loans.threading.Thread') as mock_thread:
        res = admin_client.post(f'/admin/registrar-pago/{prestamo_prendario.id}', data={
            'tipo_pago': 'interes',
            'monto': '50.0',
            'meses_interes': '1',
        }, follow_redirects=True)
        assert res.status_code == 200
        # No se debió disparar el thread de envío automático
        mock_thread.assert_not_called()
        # La vista debe contener el modal de confirmación
        assert 'modalConfirmarEnvioWhatsApp' in res.data.decode('utf-8')

