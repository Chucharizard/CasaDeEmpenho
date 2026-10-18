"""Regresiones de las redirecciones revisadas antes de publicar el proyecto."""
from pathlib import Path
from unittest.mock import patch

import pytest

from app.utils import local_redirect_target


@pytest.mark.parametrize('target', [
    'https://example.org/otra-app', '//example.org/otra-app',
    '///example.org', '/\\example.org', 'http://[', 'http://localhost//example.org',
    '/admin/\n/otra-app', '/admin/\t/otra-app', '/admin/\x7f', None,
])
def test_redireccion_rechaza_destinos_ajenos_y_malformados(target):
    assert local_redirect_target(target, '/login', origin='http://localhost/') == '/login'


def test_redireccion_conserva_ruta_y_busqueda_local():
    assert local_redirect_target('/admin/dashboard?estado=activo', '/login') == '/admin/dashboard?estado=activo'
    assert local_redirect_target('http://localhost/admin/dashboard?estado=activo', '/login',
                                 origin='http://localhost/') == '/admin/dashboard?estado=activo'
    # El puerto también identifica el origen de esta instalación.
    assert local_redirect_target('http://localhost:3001/admin', '/login',
                                 origin='http://localhost/') == '/login'


@pytest.mark.parametrize('endpoint,fallback', [
    ('/admin/hacer-respaldo', '/admin/configuracion'),
    ('/admin/whatsapp/reenviar-recibo/99999', '/admin/dashboard'),
])
@pytest.mark.parametrize('referrer,expected', [
    ('https://example.org/otra-app', None),
    ('http://[', None),
    ('http://localhost/admin/dashboard?estado=retencion', '/admin/dashboard?estado=retencion'),
])
def test_acciones_conservan_retorno_solo_dentro_de_la_app(admin_client, endpoint, fallback, referrer, expected):
    with patch('app.routes.admin_config.create_backup', return_value=Path('respaldo-ficticio.db')):
        response = admin_client.post(endpoint, headers={'Referer': referrer})
    assert response.status_code == 302
    assert response.location == (expected or fallback)


def test_csrf_invalido_no_redirige_a_sitio_externo(app, client):
    app.config['CSRF_ENABLED'] = True
    response = client.post('/login', data={'ci': 'FICTICIO', 'password': 'invalida'},
                           headers={'Referer': 'https://example.org/otra-app'})
    assert response.status_code == 302
    assert response.location == '/'
