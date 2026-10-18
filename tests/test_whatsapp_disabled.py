"""El apagado general bloquea envíos y retira las acciones de la interfaz."""
from datetime import timedelta
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch

import pytest

from app import db
from app.models import Configuracion, Pago
from app.services import whatsapp_runtime, whatsapp_service
from app.services.delivery_service import pending_receipt_ids, send_receipt
from app.utils import get_bolivia_time


class VisibleText(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.ignored = 0
        self.text = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        if tag in {'script', 'style'}:
            self.ignored += 1

    def handle_endtag(self, tag):
        if tag in {'script', 'style'}:
            self.ignored -= 1

    def handle_data(self, text):
        if not self.ignored:
            self.text.append(text)


def test_apagado_cancela_pendientes_y_encendido_no_los_reenvia(admin_client, prestamo_prendario):
    Configuracion.set_valor('whatsapp_auto_envio', 'true')
    payments = []
    for state in ('pendiente', 'enviando', 'enviado'):
        payment = Pago(prestamo_id=prestamo_prendario.id, tipo_pago='interes', monto_pagado=50,
                       whatsapp_estado=state)
        db.session.add(payment)
        payments.append(payment)
    db.session.commit()
    with patch.object(whatsapp_runtime, 'stop_bot', return_value={'success': True}) as stop:
        response = admin_client.post('/admin/whatsapp/habilitar', data={})
    assert response.location.endswith('/admin/configuracion#whatsapp')
    stop.assert_called_once()
    db.session.expire_all()
    assert not whatsapp_service.esta_habilitado()
    assert [p.whatsapp_estado for p in payments] == ['cancelado', 'incierto', 'enviado']
    assert [p.monto_pagado for p in payments] == [50, 50, 50]
    assert Configuracion.get_valor('whatsapp_auto_envio') == 'true'
    with patch.object(whatsapp_runtime, 'start_bot', return_value={'success': True}) as start:
        admin_client.post('/admin/whatsapp/habilitar', data={'whatsapp_habilitado': 'on'})
    start.assert_called_once()
    assert whatsapp_service.esta_habilitado()
    assert pending_receipt_ids() == []


@pytest.mark.parametrize('auto', ['true', 'false'])
def test_pago_sin_integracion_no_encola_ni_pregunta_y_conserva_comprobantes(admin_client, prestamo_prendario, auto):
    Configuracion.set_valor('whatsapp_habilitado', 'false')
    Configuracion.set_valor('whatsapp_auto_envio', auto)
    with patch('app.routes.admin_loans.threading.Thread') as thread:
        response = admin_client.post(f'/admin/registrar-pago/{prestamo_prendario.id}', data={
            'tipo_pago': 'interes', 'monto': '50', 'meses_interes': '1',
        }, follow_redirects=True)
    assert response.status_code == 200
    thread.assert_not_called()
    payment = Pago.query.one()
    assert payment.whatsapp_estado == 'no_solicitado'
    assert 'modalConfirmarEnvioWhatsApp' not in response.get_data(as_text=True)
    for html in [response.get_data(as_text=True), admin_client.get('/admin/dashboard').get_data(as_text=True)]:
        assert 'whatsapp' not in ' '.join(VisibleText(html).text).lower()
        assert 'wa.me/' not in html
        assert 'id="whatsappModal"' not in html
        assert '/whatsapp/reenviar-recibo/' not in html
    assert admin_client.get(f'/admin/descargar-comprobante/{payment.id}').mimetype == 'application/pdf'
    assert admin_client.get(f'/admin/recibo-imagen/{payment.id}').mimetype == 'image/png'
    settings = admin_client.get('/admin/configuracion').get_data(as_text=True)
    assert 'id="whatsapp_habilitado"' in settings
    assert 'Deshabilitado' in settings
    assert 'id="whatsapp_auto_envio"' not in settings
    assert 'Estado y QR de WhatsApp' not in settings


@pytest.mark.parametrize('dias_hasta_vencer', [-1, 3])
@pytest.mark.parametrize('habilitado', [False, True])
def test_recordatorios_de_reportes_respetan_interruptor(admin_client, prestamo_prendario, dias_hasta_vencer, habilitado):
    Configuracion.set_valor('whatsapp_habilitado', 'true' if habilitado else 'false')
    prestamo_prendario.usuario.telefono = '70000000'
    prestamo_prendario.fecha_finalizacion = get_bolivia_time() + timedelta(days=dias_hasta_vencer)
    db.session.commit()
    with patch('urllib.request.urlopen') as network:
        response = admin_client.get('/admin/reportes')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert ('https://wa.me/' in html) is habilitado
    if not habilitado:
        assert 'whatsapp' not in ' '.join(VisibleText(html).text).lower()
    network.assert_not_called()


def test_apagado_bloquea_transporte_y_worker_sin_cambiar_intentos(prestamo_prendario):
    Configuracion.set_valor('whatsapp_habilitado', 'false')
    payment = Pago(prestamo_id=prestamo_prendario.id, tipo_pago='interes', monto_pagado=50,
                   whatsapp_estado='pendiente')
    db.session.add(payment)
    db.session.commit()
    with patch('urllib.request.urlopen') as network:
        for result in (whatsapp_service.obtener_estado(), whatsapp_service.obtener_qr_data(),
                       whatsapp_service.enviar_texto('70000000', 'Ficticio'),
                       whatsapp_service.enviar_imagen('70000000', b'Ficticio'),
                       whatsapp_service.reconectar(), whatsapp_service.cerrar_sesion(),
                       send_receipt(payment.id, force=True)):
            assert result['error_code'] == 'disabled'
        assert pending_receipt_ids() == []
    network.assert_not_called()
    assert payment.whatsapp_intentos == 0
    assert payment.whatsapp_estado == 'pendiente'


@pytest.mark.parametrize('path,method', [
    ('/admin/whatsapp', 'GET'), ('/admin/whatsapp/estado', 'GET'),
    ('/admin/whatsapp/qr-data', 'GET'), ('/admin/whatsapp/reconectar', 'POST'),
    ('/admin/whatsapp/cerrar-sesion', 'POST'), ('/admin/whatsapp/enviar-prueba', 'POST'),
    ('/admin/whatsapp/reenviar-recibo/9999', 'POST'), ('/admin/whatsapp/toggle-auto', 'POST'),
])
def test_rutas_antiguas_no_pueden_usarse_con_whatsapp_apagado(admin_client, path, method):
    Configuracion.set_valor('whatsapp_habilitado', 'false')
    with patch.object(whatsapp_service, '_hacer_peticion') as transport:
        response = admin_client.open(path, method=method)
    transport.assert_not_called()
    if path.endswith(('/estado', '/qr-data')):
        assert response.status_code == 403
        assert response.json['status'] == 'disabled'
    else:
        assert response.status_code == 302
        assert response.location.endswith('/admin/configuracion#whatsapp')


def test_interruptor_requiere_administrador_y_csrf(app, client, admin_client):
    with patch.object(whatsapp_runtime, 'stop_bot') as stop:
        # CSRF sigue protegiendo el interruptor incluso con una sesión administrativa.
        app.config['CSRF_ENABLED'] = True
        response = admin_client.post('/admin/whatsapp/habilitar', data={})
        assert response.status_code == 302
        assert whatsapp_service.esta_habilitado()
        stop.assert_not_called()
        app.config['CSRF_ENABLED'] = False
        admin_client.get('/logout')
        response = client.post('/admin/whatsapp/habilitar', data={})
        assert '/login' in response.location
        assert whatsapp_service.esta_habilitado()
        stop.assert_not_called()


def test_preferencia_persistida_se_aplica_en_otra_instancia(admin_client, app, tmp_path):
    from app import create_app
    Configuracion.set_valor('whatsapp_habilitado', 'false')
    # Archivo SQLite independiente, como el que carga el ejecutable al reiniciar.
    path = tmp_path / 'persistencia.db'
    with app.app_context():
        connection = db.engine.raw_connection()
        import sqlite3
        with sqlite3.connect(path) as target:
            connection.driver_connection.backup(target)
        connection.close()
    other = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite:///' + str(path),
                        'BACKUP_DIR': str(tmp_path / 'backups'), 'UPLOAD_FOLDER': str(tmp_path / 'uploads')})
    with other.app_context(), patch('subprocess.Popen') as spawn:
        assert not whatsapp_service.esta_habilitado()
        assert whatsapp_runtime.start_bot()['error_code'] == 'disabled'
        spawn.assert_not_called()
        db.session.remove()
        db.engine.dispose()


def test_runtime_empaquetado_usa_node_incluido_y_proceso_oculto(app, tmp_path):
    app.config.update(TESTING=False, BASEDIR=str(tmp_path), DATA_DIR=str(tmp_path / 'datos'))
    directory = tmp_path / 'whatsapp-bot'
    directory.mkdir()
    (directory / 'server.js').write_text('// bot ficticio', encoding='utf-8')
    (directory / 'node.exe').write_bytes(b'ficticio')
    with patch.object(whatsapp_runtime, '_port_open', return_value=False), patch('subprocess.Popen') as spawn:
        assert whatsapp_runtime.start_bot()['success']
    args, options = spawn.call_args
    assert Path(args[0][0]) == directory / 'node.exe'
    assert options['cwd'] == str(directory)
    assert options['env']['WHATSAPP_API_TOKEN'] == app.config['WHATSAPP_API_TOKEN']
    if whatsapp_runtime.os.name == 'nt':
        assert options['creationflags'] == whatsapp_runtime.subprocess.CREATE_NO_WINDOW


def test_apagado_runtime_permite_control_con_integracion_deshabilitada(app):
    app.config['TESTING'] = False
    Configuracion.set_valor('whatsapp_habilitado', 'false')
    with patch.object(whatsapp_runtime, '_port_open', side_effect=[True, False, False]), \
         patch.object(whatsapp_service, '_hacer_peticion', return_value={'success': True}) as control:
        assert whatsapp_runtime.stop_bot()['success']
    control.assert_called_once_with('/shutdown', method='POST')


def test_apagado_detiene_arranque_propio_antes_de_que_escuche(app):
    from unittest.mock import Mock
    app.config['TESTING'] = False
    process = Mock()
    process.poll.return_value = None
    app.extensions['whatsapp_process'] = process
    with patch.object(whatsapp_runtime, '_port_open', return_value=False):
        assert whatsapp_runtime.start_bot()['success']
        process.terminate.assert_not_called()
        assert whatsapp_runtime.stop_bot()['success']
    process.terminate.assert_called_once()
    process.wait.assert_called_once_with(timeout=4)
    assert 'whatsapp_process' not in app.extensions


def test_fallo_de_apagado_conserva_proceso_propio_para_reintentar(app):
    from unittest.mock import Mock
    app.config['TESTING'] = False
    process = Mock()
    process.poll.return_value = None
    process.terminate.side_effect = [PermissionError('Fallo ficticio'), None]
    app.extensions['whatsapp_process'] = process
    with patch.object(whatsapp_runtime, '_port_open', return_value=False):
        assert not whatsapp_runtime.stop_bot()['success']
        assert app.extensions['whatsapp_process'] is process
        assert whatsapp_runtime.stop_bot()['success']
    assert 'whatsapp_process' not in app.extensions
