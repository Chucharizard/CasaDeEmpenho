"""Datos inmutables compartidos por PDF, PNG y mensajes de un pago."""
import json
from datetime import datetime


DATE_FIELDS = ('fecha_pago', 'fecha_vencimiento', 'fecha_inicio')


def _interest_summary(data):
    """Cuotas tras el pago, con la misma regla de mora y los valores de esa emisión."""
    if data.get('historico_sin_plazo'):
        return None
    paid, due = data.get('fecha_pago'), data.get('fecha_vencimiento')
    if not isinstance(paid, datetime) or not isinstance(due, datetime):
        return None
    if data.get('monto_prestado') is None or data.get('interes_mensual') is None:
        return None
    fee = round(data['monto_prestado'] * (data['interes_mensual'] / 100), 2)
    months = 0
    if data.get('tipo_pago') != 'total' and paid > due:
        diff = (paid.year - due.year) * 12 + paid.month - due.month
        if paid.day < due.day:
            diff -= 1
        months = 1 + max(0, diff)
    return {'cuota_mensual': fee, 'meses_pendientes': months,
            'interes_pendiente': round(fee * months, 2)}


def _receipt_context(data, pago, prestamo):
    """Añade contexto de emisión, sin consultar saldos ni pagos posteriores."""
    from app.models import Pago

    data['fecha_inicio'] = prestamo.fecha_inicio
    data['resumen_interes'] = _interest_summary(data)
    until = data.get('fecha_pago')
    if pago.id is None or not isinstance(until, datetime):
        data['historial_pagos'] = []
        data['total_pagos_hasta_recibo'] = 0
        return
    query = Pago.query.filter(
        Pago.prestamo_id == prestamo.id,
        Pago.id <= pago.id, Pago.fecha_pago <= until,
    )
    data['total_pagos_hasta_recibo'] = query.count()
    recent = query.order_by(Pago.fecha_pago.desc(), Pago.id.desc()).limit(5).all()
    data['historial_pagos'] = [{
        'numero_recibo': f'REC-{item.id:05d}', 'fecha_pago': item.fecha_pago,
        'tipo_pago': item.tipo_pago, 'meses_pagados': item.meses_pagados,
        'monto_pagado': item.monto_pagado, 'actual': item.id == pago.id,
    } for item in reversed(recent)]


def capture_receipt(pago, prestamo, meses=None, importe_requerido=None, legacy=False, persist=True):
    usuario = prestamo.usuario
    data = {
        'numero_recibo': f'REC-{pago.id:05d}',
        'fecha_pago': pago.fecha_pago,
        'numero_documento': prestamo.numero_documento,
        'numero_prestamo': prestamo.numero_prestamo,
        'nombre_cliente': usuario.nombre if usuario else 'N/A',
        'ci_cliente': usuario.ci if usuario else 'N/A',
        'telefono_cliente': usuario.telefono if usuario and usuario.telefono else 'No registrado',
        'articulos_descripcion': ', '.join(a.nombre for a in prestamo.articulos) or 'Garantía prendaria',
        'tipo_pago': pago.tipo_pago,
        'meses_pagados': meses,
        'monto_pagado': pago.monto_pagado,
        'monto_prestado': prestamo.monto_prestado,
        'interes_mensual': prestamo.interes_mensual,
        'fecha_vencimiento': None if legacy else prestamo.fecha_finalizacion,
        'excedente': round(max(0, pago.monto_pagado - importe_requerido), 2) if importe_requerido is not None else None,
        'historico_sin_plazo': legacy,
    }
    _receipt_context(data, pago, prestamo)
    data['version_recibo'] = 2
    if persist:
        pago.comprobante_json = json.dumps(data, ensure_ascii=False, default=lambda v: v.isoformat())
    return data


def build_receipt_data(pago):
    if pago.comprobante_json:
        data = json.loads(pago.comprobante_json)
    else:
        # Datos anteriores al registro de plazos: nunca inferir meses o vencimiento.
        data = capture_receipt(pago, pago.prestamo, legacy=True, persist=False)
    for field in DATE_FIELDS:
        if isinstance(data.get(field), str):
            data[field] = datetime.fromisoformat(data[field])
    if data.get('version_recibo', 1) < 2:
        # Recibos ya emitidos: se conserva su JSON y se amplía solo la presentación.
        # Capital, tasa, vencimiento y fecha de cálculo provienen de la instantánea.
        _receipt_context(data, pago, pago.prestamo)
    for item in data.get('historial_pagos', []):
        if isinstance(item.get('fecha_pago'), str):
            item['fecha_pago'] = datetime.fromisoformat(item['fecha_pago'])
    return data


def payment_message(pago):
    data = build_receipt_data(pago)
    fecha = data['fecha_pago'].strftime('%d/%m/%Y %H:%M') if data['fecha_pago'] else ''
    lines = [
        '🧾 *COMPROBANTE DE PAGO - PANDA | CASA DE EMPEÑO*',
        f"Estimado/a *{data['nombre_cliente']}*, confirmamos la recepción de su pago.",
        f"• *N° Recibo:* {data['numero_recibo']}",
        f'• *Fecha y Hora:* {fecha}',
        f"• *Préstamo:* {data['numero_documento']}",
        f"• *Garantía:* {data['articulos_descripcion']}",
        f"• *Monto Cancelado:* *Bs. {data['monto_pagado']:.2f}*",
    ]
    if pago.tipo_pago == 'total':
        lines.extend(['• *Concepto:* Liquidación Total y Retiro de Prenda', '✅ *PRENDA LIBERADA Y DISPONIBLE PARA RETIRO*'])
    else:
        meses = data.get('meses_pagados')
        lines.append(f'• *Concepto:* Pago de Interés ({meses} mes/es) - Renovación de Plazo' if meses is not None else '• *Concepto:* Pago de Interés (registro histórico)')
        vencimiento = data.get('fecha_vencimiento')
        lines.append(f"• *Próximo Vencimiento:* *{vencimiento.strftime('%d/%m/%Y')}*" if vencimiento else '• Plazo original no registrado en el comprobante histórico.')
        # Una renovación parcial de mora no implica que el préstamo esté al día.
    if data.get('excedente'):
        lines.append(f"• Importe adicional recibido: Bs. {data['excedente']:.2f}; no amplía los meses indicados.")
    return '\n'.join(lines)
