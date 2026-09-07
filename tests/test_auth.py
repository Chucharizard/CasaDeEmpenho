"""
Tests de autenticación: login, logout, registro y protección brute-force.
"""

import pytest
from app import db as _db
from app.models.usuario import Usuario
from werkzeug.security import generate_password_hash


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

class TestLogin:

    def test_login_exitoso_redirige_al_dashboard(self, client, admin_user):
        resp = client.post('/login', data={
            'ci': 'ADMIN001',
            'password': 'AdminPass123',
        })
        # Debe redirigir (302) al dashboard
        assert resp.status_code == 302
        assert '/admin/dashboard' in resp.headers.get('Location', '')

    def test_login_exitoso_establece_sesion(self, client, admin_user):
        client.post('/login', data={
            'ci': 'ADMIN001',
            'password': 'AdminPass123',
        })
        # Tras el login, el dashboard debe cargarse (200)
        resp = client.get('/admin/dashboard')
        assert resp.status_code == 200

    def test_login_ci_incorrecto_no_redirige(self, client, admin_user):
        resp = client.post('/login', data={
            'ci': 'CI_QUE_NO_EXISTE',
            'password': 'AdminPass123',
        }, follow_redirects=True)
        assert resp.status_code == 200
        # Debe volver al formulario de login
        assert b'login' in resp.data.lower() or b'CI o' in resp.data

    def test_login_password_incorrecto(self, client, admin_user):
        resp = client.post('/login', data={
            'ci': 'ADMIN001',
            'password': 'ContraseñaEquivocada',
        }, follow_redirects=True)
        assert resp.status_code == 200

    def test_login_cuenta_inactiva_redirige_a_registro(self, client, inactive_user):
        resp = client.post('/login', data={
            'ci': 'INACTIVE001',
            'password': 'cualquier_cosa',
        })
        # Debe redirigir a /register
        assert resp.status_code == 302
        assert 'register' in resp.headers.get('Location', '')

    def test_sin_login_dashboard_redirige_a_login(self, client):
        resp = client.get('/admin/dashboard', follow_redirects=True)
        assert resp.status_code == 200
        # Debe terminar en la página de login
        body = resp.data.decode('utf-8', errors='replace').lower()
        assert 'acceso administrador' in body or 'acceso restringido' in body or 'usuario' in body


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------

class TestLogout:

    def test_logout_redirige_al_inicio(self, admin_client):
        resp = admin_client.get('/logout')
        assert resp.status_code == 302
        # Debe ir al index público
        loc = resp.headers.get('Location', '')
        assert loc.endswith('/') or 'index' in loc

    def test_despues_del_logout_no_puede_acceder_dashboard(self, admin_client):
        admin_client.get('/logout')
        resp = admin_client.get('/admin/dashboard')
        assert resp.status_code == 302
        assert 'login' in resp.headers.get('Location', '')


# ---------------------------------------------------------------------------
# Brute-force
# ---------------------------------------------------------------------------

class TestBruteForce:

    def test_5_intentos_fallidos_bloquean_cuenta(self, client, admin_user):
        for _ in range(5):
            client.post('/login', data={
                'ci': 'ADMIN001',
                'password': 'incorrecta',
            })
        # 6° intento — debe ser bloqueado incluso con la contraseña correcta
        resp = client.post('/login', data={
            'ci': 'ADMIN001',
            'password': 'AdminPass123',
        }, follow_redirects=True)
        assert b'Demasiados intentos' in resp.data

    def test_4_intentos_fallidos_aun_permite_login(self, client, admin_user):
        for _ in range(4):
            client.post('/login', data={
                'ci': 'ADMIN001',
                'password': 'incorrecta',
            })
        # 5° intento con contraseña correcta → debe entrar
        resp = client.post('/login', data={
            'ci': 'ADMIN001',
            'password': 'AdminPass123',
        })
        assert resp.status_code == 302
        assert 'dashboard' in resp.headers.get('Location', '')


# ---------------------------------------------------------------------------
# Registro / activación de cuenta
# ---------------------------------------------------------------------------

class TestRegistro:

    def test_registro_activa_cuenta_de_usuario_inactivo(self, client, inactive_user):
        resp = client.post('/register', data={
            'ci': 'INACTIVE001',
            'password': 'NuevaPass123',
            'telefono': '71234567',
        }, follow_redirects=True)
        assert resp.status_code == 200
        # Verificar que la cuenta quedó activa
        _db.session.refresh(inactive_user)
        assert inactive_user.cuenta_activa is True

    def test_registro_requiere_password_minimo_8_chars(self, client, inactive_user):
        resp = client.post('/register', data={
            'ci': 'INACTIVE001',
            'password': 'corta',
        }, follow_redirects=True)
        assert resp.status_code == 200
        # La cuenta no debe haberse activado
        _db.session.refresh(inactive_user)
        assert inactive_user.cuenta_activa is False

    def test_registro_no_permite_activar_admin(self, client, admin_user):
        """El endpoint público no debe poder activar cuentas de admin."""
        resp = client.post('/register', data={
            'ci': 'ADMIN001',
            'password': 'NuevoPass999',
        }, follow_redirects=True)
        assert resp.status_code == 200
        # El admin ya estaba activo — su contraseña no debe haber cambiado
        _db.session.refresh(admin_user)
        from werkzeug.security import check_password_hash
        # Password original intacta
        assert check_password_hash(admin_user.password, 'AdminPass123')

    def test_registro_ci_inexistente_no_crea_usuario(self, client):
        resp = client.post('/register', data={
            'ci': 'CI_FANTASMA',
            'password': 'Password123',
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert Usuario.query.filter_by(ci='CI_FANTASMA').first() is None
