"""Casos de negocio e integridad que faltaban en la suite original."""
import json
import sqlite3
from contextlib import closing
from datetime import datetime
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest
from dateutil.relativedelta import relativedelta
from sqlalchemy import event
from werkzeug.security import generate_password_hash

from app import create_app, db
from app.models import Articulo, Configuracion, Pago, Prestamo, ProductoVenta, Usuario, Venta
from app.services.database_service import create_backup, initialize_database, restore_backup
from app.services.delivery_service import send_receipt
from app.services.receipt_service import build_receipt_data
from app.routes.admin_shared import parse_positive_float
from app.utils import get_bolivia_time


def pay(client, loan, **changes):
    data = {'tipo_pago': 'interes', 'monto': str(loan.interes_un_mes),
            'meses_interes': '1', 'operacion_id': uuid4().hex}
    data.update(changes)
    response = client.post(f'/admin/registrar-pago/{loan.id}', data=data)
    db.session.expire_all()
    return response


@pytest.mark.parametrize('value', ['inf', '-inf', 'nan', '0.001', '-1', '0', '1e999', None])
def test_rechaza_importes_invalidos(value):
    with pytest.raises(ValueError):
        parse_positive_float(value, 'monto')


def test_saldo_no_amortiza_capital_con_interes(admin_client, prestamo_prendario):
    pay(admin_client, prestamo_prendario)
    assert prestamo_prendario.monto_pendiente_estimado == 500
    assert prestamo_prendario.monto_liquidacion_actual == 500


def test_prestamo_anterior_rechaza_fecha_futura(admin_client):
    future = (get_bolivia_time() + relativedelta(days=1)).strftime('%Y-%m-%d')
    admin_client.post('/admin/prestamo-anterior', data={'ci': 'FUTURE', 'nombre': 'Ficticio', 'monto': '500', 'articulo_nombre': 'Prenda', 'fecha_inicio': future})
    assert Prestamo.query.count() == 0


@pytest.mark.parametrize('state', ['finalizado', 'decomisado'])
def test_mensaje_cerrado_no_ofrece_renovar(state, prestamo_prendario):
    prestamo_prendario.estado = state
    assert state in prestamo_prendario.whatsapp_mensaje
    assert 'renovar' not in prestamo_prendario.whatsapp_mensaje.lower()


def test_recibo_inmutable_y_excedente_no_inventa_meses(admin_client, prestamo_prendario):
    initial_due = prestamo_prendario.fecha_finalizacion
    pay(admin_client, prestamo_prendario, monto='100')
    first = Pago.query.order_by(Pago.id).first()
    original = build_receipt_data(first)
    assert original['meses_pagados'] == 1
    assert original['excedente'] == 50
    assert original['fecha_vencimiento'] == initial_due + relativedelta(months=1)
    assert prestamo_prendario.meses_interes_pagados == 1
    pay(admin_client, prestamo_prendario)
    prestamo_prendario.usuario.nombre = 'Nombre cambiado'
    prestamo_prendario.interes_mensual = 20
    db.session.commit()
    assert build_receipt_data(first) == original
    with patch('app.routes.admin_loans.generar_comprobante_pago', return_value=BytesIO(b'%PDF-test')) as generator:
        assert admin_client.get(f'/admin/descargar-comprobante/{first.id}').status_code == 200
        assert generator.call_args.args[0] == original
    assert '1 mes/es' in first.whatsapp_mensaje


def test_pago_historico_no_adivina_plazo(app, prestamo_prendario):
    pago = Pago(prestamo_id=prestamo_prendario.id, tipo_pago='interes', monto_pagado=50)
    db.session.add(pago)
    db.session.commit()
    data = build_receipt_data(pago)
    assert data['meses_pagados'] is None
    assert data['fecha_vencimiento'] is None
    assert data['historico_sin_plazo'] is True
    assert 'plazo original' in pago.whatsapp_mensaje.lower()


@pytest.mark.parametrize('kind', ['interes', 'total'])
def test_reintento_pago_no_duplica(admin_client, prestamo_prendario, kind):
    token = uuid4().hex
    amount = '50' if kind == 'interes' else '550'
    pay(admin_client, prestamo_prendario, tipo_pago=kind, monto=amount, operacion_id=token)
    due = prestamo_prendario.fecha_finalizacion
    pay(admin_client, prestamo_prendario, tipo_pago=kind, monto=amount, operacion_id=token)
    assert Pago.query.count() == 1
    assert prestamo_prendario.fecha_finalizacion == due


def test_identificador_no_reutilizable_con_otro_importe(admin_client, prestamo_prendario):
    token = uuid4().hex
    pay(admin_client, prestamo_prendario, operacion_id=token)
    pay(admin_client, prestamo_prendario, operacion_id=token, monto='100')
    assert Pago.query.count() == 1
    assert Pago.query.first().monto_pagado == 50


def test_pago_sin_identificador_no_se_registra(admin_client, prestamo_prendario):
    pay(admin_client, prestamo_prendario, operacion_id='')
    assert Pago.query.count() == 0


def test_infinito_no_liquida(admin_client, prestamo_prendario):
    pay(admin_client, prestamo_prendario, tipo_pago='total', monto='inf')
    assert prestamo_prendario.estado == 'activo'
    assert Pago.query.count() == 0


def test_liquidacion_libera_garantia(admin_client, prestamo_prendario):
    pay(admin_client, prestamo_prendario, tipo_pago='total', monto='550')
    assert prestamo_prendario.estado == 'finalizado'
    assert all(a.estado == 'liberado' for a in prestamo_prendario.articulos)


def test_decomiso_manual_sincroniza_y_no_duplica(admin_client, prestamo_prendario):
    for _ in range(2):
        admin_client.post(f'/admin/cambiar-estado/{prestamo_prendario.id}', data={'estado': 'decomisado'})
    db.session.expire_all()
    assert ProductoVenta.query.count() == 1
    assert prestamo_prendario.articulos[0].estado == 'decomisado'
    with patch('app.models.prestamo.get_bolivia_time', return_value=get_bolivia_time() + relativedelta(years=1)):
        assert prestamo_prendario.meses_adeudados == 0
        assert prestamo_prendario.interes_acumulado_pendiente == 0
        assert prestamo_prendario.monto_liquidacion_actual == 0


def test_no_libera_garantia_ya_vendida(admin_client, prestamo_prendario):
    admin_client.post(f'/admin/cambiar-estado/{prestamo_prendario.id}', data={'estado': 'decomisado'})
    producto = ProductoVenta.query.first()
    admin_client.post(f'/admin/vender-producto/{producto.id}', data={'precio_final': '700'})
    admin_client.post(f'/admin/cambiar-estado/{prestamo_prendario.id}', data={'estado': 'activo'})
    db.session.expire_all()
    assert prestamo_prendario.estado == 'decomisado'
    assert ProductoVenta.query.count() == 1


def test_ventas_parciales_conservan_importes_y_costos(admin_client, producto_venta):
    producto_venta.stock = 2
    producto_venta.stock_inicial = 2
    producto_venta.precio = 120
    producto_venta.precio_compra = 80
    db.session.commit()
    for price, expected in [('120', 120), ('150', 270)]:
        admin_client.post(f'/admin/vender-producto/{producto_venta.id}', data={'precio_final': price})
        assert sum(v.precio for v in Venta.query.all()) == expected
        response = admin_client.get('/admin/inventario?tab=vendidos')
        assert response.status_code == 200
    assert sum(v.ganancia for v in Venta.query.all()) == 110
    db.session.refresh(producto_venta)
    assert producto_venta.precio == 120
    producto_venta.nombre = 'Nombre actual'
    producto_venta.precio_compra = 999
    db.session.commit()
    assert all(v.costo_unitario == 80 and v.nombre != 'Nombre actual' for v in Venta.query.all())
    admin_client.post(f'/admin/eliminar-producto/{producto_venta.id}')
    db.session.expire_all()
    assert Venta.query.count() == 2
    assert producto_venta.estado == 'archivado'


def test_reintento_venta_no_duplica(admin_client, producto_venta):
    data = {'precio_final': '120', 'operacion_id': uuid4().hex}
    for _ in range(2):
        admin_client.post(f'/admin/vender-producto/{producto_venta.id}', data=data)
    db.session.refresh(producto_venta)
    assert Venta.query.count() == 1
    assert producto_venta.stock == 2


def test_tasa_configurada_se_muestra_y_aplica(admin_client):
    Configuracion.set_valor('interes_prendario', '15')
    for path in ['/admin/nuevo-prestamo', '/admin/prestamo-anterior']:
        html = admin_client.get(path).text
        assert 'const INTERES_MENSUAL = 15.0' in html
        assert 'Interés (15.0%)' in html
    admin_client.post('/admin/nuevo-prestamo', data={'ci': 'new123', 'nombre': 'Cliente', 'monto': '1000', 'articulo_nombre': 'Artículo'})
    assert Prestamo.query.first().interes_mensual == 15
    assert Prestamo.query.first().monto_liquidacion_actual == 1150


def test_ci_misma_normalizacion(admin_client, regular_user):
    assert admin_client.get('/admin/api/buscar-usuario/client001').json['encontrado'] is True
    admin_client.post('/admin/nuevo-prestamo', data={'ci': 'client001', 'nombre': 'Cliente', 'monto': '500', 'articulo_nombre': 'Artículo'})
    assert Usuario.query.filter_by(ci='CLIENT001').count() == 1
    assert Prestamo.query.first().usuario_id == regular_user.id


def test_cliente_anonimo_no_hereda_administrador(app, admin_client, regular_user):
    assert admin_client.get('/admin/dashboard').status_code == 200
    anonymous = app.test_client()
    assert anonymous.get('/admin/dashboard').status_code == 302
    regular = app.test_client()
    regular.post('/login', data={'ci': 'client001', 'password': 'ClientPass123'})
    assert regular.get('/admin/dashboard').status_code == 302
    assert regular.get('/cliente/panel').status_code == 200
    assert admin_client.get('/admin/dashboard').status_code == 200


def test_csrf_activo_acepta_token_y_rechaza_post_sin_token(app, client, admin_user):
    app.config['CSRF_ENABLED'] = True
    client.get('/login')
    with client.session_transaction() as session:
        token = session['_csrf_token']
    assert client.post('/login', data={'ci': 'ADMIN001', 'password': 'AdminPass123'}, headers={'Accept': 'application/json'}).status_code == 400
    assert client.get('/admin/dashboard').status_code == 302
    assert client.post('/login', data={'ci': 'ADMIN001', 'password': 'AdminPass123', 'csrf_token': token}).status_code == 302
    assert client.get('/admin/dashboard').status_code == 200


def test_dashboard_pagina_y_no_consulta_pago_por_fila(app, admin_client, admin_user):
    now = get_bolivia_time()
    for n in range(1, 62):
        db.session.add(Prestamo(numero_prestamo=n, numero_documento=f'PERF-{n}', usuario_id=admin_user.id,
            monto_prestado=1000, interes_mensual=10, fecha_inicio=now, fecha_finalizacion=now + relativedelta(months=1),
            estado='activo', tipo_prestamo='prendario'))
    db.session.commit()
    queries = []
    def count(conn, cursor, statement, params, context, executemany):
        queries.append(statement)
    event.listen(db.engine, 'before_cursor_execute', count)
    try:
        response = admin_client.get('/admin/dashboard')
    finally:
        event.remove(db.engine, 'before_cursor_execute', count)
    assert response.status_code == 200
    assert response.text.count('data-prestamo-id=') == 50
    assert '61 préstamos' in response.text
    assert sum('FROM pago' in q for q in queries) == 1
    assert admin_client.get('/admin/dashboard?page=2').text.count('data-prestamo-id=') == 11


def test_entrega_fallida_persistida_y_reintento(admin_client, prestamo_prendario):
    prestamo_prendario.usuario.telefono = '71234567'
    db.session.commit()
    pay(admin_client, prestamo_prendario)
    pago = Pago.query.first()
    with patch('app.services.whatsapp_service.esta_conectado', return_value=False):
        assert send_receipt(pago.id)['success'] is False
    assert pago.whatsapp_estado == 'error'
    with patch('app.services.whatsapp_service.esta_conectado', return_value=True), \
         patch('app.services.whatsapp_service.enviar_imagen', return_value={'success': True}) as send, \
         patch('app.services.pdf_service.generar_comprobante_imagen', return_value=BytesIO(b'png')):
        assert send_receipt(pago.id)['success'] is True
        assert send_receipt(pago.id)['success'] is True
        send.assert_called_once()
    assert pago.whatsapp_estado == 'enviado'


def file_app(tmp_path):
    app = create_app({'TESTING': True, 'CSRF_ENABLED': False,
                      'SQLALCHEMY_DATABASE_URI': 'sqlite:///' + str(tmp_path / 'operativa.db'),
                      'BACKUP_DIR': str(tmp_path / 'backups'), 'UPLOAD_FOLDER': str(tmp_path / 'uploads')})
    return app


def test_respaldo_wal_y_restauracion_validada(tmp_path):
    instance = file_app(tmp_path)
    with instance.app_context():
        try:
            initialize_database()
            user = Usuario(ci='TEST', nombre='Nombre inicial', password=generate_password_hash('testpass123'), es_admin=True, cuenta_activa=True)
            db.session.add(user)
            db.session.commit()
            backup = create_backup()
            with closing(sqlite3.connect(backup)) as connection:
                assert connection.execute('SELECT nombre FROM usuario').fetchone()[0] == 'Nombre inicial'
            Usuario.query.first().nombre = 'Nombre posterior'
            db.session.commit()
            invalid = tmp_path / 'invalid.db'
            invalid.write_text('no soy SQLite', encoding='utf-8')
            with pytest.raises((ValueError, sqlite3.DatabaseError)):
                restore_backup(invalid)
            assert Usuario.query.first().nombre == 'Nombre posterior'
            previous = restore_backup(backup)
            assert previous.is_file()
            assert Usuario.query.first().nombre == 'Nombre inicial'
            with closing(sqlite3.connect(previous)) as connection:
                assert connection.execute('SELECT nombre FROM usuario').fetchone()[0] == 'Nombre posterior'
        finally:
            db.session.remove()
            db.engine.dispose()


def test_migra_legacy_sin_cambiar_importes(tmp_path):
    instance = file_app(tmp_path)
    from flask_migrate import upgrade
    with instance.app_context():
        try:
            upgrade(revision='f8a9b0c1d2e3')
            with db.engine.begin() as connection:
                connection.exec_driver_sql("INSERT INTO usuario(id,ci,nombre,password,es_admin,cuenta_activa) VALUES(1,'LEGACY','Cliente anterior','hash',0,0)")
                connection.exec_driver_sql("INSERT INTO prestamo(id,numero_prestamo,numero_documento,usuario_id,monto_prestado,interes_mensual,fecha_inicio,fecha_finalizacion,estado,tipo_prestamo) VALUES(1,1,'OLD-1',1,1000,10,'2026-01-01','2026-02-01','retencion','prendario')")
                connection.exec_driver_sql("INSERT INTO pago(id,prestamo_id,fecha_pago,tipo_pago,monto_pagado) VALUES(1,1,'2026-02-01','interes',100)")
            initialize_database()
            assert Pago.query.first().monto_pagado == 100
            assert Prestamo.query.first().monto_prestado == 1000
            assert build_receipt_data(Pago.query.first())['fecha_vencimiento'] is None
            assert list(Path(instance.config['BACKUP_DIR']).glob('pre_migracion_*.db'))
            initialize_database()
            assert Pago.query.count() == 1
        finally:
            db.session.remove()
            db.engine.dispose()


def test_migracion_fallida_revierte_tambien_ddl(tmp_path, monkeypatch):
    from flask_migrate import upgrade
    from alembic import op
    from sqlalchemy import inspect
    instance = file_app(tmp_path)
    with instance.app_context():
        try:
            upgrade(revision='f8a9b0c1d2e3')
            original = op.create_table
            def fail(name, *args, **kwargs):
                if name == 'venta':
                    raise RuntimeError('Fallo simulado de migración')
                return original(name, *args, **kwargs)
            monkeypatch.setattr(op, 'create_table', fail)
            with pytest.raises(RuntimeError, match='simulado'):
                initialize_database()
            assert 'comprobante_json' not in {column['name'] for column in inspect(db.engine).get_columns('pago')}
            with db.engine.connect() as connection:
                assert connection.exec_driver_sql('SELECT version_num FROM alembic_version').scalar() == 'f8a9b0c1d2e3'
        finally:
            db.session.remove()
            db.engine.dispose()


@pytest.mark.parametrize('operation', ['pago', 'venta'])
def test_operaciones_concurrentes_entre_dos_instancias(tmp_path, operation):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    instances = [file_app(tmp_path), file_app(tmp_path)]
    now = get_bolivia_time()
    with instances[0].app_context():
        initialize_database()
        user = Usuario(ci='CONCURRENT', nombre='Ficticio', password=generate_password_hash('ConcurrentPass123'), es_admin=True, cuenta_activa=True)
        db.session.add(user)
        db.session.flush()
        loan = Prestamo(numero_prestamo=1, numero_documento='CONC-1', usuario_id=user.id, monto_prestado=500,
                        interes_mensual=10, fecha_inicio=now, fecha_finalizacion=now + relativedelta(months=1), estado='activo', tipo_prestamo='prendario')
        product = ProductoVenta(nombre='Única unidad', precio=120, precio_compra=80, stock=1, stock_inicial=1, tipo='venta', estado='disponible')
        db.session.add_all([loan, product])
        db.session.commit()
        loan_id, product_id = loan.id, product.id
    barrier = Barrier(2)
    def run(instance):
        client = instance.test_client()
        client.post('/login', data={'ci': 'CONCURRENT', 'password': 'ConcurrentPass123'})
        barrier.wait(timeout=15)
        if operation == 'pago':
            return client.post(f'/admin/registrar-pago/{loan_id}', data={'tipo_pago': 'interes', 'monto': '50', 'meses_interes': '1', 'operacion_id': uuid4().hex}).status_code
        return client.post(f'/admin/vender-producto/{product_id}', data={'precio_final': '120', 'operacion_id': uuid4().hex}).status_code
    try:
        with ThreadPoolExecutor(2) as pool:
            statuses = list(pool.map(run, instances))
        assert statuses == [302, 302]
        with instances[0].app_context():
            if operation == 'pago':
                assert Pago.query.count() == 2
                assert db.session.get(Prestamo, loan_id).fecha_finalizacion == now + relativedelta(months=3)
            else:
                assert Venta.query.count() == 1
                assert db.session.get(ProductoVenta, product_id).stock == 0
    finally:
        for instance in instances:
            with instance.app_context():
                db.session.remove()
                db.engine.dispose()


def test_restaurar_invalida_las_sesiones_anteriores(tmp_path):
    instance = file_app(tmp_path)
    with instance.app_context():
        initialize_database()
        db.session.add(Usuario(ci='RESTORE', nombre='Admin ficticio', password=generate_password_hash('RestorePass123'), es_admin=True, cuenta_activa=True))
        db.session.commit()
        backup = create_backup()
    try:
        clients = [instance.test_client(), instance.test_client()]
        for client in clients:
            client.post('/login', data={'ci': 'RESTORE', 'password': 'RestorePass123'})
            assert client.get('/admin/dashboard').status_code == 200
        response = clients[0].post('/admin/restaurar-respaldo', data={'backup_name': backup.name, 'password_confirmacion': 'RestorePass123'})
        assert response.location.endswith('/login')
        assert clients[1].get('/admin/dashboard').status_code == 302
    finally:
        with instance.app_context():
            db.session.remove()
            db.engine.dispose()


def test_instalacion_nueva_permite_un_solo_administrador(client):
    assert client.get('/configurar-admin', environ_overrides={'REMOTE_ADDR': '192.0.2.1'}).status_code == 404
    assert client.get('/configurar-admin').status_code == 200
    data = {'ci': 'INITIAL', 'nombre': 'Administrador ficticio', 'password': 'InitialPass123'}
    assert client.post('/configurar-admin', data=data).status_code == 302
    assert client.post('/configurar-admin', data=data).status_code == 404
    assert Usuario.query.filter_by(es_admin=True).count() == 1


def test_ci_heredado_en_minusculas_se_encuentra(admin_client, regular_user):
    with db.engine.begin() as connection:
        connection.exec_driver_sql("UPDATE usuario SET ci='client001' WHERE ci='CLIENT001'")
    assert admin_client.get('/admin/api/buscar-usuario/CLIENT001').json['encontrado'] is True


def test_instalacion_administrativa_no_activa_clientes(app, client, regular_user):
    app.config['CLIENT_ACCESS_ENABLED'] = False
    response = client.post('/login', data={'ci': regular_user.ci, 'password': 'ClientPass123'})
    assert 'reservado a administradores' in response.text
    assert client.get('/register').status_code == 404
    assert client.get('/admin/dashboard').status_code == 302


def test_mantenimiento_espera_lectores_sin_serializar_trabajo_normal():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from app.services.database_gate import DatabaseGate
    gate = DatabaseGate()
    started, release, exclusive = Event(), Event(), Event()
    def delivery():
        with gate:
            started.set()
            assert release.wait(5)
    def ordinary_request():
        with gate:
            return 'disponible'
    def maintenance():
        with gate.exclusive():
            with gate.exclusive(), gate:
                exclusive.set()
    with ThreadPoolExecutor(3) as pool:
        first = pool.submit(delivery)
        try:
            assert started.wait(3)
            assert pool.submit(ordinary_request).result(timeout=2) == 'disponible'
            writer = pool.submit(maintenance)
            assert not exclusive.wait(0.1)
        finally:
            release.set()
        first.result(timeout=3)
        writer.result(timeout=3)
        assert exclusive.is_set()


def test_envio_lento_no_bloquea_dashboard(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    instance = file_app(tmp_path)
    with instance.app_context():
        initialize_database()
        user = Usuario(ci='SLOW', nombre='Ficticio', telefono='71234567', password=generate_password_hash('SlowPass123'), es_admin=True, cuenta_activa=True)
        db.session.add(user)
        db.session.flush()
        now = get_bolivia_time()
        loan = Prestamo(numero_prestamo=1, numero_documento='SLOW-1', usuario_id=user.id, monto_prestado=500,
                        interes_mensual=10, fecha_inicio=now, fecha_finalizacion=now + relativedelta(months=1), estado='activo', tipo_prestamo='prendario')
        db.session.add(loan)
        db.session.flush()
        payment = Pago(prestamo_id=loan.id, tipo_pago='interes', monto_pagado=50, whatsapp_estado='pendiente')
        db.session.add(payment)
        db.session.commit()
        payment_id = payment.id
    client = instance.test_client()
    client.post('/login', data={'ci': 'SLOW', 'password': 'SlowPass123'})
    started, release = Event(), Event()
    def slow_send(*args):
        started.set()
        assert release.wait(5)
        return {'success': True}
    def deliver():
        with instance.app_context():
            return send_receipt(payment_id)
    try:
        with patch('app.services.whatsapp_service.esta_conectado', return_value=True), \
             patch('app.services.pdf_service.generar_comprobante_imagen', return_value=BytesIO(b'png')), \
             patch('app.services.whatsapp_service.enviar_imagen', side_effect=slow_send), ThreadPoolExecutor(2) as pool:
            job = pool.submit(deliver)
            try:
                assert started.wait(3)
                response = pool.submit(client.get, '/admin/dashboard').result(timeout=2)
                assert response.status_code == 200
            finally:
                release.set()
            assert job.result(timeout=3)['success'] is True
    finally:
        with instance.app_context():
            db.session.remove()
            db.engine.dispose()
