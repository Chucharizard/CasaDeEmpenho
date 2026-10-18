"""
Fixtures compartidos para toda la suite de tests.

Estrategia:
  - Una instancia y base en memoria independientes por prueba.
  - SQLite en memoria con StaticPool → todas las sesiones de SQLAlchemy
    comparten la misma conexión, por lo que los datos insertados en fixtures
    son visibles dentro de los requests del test client.
  - Cada petición tiene contexto y sesión propios, sin caché de identidad compartida.
  - CSRF deshabilitado explícitamente salvo en pruebas específicas de seguridad.
"""

import os
import sys

import pytest
from sqlalchemy.pool import StaticPool
from werkzeug.security import generate_password_hash
from dateutil.relativedelta import relativedelta

# Asegurarse de que el directorio raíz del proyecto esté en sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)

from app import create_app, db as _db
from app.utils import get_bolivia_time

# ---------------------------------------------------------------------------
# Configuración para tests
# ---------------------------------------------------------------------------
TEST_CONFIG = {
    'TESTING': True,
    'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
    'SQLALCHEMY_ENGINE_OPTIONS': {
        'connect_args': {'check_same_thread': False},
        'poolclass': StaticPool,
    },
    'SECRET_KEY': 'test-secret-key-not-for-production',
    'ADMIN_URL_KEY': 'test-admin-url-key',
    'ADMIN_PREFIX': '/admin',
    'WTF_CSRF_ENABLED': False,
    'SERVER_NAME': None,
}


# ---------------------------------------------------------------------------
# App y BD independientes por prueba
# ---------------------------------------------------------------------------

from flask.testing import FlaskClient
from uuid import uuid4


class BrowserClient(FlaskClient):
    """Cada petición usa su propio contexto; simula el nonce del formulario."""
    def open(self, *args, **kwargs):
        path = args[0] if args and isinstance(args[0], str) else kwargs.get('path', '')
        if kwargs.get('method', 'GET').upper() == 'POST' or kwargs.get('data') is not None:
            if '/registrar-pago/' in path or '/vender-producto/' in path:
                data = dict(kwargs.get('data') or {})
                data.setdefault('operacion_id', uuid4().hex)
                kwargs['data'] = data
        with self.application.app_context():
            return super().open(*args, **kwargs)


@pytest.fixture
def app(tmp_path):
    config = dict(TEST_CONFIG, CSRF_ENABLED=False,
                  BACKUP_DIR=str(tmp_path / 'backups'), UPLOAD_FOLDER=str(tmp_path / 'uploads'),
                  CLIENT_ACCESS_ENABLED=True)
    instance = create_app(config)
    instance.test_client_class = BrowserClient
    with instance.app_context():
        _db.create_all()
    yield instance
    with instance.app_context():
        _db.session.remove()
        _db.drop_all()
        _db.engine.dispose()


@pytest.fixture(autouse=True)
def clean_db(app):
    """Contexto ORM por prueba; no se reutiliza para las peticiones HTTP."""
    with app.app_context():
        yield
        _db.session.remove()


@pytest.fixture
def client(app):
    return app.test_client()


# ---------------------------------------------------------------------------
# Usuarios
# ---------------------------------------------------------------------------

@pytest.fixture
def admin_user(app):
    """Usuario administrador activo."""
    from app.models.usuario import Usuario
    user = Usuario(
        ci='ADMIN001',
        nombre='Admin Test',
        password=generate_password_hash('AdminPass123'),
        es_admin=True,
        cuenta_activa=True,
    )
    _db.session.add(user)
    _db.session.commit()
    return user


@pytest.fixture
def regular_user(app):
    """Usuario cliente (no admin) activo."""
    from app.models.usuario import Usuario
    user = Usuario(
        ci='CLIENT001',
        nombre='Cliente Test',
        telefono='+59171000001',
        password=generate_password_hash('ClientPass123'),
        es_admin=False,
        cuenta_activa=True,
    )
    _db.session.add(user)
    _db.session.commit()
    return user


@pytest.fixture
def inactive_user(app):
    """Usuario creado por el admin pero sin cuenta activada aún."""
    from app.models.usuario import Usuario
    import secrets as _sec
    from werkzeug.security import generate_password_hash as gph
    user = Usuario(
        ci='INACTIVE001',
        nombre='Usuario Inactivo',
        password=gph(_sec.token_hex(16)),
        es_admin=False,
        cuenta_activa=False,
    )
    _db.session.add(user)
    _db.session.commit()
    return user


# ---------------------------------------------------------------------------
# Clientes autenticados
# ---------------------------------------------------------------------------

@pytest.fixture
def admin_client(client, admin_user):
    """Test client con sesión de administrador iniciada."""
    client.post('/login', data={
        'ci': 'ADMIN001',
        'password': 'AdminPass123',
    }, follow_redirects=True)
    return client


# ---------------------------------------------------------------------------
# Préstamos
# ---------------------------------------------------------------------------

@pytest.fixture
def prestamo_prendario(app, admin_user):
    """Préstamo prendario activo, vence en 1 mes, con artículo."""
    from app.models.prestamo import Prestamo
    from app.models.articulo import Articulo
    ahora = get_bolivia_time()
    p = Prestamo(
        numero_prestamo=1,
        numero_documento='PREST-0001',
        usuario_id=admin_user.id,
        monto_prestado=500.0,
        interes_mensual=10.0,
        fecha_inicio=ahora,
        fecha_finalizacion=ahora + relativedelta(months=1),
        tipo_prestamo='prendario',
        estado='activo',
    )
    _db.session.add(p)
    _db.session.flush()
    _db.session.add(Articulo(
        nombre='Celular Samsung',
        descripcion='Samsung Galaxy S21',
        prestamo_id=p.id,
        estado='empenado',
    ))
    _db.session.commit()
    return p


@pytest.fixture
def prestamo_vencido(app, admin_user):
    """Préstamo prendario que venció hace 5 días."""
    from app.models.prestamo import Prestamo
    from app.models.articulo import Articulo
    ahora = get_bolivia_time()
    p = Prestamo(
        numero_prestamo=2,
        numero_documento='PREST-0002',
        usuario_id=admin_user.id,
        monto_prestado=300.0,
        interes_mensual=10.0,
        fecha_inicio=ahora - relativedelta(months=2),
        fecha_finalizacion=ahora - relativedelta(days=5),
        tipo_prestamo='prendario',
        estado='activo',
    )
    _db.session.add(p)
    _db.session.flush()
    _db.session.add(Articulo(
        nombre='Reloj Casio',
        descripcion='Reloj dorado vintage',
        prestamo_id=p.id,
        estado='empenado',
    ))
    _db.session.commit()
    return p





# ---------------------------------------------------------------------------
# Productos
# ---------------------------------------------------------------------------

@pytest.fixture
def producto_venta(app):
    """Producto disponible para la venta."""
    from app.models.producto import ProductoVenta
    prod = ProductoVenta(
        nombre='Televisor 40"',
        descripcion='Smart TV Samsung 40 pulgadas',
        precio=1200.0,
        precio_compra=800.0,
        stock=3,
        stock_inicial=3,
        tipo='venta',
        estado='disponible',
    )
    _db.session.add(prod)
    _db.session.commit()
    return prod


@pytest.fixture
def producto_compra(app):
    """Producto adquirido, aún no puesto en venta."""
    from app.models.producto import ProductoVenta
    prod = ProductoVenta(
        nombre='Laptop HP',
        descripcion='HP Pavilion 15 Core i5',
        precio=1500.0,
        precio_compra=1500.0,
        stock=1,
        stock_inicial=1,
        tipo='compra',
        estado='compra',
    )
    _db.session.add(prod)
    _db.session.commit()
    return prod


# ---------------------------------------------------------------------------
# Brute-force reset (autouse)
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_brute_force():
    """Limpia los contadores de intentos fallidos entre tests."""
    import app.routes.auth as auth_mod
    auth_mod._FAILED_ATTEMPTS.clear()
    yield
    auth_mod._FAILED_ATTEMPTS.clear()
