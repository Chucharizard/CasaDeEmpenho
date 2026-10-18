"""
Tests del módulo de reportes y estadísticas.
"""

from app.utils import get_bolivia_time

import pytest
from dateutil.relativedelta import relativedelta

from app import db as _db
from app.models.prestamo import Pago, Prestamo


class TestReportesEndpoints:

    def test_reportes_carga(self, admin_client):
        resp = admin_client.get('/admin/reportes')
        assert resp.status_code == 200

    def test_reportes_sin_datos_carga_vacio(self, admin_client):
        """La página de reportes no debe fallar con BD vacía."""
        resp = admin_client.get('/admin/reportes')
        assert resp.status_code == 200

    def test_reportes_con_prestamos(self, admin_client, prestamo_prendario):
        resp = admin_client.get('/admin/reportes')
        assert resp.status_code == 200


class TestReportesCobradoHoy:

    def test_cobrado_hoy_registra_pagos(self, admin_client, prestamo_prendario):
        """Registrar pagos hoy y verificar que la página de reportes carga."""
        interes = prestamo_prendario.monto_prestado * prestamo_prendario.interes_mensual / 100
        admin_client.post(
            f'/admin/registrar-pago/{prestamo_prendario.id}',
            data={'tipo_pago': 'interes', 'monto': str(interes)},
        )
        resp = admin_client.get('/admin/reportes')
        assert resp.status_code == 200

    def test_pagos_del_dia_aparecen_en_bd(self, admin_client, prestamo_prendario):
        interes = prestamo_prendario.monto_prestado * prestamo_prendario.interes_mensual / 100
        admin_client.post(
            f'/admin/registrar-pago/{prestamo_prendario.id}',
            data={'tipo_pago': 'interes', 'monto': str(interes)},
        )
        _db.session.refresh(prestamo_prendario)
        pagos = Pago.query.filter_by(prestamo_id=prestamo_prendario.id).all()
        assert len(pagos) == 1
        assert pagos[0].monto_pagado == pytest.approx(interes)


class TestReportesPrestamosVencer:

    def test_prestamo_por_vencer_tiene_dias_positivos(self, admin_client, admin_user):
        """Préstamo que vence en 3 días tiene días_para_vencimiento > 0."""
        from app.models.articulo import Articulo
        ahora = get_bolivia_time()
        p = Prestamo(
            numero_prestamo=50,
            numero_documento='PREST-VENCE',
            usuario_id=admin_user.id,
            monto_prestado=200.0,
            interes_mensual=10.0,
            fecha_inicio=ahora - relativedelta(days=27),
            fecha_finalizacion=ahora + relativedelta(days=3),
            tipo_prestamo='prendario',
            estado='activo',
        )
        _db.session.add(p)
        _db.session.flush()
        _db.session.add(Articulo(nombre='Objeto por vencer', prestamo_id=p.id, estado='empenado'))
        _db.session.commit()

        assert 0 < p.dias_para_vencimiento <= 7

    def test_prestamo_vencido_tiene_dias_negativos(self, admin_client, prestamo_vencido):
        assert prestamo_vencido.dias_para_vencimiento < 0
        assert prestamo_vencido.dias_vencido == 5


class TestConfiguracion:

    def test_get_configuracion_carga(self, admin_client):
        resp = admin_client.get('/admin/configuracion')
        assert resp.status_code == 200

    def test_cambiar_tema_persiste(self, admin_client):
        """El POST con accion=cambiar_tema debe guardar el tema en Configuracion."""
        resp = admin_client.post('/admin/configuracion', data={
            'accion': 'cambiar_tema',
            'tema': 'dark',
        }, follow_redirects=True)
        assert resp.status_code == 200
        from app.models.configuracion import Configuracion
        assert Configuracion.get_valor('tema_sistema') == 'dark'

    def test_cambiar_interes_prendario_persiste(self, admin_client):
        """El POST con accion=cambiar_interes debe guardar las tasas."""
        admin_client.post('/admin/configuracion', data={
            'accion': 'cambiar_interes',
            'interes_prendario': '12',
            'interes_maximo': '25',
        })
        from app.models.configuracion import Configuracion
        assert Configuracion.get_valor('interes_prendario') == '12.0'

    def test_interes_invalido_no_se_guarda(self, admin_client):
        resp = admin_client.post('/admin/configuracion', data={
            'accion': 'cambiar_interes',
            'interes_prendario': 'no_es_numero',
            'interes_maximo': '25',
        }, follow_redirects=True)
        assert resp.status_code == 200
        from app.models.configuracion import Configuracion
        val = Configuracion.get_valor('interes_prendario')
        if val is not None:
            try:
                float(val)
            except ValueError:
                pytest.fail('Se guardó un valor no numérico para interes_prendario')

    def test_tema_invalido_no_se_guarda(self, admin_client):
        from app.models.configuracion import Configuracion
        Configuracion.set_valor('tema_sistema', 'default')
        admin_client.post('/admin/configuracion', data={
            'accion': 'cambiar_tema',
            'tema': 'tema_inexistente',
        })
        assert Configuracion.get_valor('tema_sistema') == 'default'


class TestClientesAdmin:

    def test_lista_clientes_carga(self, admin_client):
        resp = admin_client.get('/admin/clientes')
        assert resp.status_code == 200

    def test_lista_clientes_muestra_no_admin(self, admin_client, regular_user):
        resp = admin_client.get('/admin/clientes')
        assert resp.status_code == 200
        assert regular_user.nombre in resp.data.decode('utf-8')

    def test_buscar_usuario_por_ci_existente(self, admin_client, regular_user):
        resp = admin_client.get(f'/admin/api/buscar-usuario/{regular_user.ci}')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['encontrado'] is True
        assert data['ci'] == regular_user.ci

    def test_buscar_usuario_por_ci_inexistente(self, admin_client):
        resp = admin_client.get('/admin/api/buscar-usuario/CI_NO_EXISTE')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['encontrado'] is False
