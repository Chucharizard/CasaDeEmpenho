"""El diseño de recibos debe conservar los datos y permitir textos completos."""
from copy import deepcopy
from datetime import datetime
from io import BytesIO

from PIL import Image, ImageDraw
import pytest

from app.services import receipt_image
from app.services.pdf_service import generar_comprobante_imagen


@pytest.fixture
def receipt_data():
    return {
        'numero_recibo': 'REC-DEMO-001', 'numero_documento': 'PREST-DEMO-015',
        'nombre_cliente': 'Ana Lucía Fernández de la Vega', 'ci_cliente': 'DEMO-001',
        'telefono_cliente': 'No registrado', 'articulos_descripcion': 'Laptop y cargador',
        'tipo_pago': 'interes', 'meses_pagados': 1, 'monto_pagado': 210,
        'monto_prestado': 2100, 'fecha_pago': datetime(2026, 10, 17, 17, 30),
        'fecha_inicio': datetime(2026, 1, 13),
        'fecha_vencimiento': datetime(2026, 11, 13), 'excedente': 0,
        'historico_sin_plazo': False,
    }


@pytest.mark.parametrize('variant', ['renovacion', 'total', 'historico', 'mora', 'largo', 'resumen', 'linea_temporal'])
def test_recibo_dibuja_datos_sin_recortar_o_modificar(monkeypatch, receipt_data, variant):
    if variant == 'total':
        receipt_data.update(tipo_pago='total', monto_pagado=2310)
    elif variant == 'historico':
        receipt_data.update(historico_sin_plazo=True, meses_pagados=None, fecha_vencimiento=None)
    elif variant == 'mora':
        receipt_data.update(fecha_vencimiento=datetime(2026, 5, 13), excedente=25)
    elif variant == 'largo':
        receipt_data.update(
            nombre_cliente='María de los Ángeles Fernández de la Vega y Salvatierra Quispe',
            ci_cliente='DEMO-IDENTIFICADOR-MUY-LARGO-' + '1234567890' * 5,
            articulos_descripcion='Laptop, cargador original y accesorios. ' * 25,
            monto_pagado=1234567890.50,
        )
    elif variant == 'resumen':
        receipt_data.update(resumen_interes={'cuota_mensual': 210, 'meses_pendientes': 4, 'interes_pendiente': 840})
    elif variant == 'linea_temporal':
        receipt_data.update(historial_pagos=[{
            'numero_recibo': f'REC-{i}', 'fecha_pago': datetime(2026, 10, 17),
            'tipo_pago': 'interes', 'meses_pagados': i, 'monto_pagado': 1234567890.50,
            'actual': i == 5,
        } for i in range(1, 6)], total_pagos_hasta_recibo=15)
    original_data = deepcopy(receipt_data)
    drawn = []
    original_text = ImageDraw.ImageDraw.text

    def record_text(draw, xy, value, *args, **kwargs):
        drawn.append((str(value), draw.textbbox(xy, value, font=kwargs['font'], anchor=kwargs['anchor'])))
        return original_text(draw, xy, value, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, 'text', record_text)
    result = generar_comprobante_imagen(receipt_data)
    assert receipt_data == original_data
    with Image.open(result) as image:
        assert image.format == 'PNG'
        assert image.width == 960
        assert image.height > 1000
        for value, (left, top, right, bottom) in drawn:
            assert 32 <= left <= right <= image.width - 32, value
            assert 32 <= top <= bottom <= image.height - 32, value
    text = ' '.join(value for value, _ in drawn)
    assert 'PANDA' in text
    assert 'CAPITAL INICIAL' not in text
    assert '13/01/2026' in text
    assert receipt_data['numero_recibo'] in text
    assert f"Bs. {receipt_data['monto_pagado']:,.2f}" in text
    # Los saltos de línea no pueden perder letras de los nombres o la garantía.
    compact_text = ''.join(text.split())
    assert ''.join(receipt_data['nombre_cliente'].split()) in compact_text
    assert ''.join(receipt_data['articulos_descripcion'].split()) in compact_text
    assert ''.join(receipt_data['ci_cliente'].split()) in compact_text
    if variant == 'total':
        assert 'Garantía liberada para retiro' in text
        assert 'VENCIMIENTO TRAS ESTE PAGO' not in text
    elif variant == 'historico':
        assert 'Plazo original no disponible' in text
        assert 'VENCIMIENTO TRAS ESTE PAGO' not in text
        assert 'renovación' not in text
    elif variant == 'mora':
        assert '13/05/2026' in text
        assert 'anterior a la fecha del pago' in text
        assert 'No amplía los meses indicados.' in text
    else:
        assert '13/11/2026' in text
    if variant == 'resumen':
        assert '4 cuotas pendientes' in text
        assert 'Bs. 840.00' in text
    elif variant == 'linea_temporal':
        assert 'Últimos 5 de 15' in text
        assert 'este pago' in text


def test_recibo_sin_asset_no_impide_descargar(monkeypatch, tmp_path, receipt_data):
    monkeypatch.setattr(receipt_image, 'LOGO_PATH', tmp_path / 'missing-logo.png')
    image = generar_comprobante_imagen(receipt_data)
    assert image.getvalue().startswith(b'\x89PNG')


def test_imagen_con_texto_de_markup_se_muestra_literal(receipt_data):
    receipt_data['nombre_cliente'] = '<b>Cliente & socios</b>'
    result = generar_comprobante_imagen(receipt_data)
    Image.open(BytesIO(result.getvalue())).verify()
