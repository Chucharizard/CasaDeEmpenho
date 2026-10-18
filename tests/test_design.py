"""Persistencia de apariencia y contraste de las acciones principales."""
import pytest

from app.models import Configuracion
from app.utils.themes import THEMES, _luminance


@pytest.mark.parametrize('style', ['brutalist', 'handdrawn', 'flat'])
@pytest.mark.parametrize('theme', ['citrus', 'graphite'])
def test_guarda_apariencia_sin_cambiar_reglas(admin_client, style, theme):
    Configuracion.set_valor('interes_prendario', '15')
    Configuracion.set_valor('whatsapp_auto_envio', 'false')
    response = admin_client.post('/admin/configuracion', data={
        'accion': 'cambiar_tema', 'tema': theme, 'estilo': style,
    })
    assert response.status_code == 302
    assert response.location.endswith('#apariencia')
    assert Configuracion.get_valor('tema_sistema') == theme
    assert Configuracion.get_valor('estilo_sistema') == style
    assert Configuracion.get_valor('interes_prendario') == '15'
    assert Configuracion.get_valor('whatsapp_auto_envio') == 'false'
    page = admin_client.get('/admin/configuracion').get_data(as_text=True)
    assert f'data-design="{style}"' in page
    assert f'data-theme="{theme}"' in page
    assert f'data-dark="{1 if THEMES[theme]["is_dark"] else 0}"' in page
    assert 'Datos de ejemplo' in page


@pytest.mark.parametrize('theme,style', [('citrus', 'inexistente'), ('inexistente', 'brutalist')])
def test_apariencia_invalida_no_guarda_parcialmente(admin_client, theme, style):
    Configuracion.set_valor('tema_sistema', 'midnight')
    Configuracion.set_valor('estilo_sistema', 'flat')
    admin_client.post('/admin/configuracion', data={'accion': 'cambiar_tema', 'tema': theme, 'estilo': style})
    assert Configuracion.get_valor('tema_sistema') == 'midnight'
    assert Configuracion.get_valor('estilo_sistema') == 'flat'


def test_cambio_de_color_anterior_conserva_estilo(admin_client):
    Configuracion.set_valor('estilo_sistema', 'handdrawn')
    admin_client.post('/admin/configuracion', data={'accion': 'cambiar_tema', 'tema': 'purple'})
    assert Configuracion.get_valor('estilo_sistema') == 'handdrawn'


def test_textos_de_botones_tienen_contraste_suficiente():
    for key, theme in THEMES.items():
        for background, foreground in [('--primario', '--sobre-primario'), ('--secundario', '--sobre-secundario')]:
            light, dark = sorted((_luminance(theme['variables'][background]), _luminance(theme['variables'][foreground])), reverse=True)
            assert (light + .05) / (dark + .05) >= 4.5, (key, background)


def test_grafito_textos_sobre_las_superficies_oscuras():
    variables = THEMES['graphite']['variables']
    for foreground in ('--color-texto-principal', '--color-texto-secundario'):
        for background in ('--bg-corporativo', '--bg-tarjeta', '--bg-sidebar'):
            light, dark = sorted((_luminance(variables[foreground]), _luminance(variables[background])), reverse=True)
            assert (light + .05) / (dark + .05) >= 4.5, (foreground, background)
