"""La cuota e historial del recibo corresponden al momento de la emisión."""
import json
from datetime import datetime
from uuid import uuid4
import pytest
from dateutil.relativedelta import relativedelta

from app import db
from app.models import Pago
from app.services.receipt_service import build_receipt_data, capture_receipt, _interest_summary


@pytest.mark.parametrize('due,months', [
    (datetime(2026, 7, 13), 4),
    (datetime(2026, 9, 20), 1),
    (datetime(2026, 10, 17, 18), 0),
    (datetime(2026, 11, 13), 0),
    (datetime(2026, 1, 31), 9),
])
def test_resumen_respeta_meses_de_mora(due, months):
    data = {'tipo_pago': 'interes', 'monto_prestado': 2100, 'interes_mensual': 10,
            'fecha_pago': datetime(2026, 10, 17, 17, 30), 'fecha_vencimiento': due}
    summary = _interest_summary(data)
    assert summary == {'cuota_mensual': 210, 'meses_pendientes': months, 'interes_pendiente': 210 * months}


def test_resumen_no_infiere_saldo_sin_plazo():
    assert _interest_summary({'historico_sin_plazo': True}) is None
    assert _interest_summary({'monto_prestado': 2100, 'interes_mensual': 10}) is None


def test_liquidado_sin_interes_pendiente():
    summary = _interest_summary({'tipo_pago': 'total', 'monto_prestado': 2100, 'interes_mensual': 10,
                                'fecha_pago': datetime(2026, 10, 17), 'fecha_vencimiento': datetime(2026, 1, 1)})
    assert summary['interes_pendiente'] == 0


def test_pago_real_captura_mismo_saldo_que_el_prestamo(admin_client, prestamo_prendario, monkeypatch):
    loan = prestamo_prendario
    now = datetime(2026, 10, 17, 17, 30)
    monkeypatch.setattr('app.models.prestamo.get_bolivia_time', lambda: now)
    monkeypatch.setattr('app.routes.admin_loans.get_bolivia_time', lambda: now)
    loan.fecha_inicio = datetime(2026, 3, 13)
    loan.fecha_finalizacion = datetime(2026, 4, 13)
    loan.monto_prestado = 2100
    loan.interes_mensual = 10
    db.session.commit()
    response = admin_client.post(f'/admin/registrar-pago/{loan.id}', data={
        'tipo_pago': 'interes', 'monto': '420', 'meses_interes': '2', 'operacion_id': uuid4().hex,
    })
    assert response.status_code == 302
    db.session.expire_all()
    receipt = build_receipt_data(Pago.query.filter_by(prestamo_id=loan.id).one())
    assert receipt['resumen_interes']['cuota_mensual'] == loan.interes_un_mes
    assert receipt['resumen_interes']['meses_pendientes'] == loan.meses_adeudados == 5
    assert receipt['resumen_interes']['interes_pendiente'] == loan.interes_acumulado_pendiente == 1050


def test_snapshot_conserva_historial_fecha_y_cuota(admin_client, prestamo_prendario):
    loan = prestamo_prendario
    now = datetime(2026, 10, 17, 17, 30)
    loan.fecha_inicio = datetime(2026, 1, 13)
    loan.fecha_finalizacion = datetime(2026, 7, 13)
    loan.monto_prestado = 2100
    loan.interes_mensual = 10
    for i in range(8):
        db.session.add(Pago(prestamo_id=loan.id, fecha_pago=now-relativedelta(days=8-i),
                            tipo_pago='interes', monto_pagado=210, meses_pagados=1))
    # Un registro futuro no puede aparecer en el comprobante de hoy.
    db.session.add(Pago(prestamo_id=loan.id, fecha_pago=now+relativedelta(days=1),
                        tipo_pago='interes', monto_pagado=210, meses_pagados=1))
    current = Pago(prestamo_id=loan.id, fecha_pago=now, tipo_pago='interes', monto_pagado=420, meses_pagados=2)
    db.session.add(current)
    db.session.flush()
    capture_receipt(current, loan, meses=2, importe_requerido=420)
    db.session.commit()
    original = build_receipt_data(current)
    assert original['fecha_inicio'] == datetime(2026, 1, 13)
    assert original['resumen_interes']['interes_pendiente'] == 840
    assert original['total_pagos_hasta_recibo'] == 9
    assert len(original['historial_pagos']) == 5
    assert original['historial_pagos'][-1]['actual'] is True
    assert all(p['fecha_pago'] <= now for p in original['historial_pagos'])
    saved = current.comprobante_json
    loan.fecha_inicio = datetime(2025, 1, 1)
    loan.interes_mensual = 20
    loan.fecha_finalizacion = now+relativedelta(months=5)
    # Incluso un pago añadido después con la misma hora no se incorpora al recibo anterior.
    db.session.add(Pago(prestamo_id=loan.id, fecha_pago=now, tipo_pago='interes', monto_pagado=420, meses_pagados=1))
    db.session.commit()
    assert build_receipt_data(current) == original
    assert current.comprobante_json == saved


def test_recibo_anterior_amplia_presentacion_sin_reescribir_snapshot(prestamo_prendario):
    loan = prestamo_prendario
    now = datetime(2026, 10, 17, 17, 30)
    loan.fecha_inicio = datetime(2026, 1, 13)
    current = Pago(prestamo_id=loan.id, fecha_pago=now, tipo_pago='interes', monto_pagado=420, meses_pagados=2)
    db.session.add(current)
    db.session.flush()
    snapshot = {'numero_recibo': f'REC-{current.id:05d}', 'tipo_pago': 'interes', 'meses_pagados': 2,
                'fecha_pago': now.isoformat(), 'fecha_vencimiento': datetime(2026, 7, 13).isoformat(),
                'monto_prestado': 2100, 'interes_mensual': 10}
    current.comprobante_json = json.dumps(snapshot)
    saved = current.comprobante_json
    # El préstamo actual ya tiene otra tasa y otro vencimiento.
    loan.interes_mensual = 20
    loan.fecha_finalizacion = now+relativedelta(months=3)
    db.session.add(Pago(prestamo_id=loan.id, fecha_pago=now+relativedelta(days=1),
                        tipo_pago='interes', monto_pagado=1000, meses_pagados=1))
    db.session.add(Pago(prestamo_id=loan.id, fecha_pago=now-relativedelta(days=1),
                        tipo_pago='interes', monto_pagado=500, meses_pagados=1))
    db.session.commit()
    data = build_receipt_data(current)
    assert data['resumen_interes'] == {'cuota_mensual': 210, 'meses_pendientes': 4, 'interes_pendiente': 840}
    assert len(data['historial_pagos']) == 1
    assert data['historial_pagos'][0]['actual']
    assert current.comprobante_json == saved
