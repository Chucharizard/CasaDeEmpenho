"""
Tests del módulo de inventario/tienda:
  - Visualización de productos
  - Creación de productos de venta y compra
  - Edición
  - Venta (reduce stock, cambia estado a 'vendido' si llega a 0)
  - Poner en venta (compra → disponible)
  - Eliminar
"""

import pytest
from app import db as _db
from app.models.producto import ProductoVenta


class TestInventarioLista:

    def test_inventario_carga(self, admin_client):
        resp = admin_client.get('/admin/inventario')
        assert resp.status_code == 200

    def test_inventario_con_productos(self, admin_client, producto_venta):
        resp = admin_client.get('/admin/inventario')
        assert resp.status_code == 200
        assert 'Televisor' in resp.data.decode('utf-8')


class TestCrearProducto:

    def test_crear_producto_venta_exitoso(self, admin_client):
        resp = admin_client.post('/admin/nuevo-producto', data={
            'nombre': 'Celular Xiaomi',
            'descripcion': 'Xiaomi Redmi Note 12',
            'precio': '350',
            'precio_compra': '250',
            'stock': '5',
            'tipo': 'venta',
        }, follow_redirects=True)
        assert resp.status_code == 200
        p = ProductoVenta.query.filter_by(nombre='Celular Xiaomi').first()
        assert p is not None
        assert p.precio == pytest.approx(350.0)
        assert p.stock == 5
        assert p.tipo == 'venta'
        assert p.estado == 'disponible'

    def test_crear_producto_compra_exitoso(self, admin_client):
        resp = admin_client.post('/admin/nuevo-producto', data={
            'nombre': 'Cámara Canon',
            'descripcion': 'EOS Rebel SL3',
            'precio': '1200',
            'precio_compra': '1200',
            'stock': '1',
            'tipo': 'compra',
        }, follow_redirects=True)
        assert resp.status_code == 200
        p = ProductoVenta.query.filter_by(nombre='Cámara Canon').first()
        assert p is not None
        assert p.tipo == 'compra'
        assert p.estado == 'compra'

    def test_crear_producto_sin_nombre_falla(self, admin_client):
        resp = admin_client.post('/admin/nuevo-producto', data={
            'nombre': '',
            'precio': '100',
            'stock': '1',
            'tipo': 'venta',
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert ProductoVenta.query.count() == 0

    def test_stock_inicial_igual_a_stock(self, admin_client):
        admin_client.post('/admin/nuevo-producto', data={
            'nombre': 'Producto Test',
            'precio': '100',
            'precio_compra': '80',
            'stock': '7',
            'tipo': 'venta',
        }, follow_redirects=True)
        p = ProductoVenta.query.filter_by(nombre='Producto Test').first()
        assert p is not None
        assert p.stock_inicial == 7


class TestEditarProducto:

    def test_editar_precio_y_descripcion(self, admin_client, producto_venta):
        resp = admin_client.post(
            f'/admin/editar-producto/{producto_venta.id}',
            data={
                'nombre': 'Televisor 55"',
                'descripcion': 'Smart TV Samsung 55"',
                'precio': '1800',
                'precio_compra': '1200',
                'stock': str(producto_venta.stock),
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        _db.session.refresh(producto_venta)
        assert producto_venta.precio == pytest.approx(1800.0)
        assert producto_venta.nombre == 'Televisor 55"'

    def test_editar_producto_inexistente_retorna_404(self, admin_client):
        resp = admin_client.post('/admin/editar-producto/99999', data={
            'nombre': 'No existe', 'precio': '100', 'stock': '1',
        })
        assert resp.status_code == 404


class TestVenderProducto:

    def test_vender_reduce_stock(self, admin_client, producto_venta):
        stock_antes = producto_venta.stock
        resp = admin_client.post(
            f'/admin/vender-producto/{producto_venta.id}',
            data={'cantidad': '1', 'precio_final': '1200'},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        _db.session.refresh(producto_venta)
        assert producto_venta.stock == stock_antes - 1

    def test_vender_todo_el_stock_cambia_estado_a_vendido(self, admin_client, producto_venta):
        """Al vender todas las unidades, el producto queda como 'vendido'."""
        # Vender las 3 unidades que tiene el producto de prueba, de a una por vez
        for _ in range(3):
            resp = admin_client.post(
                f'/admin/vender-producto/{producto_venta.id}',
                data={'precio_final': '1200'},
                follow_redirects=True,
            )
            assert resp.status_code == 200

        _db.session.refresh(producto_venta)
        assert producto_venta.stock == 0
        assert producto_venta.estado == 'vendido'

    def test_vender_sin_stock_falla(self, admin_client):
        """Producto sin stock: la venta debe fallar (flash danger, sin cambios)."""
        from app.models.producto import ProductoVenta as PV
        p = PV(nombre='Sin Stock', precio=100.0, precio_compra=80.0,
                stock=0, stock_inicial=1, tipo='venta', estado='vendido')
        _db.session.add(p)
        _db.session.commit()
        admin_client.post(
            f'/admin/vender-producto/{p.id}',
            data={'precio_final': '100'},
        )
        _db.session.refresh(p)
        assert p.stock == 0  # no cambió

    def test_vender_producto_inexistente_404(self, admin_client):
        resp = admin_client.post('/admin/vender-producto/99999',
                                 data={'cantidad': '1', 'precio_final': '100'})
        assert resp.status_code == 404


class TestPonerEnVenta:

    def test_poner_en_venta_cambia_estado(self, admin_client, producto_compra):
        assert producto_compra.estado == 'compra'
        resp = admin_client.post(
            f'/admin/poner-en-venta/{producto_compra.id}',
            data={'precio_venta': '1800'},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        _db.session.refresh(producto_compra)
        assert producto_compra.estado == 'disponible'

    def test_poner_en_venta_actualiza_precio(self, admin_client, producto_compra):
        admin_client.post(
            f'/admin/poner-en-venta/{producto_compra.id}',
            data={'precio_venta': '2000'},
        )
        _db.session.refresh(producto_compra)
        assert producto_compra.precio == pytest.approx(2000.0)


class TestEliminarProducto:

    def test_eliminar_producto_existente(self, admin_client, producto_venta):
        pid = producto_venta.id
        resp = admin_client.post(
            f'/admin/eliminar-producto/{pid}',
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert ProductoVenta.query.get(pid) is None

    def test_eliminar_producto_inexistente_404(self, admin_client):
        resp = admin_client.post('/admin/eliminar-producto/99999')
        assert resp.status_code == 404
