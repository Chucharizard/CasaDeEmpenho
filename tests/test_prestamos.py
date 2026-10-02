"""
Tests de flujos HTTP para préstamos prendarios y personales:
  - Creación de nuevos préstamos
  - Ver detalle (transición automática activo → retención)
  - Registro de pagos (interés y total)
  - Edición
  - Cambio de estado
  - Descarga de documento PDF
  - Dashboard y búsqueda
"""

import pytest
from dateutil.relativedelta import relativedelta

from app import db as _db
from app.models.articulo import Articulo
from app.models.prestamo import Pago, Prestamo
from app.models.usuario import Usuario


# ===========================================================================
# Nuevo préstamo
# ===========================================================================

class TestNuevoPrestamo:

    def test_get_formulario_nuevo_prestamo(self, admin_client):
        resp = admin_client.get('/admin/nuevo-prestamo')
        assert resp.status_code == 200

    def test_crear_prestamo_exitoso(self, admin_client):
        resp = admin_client.post('/admin/nuevo-prestamo', data={
            'ci': '87654321',
            'nombre': 'María Lopez',
            'telefono': '72345678',
            'articulo_nombre': 'Anillo de oro',
            'articulo_descripcion': 'Anillo 18k con piedra',
            'monto': '300',
        }, follow_redirects=True)
        assert resp.status_code == 200
        # El préstamo debe existir en la BD
        p = Prestamo.query.filter_by(numero_documento='PREST-0001').first()
        assert p is not None
        assert p.monto_prestado == 300.0
        assert p.tipo_prestamo == 'prendario'
        assert p.estado == 'activo'

    def test_crear_prestamo_crea_usuario_nuevo(self, admin_client):
        admin_client.post('/admin/nuevo-prestamo', data={
            'ci': 'CLIENTE_NUEVO',
            'nombre': 'Pedro Rojas',
            'telefono': '73456789',
            'articulo_nombre': 'Laptop',
            'articulo_descripcion': 'HP Core i5',
            'monto': '1000',
        }, follow_redirects=True)
        usuario = Usuario.query.filter_by(ci='CLIENTE_NUEVO').first()
        assert usuario is not None
        assert usuario.nombre == 'Pedro Rojas'
        assert usuario.es_admin is False
        assert usuario.cuenta_activa is False

    def test_crear_prestamo_crea_articulo(self, admin_client):
        admin_client.post('/admin/nuevo-prestamo', data={
            'ci': '11111111',
            'nombre': 'Ana Garcia',
            'articulo_nombre': 'TV Samsung',
            'articulo_descripcion': 'Smart TV 43"',
            'monto': '500',
        }, follow_redirects=True)
        p = Prestamo.query.filter_by(numero_documento='PREST-0001').first()
        assert p is not None
        assert len(p.articulos) == 1
        assert p.articulos[0].nombre == 'TV Samsung'

    def test_crear_prestamo_usa_usuario_existente(self, admin_client, regular_user):
        admin_client.post('/admin/nuevo-prestamo', data={
            'ci': 'CLIENT001',  # CI del regular_user que ya existe
            'nombre': 'Nombre Actualizado',
            'articulo_nombre': 'Reloj',
            'monto': '200',
        }, follow_redirects=True)
        # No debe haber duplicado de usuario
        assert Usuario.query.filter_by(ci='CLIENT001').count() == 1

    def test_crear_prestamo_campos_obligatorios_vacios(self, admin_client):
        resp = admin_client.post('/admin/nuevo-prestamo', data={
            'ci': '',
            'nombre': '',
            'articulo_nombre': '',
            'monto': '100',
        }, follow_redirects=True)
        assert resp.status_code == 200
        # No debe haberse creado ningún préstamo
        assert Prestamo.query.count() == 0

    def test_crear_prestamo_monto_invalido(self, admin_client):
        resp = admin_client.post('/admin/nuevo-prestamo', data={
            'ci': '99999999',
            'nombre': 'Test',
            'articulo_nombre': 'Objeto',
            'monto': 'no_es_numero',
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert Prestamo.query.count() == 0


# ===========================================================================
# Ver préstamo (detalle)
# ===========================================================================

class TestVerPrestamo:

    def test_ver_prestamo_existente_retorna_200(self, admin_client, prestamo_prendario):
        resp = admin_client.get(f'/admin/prestamo/{prestamo_prendario.id}')
        assert resp.status_code == 200

    def test_ver_prestamo_inexistente_retorna_404(self, admin_client):
        resp = admin_client.get('/admin/prestamo/99999')
        assert resp.status_code == 404

    def test_ver_prestamo_vencido_cambia_estado_a_retencion(self, admin_client, prestamo_vencido):
        assert prestamo_vencido.estado == 'activo'
        admin_client.get(f'/admin/prestamo/{prestamo_vencido.id}')
        _db.session.refresh(prestamo_vencido)
        assert prestamo_vencido.estado == 'retencion'


# ===========================================================================
# Registrar pago
# ===========================================================================

class TestRegistrarPago:

    def test_pago_interes_exitoso(self, admin_client, prestamo_prendario):
        interes = prestamo_prendario.monto_prestado * prestamo_prendario.interes_mensual / 100
        resp = admin_client.post(
            f'/admin/registrar-pago/{prestamo_prendario.id}',
            data={'tipo_pago': 'interes', 'monto': str(interes)},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        _db.session.refresh(prestamo_prendario)
        assert len(prestamo_prendario.pagos) == 1
        assert prestamo_prendario.pagos[0].tipo_pago == 'interes'

    def test_pago_interes_extiende_vencimiento_un_mes(self, admin_client, prestamo_prendario):
        fecha_antes = prestamo_prendario.fecha_finalizacion
        interes = prestamo_prendario.monto_prestado * prestamo_prendario.interes_mensual / 100
        admin_client.post(
            f'/admin/registrar-pago/{prestamo_prendario.id}',
            data={'tipo_pago': 'interes', 'monto': str(interes)},
        )
        _db.session.refresh(prestamo_prendario)
        assert prestamo_prendario.fecha_finalizacion > fecha_antes
        # Debe ser exactamente 1 mes más
        esperado = fecha_antes + relativedelta(months=1)
        diff = abs((prestamo_prendario.fecha_finalizacion - esperado).total_seconds())
        assert diff < 60  # margen de 1 minuto

    def test_pago_interes_mantiene_estado_activo(self, admin_client, prestamo_prendario):
        interes = prestamo_prendario.monto_prestado * prestamo_prendario.interes_mensual / 100
        admin_client.post(
            f'/admin/registrar-pago/{prestamo_prendario.id}',
            data={'tipo_pago': 'interes', 'monto': str(interes)},
        )
        _db.session.refresh(prestamo_prendario)
        assert prestamo_prendario.estado == 'activo'

    def test_pago_interes_monto_insuficiente_no_registra(self, admin_client, prestamo_prendario):
        interes = prestamo_prendario.monto_prestado * prestamo_prendario.interes_mensual / 100
        monto_bajo = interes - 1  # 1 Bs menos del interés
        resp = admin_client.post(
            f'/admin/registrar-pago/{prestamo_prendario.id}',
            data={'tipo_pago': 'interes', 'monto': str(monto_bajo)},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        _db.session.refresh(prestamo_prendario)
        assert len(prestamo_prendario.pagos) == 0

    def test_pago_total_finaliza_prestamo(self, admin_client, prestamo_prendario):
        total = prestamo_prendario.monto_a_pagar
        resp = admin_client.post(
            f'/admin/registrar-pago/{prestamo_prendario.id}',
            data={'tipo_pago': 'total', 'monto': str(total)},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        _db.session.refresh(prestamo_prendario)
        assert prestamo_prendario.estado == 'finalizado'

    def test_pago_total_registra_pago_en_bd(self, admin_client, prestamo_prendario):
        total = prestamo_prendario.monto_a_pagar
        admin_client.post(
            f'/admin/registrar-pago/{prestamo_prendario.id}',
            data={'tipo_pago': 'total', 'monto': str(total)},
        )
        _db.session.refresh(prestamo_prendario)
        assert len(prestamo_prendario.pagos) == 1
        assert prestamo_prendario.pagos[0].tipo_pago == 'total'

    def test_pago_total_monto_insuficiente_no_finaliza(self, admin_client, prestamo_prendario):
        total = prestamo_prendario.monto_a_pagar
        admin_client.post(
            f'/admin/registrar-pago/{prestamo_prendario.id}',
            data={'tipo_pago': 'total', 'monto': str(total - 1)},
        )
        _db.session.refresh(prestamo_prendario)
        assert prestamo_prendario.estado == 'activo'

    def test_pago_en_prestamo_finalizado_rechazado(self, admin_client, prestamo_prendario):
        """No se deben aceptar pagos en préstamos ya finalizados."""
        prestamo_prendario.estado = 'finalizado'
        _db.session.commit()
        resp = admin_client.post(
            f'/admin/registrar-pago/{prestamo_prendario.id}',
            data={'tipo_pago': 'total', 'monto': '9999'},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        _db.session.refresh(prestamo_prendario)
        assert len(prestamo_prendario.pagos) == 0


# ===========================================================================
# Cambiar estado
# ===========================================================================

class TestCambiarEstado:

    def test_cambiar_a_retencion(self, admin_client, prestamo_prendario):
        resp = admin_client.post(
            f'/admin/cambiar-estado/{prestamo_prendario.id}',
            data={'estado': 'retencion'},
        )
        assert resp.status_code == 302
        _db.session.refresh(prestamo_prendario)
        assert prestamo_prendario.estado == 'retencion'

    def test_cambiar_a_decomisado(self, admin_client, prestamo_prendario):
        admin_client.post(
            f'/admin/cambiar-estado/{prestamo_prendario.id}',
            data={'estado': 'decomisado'},
        )
        _db.session.refresh(prestamo_prendario)
        assert prestamo_prendario.estado == 'decomisado'

    def test_cambiar_a_estado_invalido_no_cambia(self, admin_client, prestamo_prendario):
        admin_client.post(
            f'/admin/cambiar-estado/{prestamo_prendario.id}',
            data={'estado': 'estado_inventado'},
            follow_redirects=True,
        )
        _db.session.refresh(prestamo_prendario)
        assert prestamo_prendario.estado == 'activo'


# ===========================================================================
# Editar préstamo
# ===========================================================================

class TestEditarPrestamo:

    def test_editar_monto_e_interes(self, admin_client, prestamo_prendario):
        nueva_fecha = '2027-12-31'
        admin_client.post(
            f'/admin/editar-prestamo/{prestamo_prendario.id}',
            data={
                'monto_prestado': '750',
                'interes_mensual': '12',
                'fecha_finalizacion': nueva_fecha,
                'articulo_nombre': 'Nuevo nombre articulo',
                'articulo_descripcion': 'Nueva descripcion',
            },
        )
        _db.session.refresh(prestamo_prendario)
        assert prestamo_prendario.monto_prestado == pytest.approx(750.0)
        assert prestamo_prendario.interes_mensual == pytest.approx(12.0)

    def test_editar_articulo(self, admin_client, prestamo_prendario):
        admin_client.post(
            f'/admin/editar-prestamo/{prestamo_prendario.id}',
            data={
                'monto_prestado': '500',
                'interes_mensual': '10',
                'fecha_finalizacion': '2027-06-01',
                'articulo_nombre': 'iPhone 15 Pro',
                'articulo_descripcion': 'Negro 256GB',
            },
        )
        _db.session.refresh(prestamo_prendario)
        assert prestamo_prendario.articulos[0].nombre == 'iPhone 15 Pro'


# ===========================================================================
# Descarga de PDF
# ===========================================================================

class TestDescargarDocumento:

    def test_descarga_pdf_retorna_application_pdf(self, admin_client, prestamo_prendario):
        resp = admin_client.get(f'/admin/descargar-documento/{prestamo_prendario.id}')
        assert resp.status_code == 200
        assert resp.content_type == 'application/pdf'

    def test_descarga_pdf_nombre_correcto(self, admin_client, prestamo_prendario):
        resp = admin_client.get(f'/admin/descargar-documento/{prestamo_prendario.id}')
        disposition = resp.headers.get('Content-Disposition', '')
        assert 'PREST-0001' in disposition

    def test_descarga_pdf_inexistente_retorna_404(self, admin_client):
        resp = admin_client.get('/admin/descargar-documento/99999')
        assert resp.status_code == 404


# ===========================================================================
# Dashboard
# ===========================================================================

class TestDashboard:

    def test_dashboard_carga_correctamente(self, admin_client):
        resp = admin_client.get('/admin/dashboard')
        assert resp.status_code == 200

    def test_dashboard_busqueda_por_ci(self, admin_client, prestamo_prendario):
        resp = admin_client.get('/admin/dashboard?search_ci=ADMIN001')
        assert resp.status_code == 200

    def test_dashboard_filtro_estado_activo(self, admin_client, prestamo_prendario):
        resp = admin_client.get('/admin/dashboard?estado=activo')
        assert resp.status_code == 200

    def test_dashboard_auto_transicion_vencidos_a_retencion(self, admin_client, prestamo_vencido):
        assert prestamo_vencido.estado == 'activo'
        admin_client.get('/admin/dashboard')
        _db.session.refresh(prestamo_vencido)
        assert prestamo_vencido.estado == 'retencion'

    def test_api_buscar_usuario_existente(self, admin_client, regular_user):
        resp = admin_client.get(f'/admin/api/buscar-usuario/{regular_user.ci}')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['encontrado'] is True
        assert data['ci'] == regular_user.ci

    def test_api_buscar_usuario_inexistente(self, admin_client):
        resp = admin_client.get('/admin/api/buscar-usuario/CI_FANTASMA')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['encontrado'] is False


# ===========================================================================
# Pagos múltiples, decomiso a inventario y rutas eliminadas
# ===========================================================================

class TestPrestamosExtensionesyDecomiso:

    def test_rutas_personales_retornan_404(self, admin_client):
        resp1 = admin_client.get('/admin/prestamos-personales')
        assert resp1.status_code == 404
        resp2 = admin_client.get('/admin/nuevo-prestamo-personal')
        assert resp2.status_code == 404

    def test_pago_interes_multiples_meses(self, admin_client, prestamo_vencido):
        fecha_antes = prestamo_vencido.fecha_finalizacion
        cuota = prestamo_vencido.interes_un_mes
        resp = admin_client.post(
            f'/admin/registrar-pago/{prestamo_vencido.id}',
            data={
                'tipo_pago': 'interes',
                'meses_interes': '2',
                'monto': str(cuota * 2),
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        _db.session.refresh(prestamo_vencido)
        # Vencimiento debe haberse extendido 2 meses
        esperado = fecha_antes + relativedelta(months=2)
        diff = abs((prestamo_vencido.fecha_finalizacion - esperado).total_seconds())
        assert diff < 60
        assert len(prestamo_vencido.pagos) == 1
        assert prestamo_vencido.pagos[0].monto_pagado == cuota * 2

    def test_decomisar_a_inventario(self, admin_client, prestamo_vencido):
        from app.models.producto import ProductoVenta
        resp = admin_client.post(
            f'/admin/decomisar-a-inventario/{prestamo_vencido.id}',
            data={'precio_venta': '750.50'},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        _db.session.refresh(prestamo_vencido)
        assert prestamo_vencido.estado == 'decomisado'
        articulo = prestamo_vencido.articulos[0]
        assert articulo.estado == 'decomisado'
        # Debe existir el producto en inventario/tienda
        prod = ProductoVenta.query.filter_by(nombre=articulo.nombre).first()
        assert prod is not None
        assert prod.precio == 750.50
        assert prod.precio_compra == prestamo_vencido.monto_prestado

    def test_prestamo_anterior_exitoso(self, admin_client):
        resp = admin_client.post('/admin/prestamo-anterior', data={
            'ci': 'ANTIGUO001',
            'nombre': 'Carlos Viejo',
            'articulo_nombre': 'Cadena de oro',
            'articulo_descripcion': '18 kilates',
            'monto': '250',
            'fecha_inicio': '2025-01-15',
        }, follow_redirects=True)
        assert resp.status_code == 200
        p = Prestamo.query.filter_by(numero_documento='PREST-0001').first()
        assert p is not None
        assert p.fecha_inicio.year == 2025


# ===========================================================================
# Generación y Descarga de Documentos PDF
# ===========================================================================

class TestDocumentosPDF:

    def test_descargar_contrato_pdf(self, admin_client, prestamo_prendario):
        resp = admin_client.get(f'/admin/descargar-documento/{prestamo_prendario.id}')
        assert resp.status_code == 200
        assert resp.content_type == 'application/pdf'
        assert resp.data.startswith(b'%PDF')

    def test_descargar_comprobante_pago_pdf(self, admin_client, prestamo_prendario):
        # Registrar un pago primero
        cuota = prestamo_prendario.interes_un_mes
        admin_client.post(
            f'/admin/registrar-pago/{prestamo_prendario.id}',
            data={'tipo_pago': 'interes', 'monto': str(cuota), 'meses_interes': '1'},
        )
        _db.session.refresh(prestamo_prendario)
        assert len(prestamo_prendario.pagos) == 1
        pago = prestamo_prendario.pagos[0]

        resp = admin_client.get(f'/admin/descargar-comprobante/{pago.id}')
        assert resp.status_code == 200
        assert resp.content_type == 'application/pdf'
        assert resp.data.startswith(b'%PDF')

    def test_descargar_comprobante_inexistente(self, admin_client):
        resp = admin_client.get('/admin/descargar-comprobante/99999', follow_redirects=True)
        assert resp.status_code == 200
        assert 'Pago no encontrado' in resp.get_data(as_text=True)

    def test_descargar_comprobante_imagen_png(self, admin_client, prestamo_prendario):
        cuota = prestamo_prendario.interes_un_mes
        admin_client.post(
            f'/admin/registrar-pago/{prestamo_prendario.id}',
            data={'tipo_pago': 'interes', 'monto': str(cuota), 'meses_interes': '1'},
        )
        _db.session.refresh(prestamo_prendario)
        pago = prestamo_prendario.pagos[0]

        resp = admin_client.get(f'/admin/recibo-imagen/{pago.id}')
        assert resp.status_code == 200
        assert resp.content_type == 'image/png'
        assert resp.data.startswith(b'\x89PNG\r\n\x1a\n')

    def test_recibo_imagen_inexistente(self, admin_client):
        resp = admin_client.get('/admin/recibo-imagen/99999', follow_redirects=True)
        assert resp.status_code == 200
        assert 'Pago no encontrado' in resp.get_data(as_text=True)



# ===========================================================================
# Envío de Recibo por WhatsApp
# ===========================================================================

class TestWhatsAppRecibo:

    def test_whatsapp_url_pago_interes(self, admin_client, prestamo_prendario):
        prestamo_prendario.usuario.telefono = '72345678'
        _db.session.commit()

        cuota = prestamo_prendario.interes_un_mes
        admin_client.post(
            f'/admin/registrar-pago/{prestamo_prendario.id}',
            data={'tipo_pago': 'interes', 'monto': str(cuota), 'meses_interes': '1'},
        )
        _db.session.refresh(prestamo_prendario)
        pago = prestamo_prendario.pagos[0]

        assert pago.whatsapp_url is not None
        assert 'https://wa.me/59172345678' in pago.whatsapp_url
        assert 'COMPROBANTE' in pago.whatsapp_url
        assert pago.whatsapp_mensaje is not None
        assert 'COMPROBANTE DE PAGO' in pago.whatsapp_mensaje
        assert f"{pago.monto_pagado:.2f}" in pago.whatsapp_mensaje

    def test_whatsapp_url_pago_total(self, admin_client, prestamo_prendario):
        prestamo_prendario.usuario.telefono = '72345678'
        _db.session.commit()

        admin_client.post(
            f'/admin/registrar-pago/{prestamo_prendario.id}',
            data={'tipo_pago': 'total', 'monto': str(prestamo_prendario.monto_liquidacion_actual)},
        )
        _db.session.refresh(prestamo_prendario)
        pago = prestamo_prendario.pagos[0]

        assert pago.whatsapp_url is not None
        assert 'https://wa.me/59172345678' in pago.whatsapp_url
        assert 'COMPROBANTE' in pago.whatsapp_url
        assert 'Liquidación Total' in pago.whatsapp_mensaje
        assert 'PRENDA LIBERADA' in pago.whatsapp_mensaje

    def test_whatsapp_url_cliente_sin_telefono(self, admin_client, prestamo_prendario):
        prestamo_prendario.usuario.telefono = None
        _db.session.commit()

        cuota = prestamo_prendario.interes_un_mes
        admin_client.post(
            f'/admin/registrar-pago/{prestamo_prendario.id}',
            data={'tipo_pago': 'interes', 'monto': str(cuota), 'meses_interes': '1'},
        )
        _db.session.refresh(prestamo_prendario)
        pago = prestamo_prendario.pagos[0]
        assert pago.whatsapp_url is None
        assert pago.whatsapp_mensaje is not None


