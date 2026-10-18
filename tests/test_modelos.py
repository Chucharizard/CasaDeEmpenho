"""
Tests unitarios para los modelos del dominio.

Cubren la lógica de negocio PURA (propiedades calculadas, reglas de fecha,
acumulación de pagos) sin hacer requests HTTP.
"""

from datetime import datetime
from unittest.mock import patch

import pytest
from dateutil.relativedelta import relativedelta

from app import db as _db
from app.models.configuracion import Configuracion
from app.models.prestamo import Pago, Prestamo
from app.models.usuario import Usuario
from werkzeug.security import generate_password_hash


MODEL_NOW = datetime(2026, 10, 18, 12)


@pytest.fixture(autouse=True)
def stable_model_clock():
    """Las propiedades usan el mismo reloj que los datos, incluso en servidores UTC."""
    with patch('app.models.prestamo.get_bolivia_time', return_value=MODEL_NOW):
        yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(suffix='X'):
    u = Usuario(
        ci=f'CI-{suffix}',
        nombre=f'Usuario {suffix}',
        password=generate_password_hash('pass'),
        es_admin=False,
        cuenta_activa=False,
    )
    _db.session.add(u)
    _db.session.flush()
    return u


def _make_prestamo(usuario_id, monto=500.0, interes=10.0,
                   fecha_inicio=None, tipo='prendario', numero=99):
    inicio = fecha_inicio or MODEL_NOW
    p = Prestamo(
        numero_prestamo=numero,
        numero_documento=f'DOC-{numero}',
        usuario_id=usuario_id,
        monto_prestado=monto,
        interes_mensual=interes,
        fecha_inicio=inicio,
        fecha_finalizacion=inicio + relativedelta(months=1),
        tipo_prestamo=tipo,
        estado='activo',
    )
    _db.session.add(p)
    _db.session.flush()
    return p


# ===========================================================================
# Préstamo — propiedades de monto
# ===========================================================================

class TestPrestamoMonto:

    def test_monto_a_pagar_prendario_basico(self, app):
        u = _make_user('A')
        p = _make_prestamo(u.id, monto=1000.0, interes=10.0, numero=1)
        # 1000 * (1 + 10/100) = 1100
        assert p.monto_a_pagar == pytest.approx(1100.0)

    def test_monto_a_pagar_interes_15(self, app):
        u = _make_user('B')
        p = _make_prestamo(u.id, monto=200.0, interes=15.0, numero=2)
        # 200 * 1.15 = 230
        assert p.monto_a_pagar == pytest.approx(230.0)

    def test_interes_un_mes(self, app):
        u = _make_user('C')
        p = _make_prestamo(u.id, monto=500.0, interes=10.0, numero=3)
        # 500 * 10% = 50
        assert p.interes_un_mes == pytest.approx(50.0)

    def test_monto_objetivo_prendario_es_monto_a_pagar(self, app):
        u = _make_user('D')
        p = _make_prestamo(u.id, monto=500.0, interes=10.0, tipo='prendario', numero=4)
        assert p.monto_objetivo_actual == p.monto_a_pagar

    def test_monto_liquidacion_con_mora_acumula_intereses(self, app):
        u = _make_user('E')
        ahora = MODEL_NOW
        # Prestamo de hace 3 meses con vencimiento hace 2 meses
        fecha_ini = ahora - relativedelta(months=3)
        fecha_fin = ahora - relativedelta(months=2)
        p = _make_prestamo(u.id, monto=1000.0, interes=10.0, tipo='prendario',
                           fecha_inicio=fecha_ini, numero=5)
        p.fecha_finalizacion = fecha_fin
        # Interes mensual = 100
        # meses_adeudados = 1 + 2 = 3 meses
        assert p.meses_adeudados == 3
        assert p.interes_acumulado_pendiente == pytest.approx(300.0)
        assert p.monto_liquidacion_actual == pytest.approx(1300.0)
        assert p.monto_a_pagar == pytest.approx(1300.0)


# ===========================================================================
# Préstamo — propiedades de fecha y estado
# ===========================================================================

class TestPrestamoFechas:

    def test_esta_vencido_false_cuando_vence_en_futuro(self, app):
        u = _make_user('F')
        p = _make_prestamo(u.id, numero=10)
        # fecha_finalizacion = ahora + 1 mes → no vencido
        assert p.esta_vencido is False

    def test_esta_vencido_true_cuando_ya_vencio(self, app):
        u = _make_user('G')
        ahora = MODEL_NOW
        p = _make_prestamo(u.id, fecha_inicio=ahora - relativedelta(months=2), numero=11)
        # Ajustar vencimiento al pasado
        p.fecha_finalizacion = ahora - relativedelta(days=1)
        assert p.esta_vencido is True

    def test_dias_vencido_cero_si_vigente(self, app):
        u = _make_user('H')
        p = _make_prestamo(u.id, numero=12)
        assert p.dias_vencido == 0

    def test_dias_vencido_positivo_si_vencido(self, app):
        u = _make_user('I')
        ahora = MODEL_NOW
        p = _make_prestamo(u.id, fecha_inicio=ahora - relativedelta(months=2), numero=13)
        p.fecha_finalizacion = ahora - relativedelta(days=10)
        assert p.dias_vencido == 10

    def test_dias_para_vencimiento_positivo(self, app):
        u = _make_user('J')
        p = _make_prestamo(u.id, numero=14)
        # Vence en ~30 días
        assert p.dias_para_vencimiento > 0

    def test_dias_para_vencimiento_negativo_si_vencido(self, app):
        u = _make_user('K')
        ahora = MODEL_NOW
        p = _make_prestamo(u.id, numero=15)
        p.fecha_finalizacion = ahora - relativedelta(days=3)
        assert p.dias_para_vencimiento < 0

    def test_meses_transcurridos_minimo_uno(self, app):
        """Aun en el mismo día el préstamo vale 1 mes mínimo."""
        u = _make_user('L')
        ahora = MODEL_NOW
        p = _make_prestamo(u.id, fecha_inicio=ahora, numero=16)
        # Mockear get_bolivia_time para que devuelva 'ahora'
        with patch('app.models.prestamo.get_bolivia_time', return_value=ahora):
            assert p.meses_transcurridos == 1

    def test_meses_transcurridos_dos_meses(self, app):
        u = _make_user('M')
        inicio = datetime(2026, 1, 15)
        p = _make_prestamo(u.id, fecha_inicio=inicio, numero=17)
        ahora_simulado = datetime(2026, 3, 15)
        with patch('app.models.prestamo.get_bolivia_time', return_value=ahora_simulado):
            assert p.meses_transcurridos == 3  # incluye el mes actual

    def test_monto_liquidacion_con_pagos_previos(self, app):
        """Si se pagaron meses de interés, se descuentan de los meses adeudados."""
        u = _make_user('N')
        ahora = MODEL_NOW
        fecha_ini = ahora - relativedelta(months=4)
        fecha_fin = ahora - relativedelta(months=1)  # vencido hace 1 mes
        p = _make_prestamo(u.id, monto=1000.0, interes=10.0, tipo='prendario',
                           fecha_inicio=fecha_ini, numero=18)
        p.fecha_finalizacion = fecha_fin
        
        from app.models.prestamo import Pago
        from app import db as _db
        pago = Pago(
            prestamo_id=p.id,
            monto_pagado=100.0,
            tipo_pago='interes',
            fecha_pago=ahora - relativedelta(months=2)
        )
        _db.session.add(pago)
        _db.session.commit()
        
        assert p.meses_interes_pagados == 1
        # Con fecha_fin vencida hace 1 mes, diff = 1, adeudados = 1 + 1 = 2 meses
        assert p.meses_adeudados == 2
        assert p.interes_acumulado_pendiente == pytest.approx(200.0)
        assert p.monto_liquidacion_actual == pytest.approx(1200.0)


# ===========================================================================
# Préstamo — pagos
# ===========================================================================

class TestPrestamoPagos:

    def test_total_pagado_sin_pagos_es_cero(self, app):
        u = _make_user('O')
        p = _make_prestamo(u.id, numero=20)
        assert p.total_pagado == pytest.approx(0.0)

    def test_total_pagado_suma_varios_pagos(self, app):
        u = _make_user('P')
        p = _make_prestamo(u.id, monto=500.0, interes=10.0, numero=21)
        _db.session.add(Pago(prestamo_id=p.id, tipo_pago='interes', monto_pagado=50.0))
        _db.session.add(Pago(prestamo_id=p.id, tipo_pago='interes', monto_pagado=50.0))
        _db.session.commit()
        assert p.total_pagado == pytest.approx(100.0)

    def test_monto_pendiente_disminuye_con_pagos(self, app):
        u = _make_user('Q')
        p = _make_prestamo(u.id, monto=500.0, interes=10.0, numero=22)
        pendiente_inicial = p.monto_pendiente_estimado
        _db.session.add(Pago(prestamo_id=p.id, tipo_pago='interes', monto_pagado=50.0))
        _db.session.commit()
        _db.session.refresh(p)
        assert p.monto_pendiente_estimado < pendiente_inicial

    def test_monto_pendiente_no_negativo(self, app):
        u = _make_user('R')
        p = _make_prestamo(u.id, monto=500.0, interes=10.0, numero=23)
        # Pagar más de lo necesario
        _db.session.add(Pago(prestamo_id=p.id, tipo_pago='total', monto_pagado=9999.0))
        p.estado = 'finalizado'
        _db.session.commit()
        _db.session.refresh(p)
        assert p.monto_pendiente_estimado == pytest.approx(0.0)


# ===========================================================================
# Configuración
# ===========================================================================

class TestConfiguracion:

    def test_get_valor_clave_inexistente_retorna_default(self, app):
        result = Configuracion.get_valor('clave_que_no_existe', 'mi_default')
        assert result == 'mi_default'

    def test_get_valor_none_si_no_hay_default(self, app):
        result = Configuracion.get_valor('clave_fantasma')
        assert result is None

    def test_set_y_get_valor(self, app):
        Configuracion.set_valor('interes_prendario', '12.5')
        assert Configuracion.get_valor('interes_prendario') == '12.5'

    def test_update_valor_existente(self, app):
        Configuracion.set_valor('interes_prendario', '10.0')
        Configuracion.set_valor('interes_prendario', '15.0')
        assert Configuracion.get_valor('interes_prendario') == '15.0'

    def test_multiples_claves_independientes(self, app):
        Configuracion.set_valor('clave_a', 'valor_a')
        Configuracion.set_valor('clave_b', 'valor_b')
        assert Configuracion.get_valor('clave_a') == 'valor_a'
        assert Configuracion.get_valor('clave_b') == 'valor_b'


# ===========================================================================
# Préstamo — WhatsApp Recordatorios
# ===========================================================================

class TestPrestamoWhatsApp:

    def test_telefono_whatsapp_bolivia_8_digitos(self, app):
        u = _make_user('WA1')
        u.telefono = '71234567'
        p = _make_prestamo(u.id, numero=201)
        assert p.telefono_whatsapp == '59171234567'

    def test_telefono_whatsapp_con_mas_y_espacios(self, app):
        u = _make_user('WA2')
        u.telefono = '+591 6987-6543'
        p = _make_prestamo(u.id, numero=202)
        assert p.telefono_whatsapp == '59169876543'

    def test_telefono_whatsapp_invalido_o_vacio(self, app):
        u = _make_user('WA3')
        u.telefono = '123'
        p = _make_prestamo(u.id, numero=203)
        assert p.telefono_whatsapp is None

        u.telefono = None
        assert p.telefono_whatsapp is None

    def test_whatsapp_mensaje_vencido_incluye_meses_y_decomiso(self, app):
        u = _make_user('WA4')
        u.nombre = 'Juan Perez'
        u.telefono = '77889900'
        ahora = MODEL_NOW
        # Vencido hace 2 meses (total 3 meses adeudados)
        p = _make_prestamo(u.id, monto=1000.0, interes=10.0,
                           fecha_inicio=ahora - relativedelta(months=3), numero=204)
        p.fecha_finalizacion = ahora - relativedelta(months=2)

        msg = p.whatsapp_mensaje
        assert 'Juan Perez' in msg
        assert 'DOC-204' in msg
        assert '3 mes(es)' in msg
        assert 'decomiso' in msg.lower()
        assert '300.00' in msg  # interes acumulado

    def test_whatsapp_mensaje_al_dia_recordatorio(self, app):
        u = _make_user('WA5')
        u.nombre = 'Maria Lopez'
        u.telefono = '71122334'
        p = _make_prestamo(u.id, monto=500.0, interes=10.0, numero=205)

        msg = p.whatsapp_mensaje
        assert 'Maria Lopez' in msg
        assert 'Bs. 50.00' in msg
        assert 'decomiso' in msg.lower() or 'garantía' in msg.lower()

    def test_whatsapp_url_correcta(self, app):
        u = _make_user('WA6')
        u.telefono = '75566778'
        p = _make_prestamo(u.id, numero=206)

        url = p.whatsapp_url
        assert url.startswith('https://wa.me/59175566778?text=')
        assert 'DOC-206' in url

    def test_whatsapp_url_none_sin_telefono(self, app):
        u = _make_user('WA7')
        u.telefono = None
        p = _make_prestamo(u.id, numero=207)
        assert p.whatsapp_url is None
