from app.utils import get_bolivia_time
from datetime import datetime, timedelta

from flask import render_template
from flask_login import login_required

from app.models import Pago, Prestamo
from app.routes.admin_shared import admin, admin_required


@admin.route('/reportes')
@login_required
@admin_required
def reportes():
    ahora = get_bolivia_time()
    inicio_hoy = datetime.combine(ahora.date(), datetime.min.time())
    inicio_mes = datetime(ahora.year, ahora.month, 1)
    limite_vencimiento = ahora + timedelta(days=7)

    pagos_hoy = Pago.query.filter(Pago.fecha_pago >= inicio_hoy).order_by(Pago.fecha_pago.desc()).all()
    pagos_mes = Pago.query.filter(Pago.fecha_pago >= inicio_mes).order_by(Pago.fecha_pago.desc()).all()
    pagos_recientes = Pago.query.order_by(Pago.fecha_pago.desc()).limit(20).all()

    prestamos_por_vencer = (
        Prestamo.query.filter(
            Prestamo.estado == 'activo',
            Prestamo.fecha_finalizacion >= ahora,
            Prestamo.fecha_finalizacion <= limite_vencimiento,
        )
        .order_by(Prestamo.fecha_finalizacion.asc())
        .all()
    )

    prestamos_vencidos = (
        Prestamo.query.filter(
            Prestamo.estado.in_(['activo', 'retencion']),
            Prestamo.fecha_finalizacion < ahora,
        )
        .order_by(Prestamo.fecha_finalizacion.asc())
        .all()
    )

    resumen = {
        'cobrado_hoy': round(sum(item.monto_pagado for item in pagos_hoy), 2),
        'cobrado_mes': round(sum(item.monto_pagado for item in pagos_mes), 2),
        'cantidad_pagos_hoy': len(pagos_hoy),
        'cantidad_pagos_mes': len(pagos_mes),
        'prestamos_por_vencer': len(prestamos_por_vencer),
        'prestamos_vencidos': len(prestamos_vencidos),
        'pagos_interes_mes': round(sum(item.monto_pagado for item in pagos_mes if item.tipo_pago == 'interes'), 2),
        'pagos_total_mes': round(sum(item.monto_pagado for item in pagos_mes if item.tipo_pago == 'total'), 2),
    }

    return render_template(
        'admin/reportes.html',
        resumen=resumen,
        pagos_hoy=pagos_hoy,
        pagos_recientes=pagos_recientes,
        prestamos_por_vencer=prestamos_por_vencer,
        prestamos_vencidos=prestamos_vencidos,
        ahora=ahora,
    )
