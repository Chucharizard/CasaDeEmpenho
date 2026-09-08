from app.utils import get_bolivia_time
import os
import secrets
from datetime import datetime
from functools import wraps

from dateutil.relativedelta import relativedelta
from flask import Blueprint, flash, redirect, url_for
from flask_login import current_user
from werkzeug.security import generate_password_hash

from config import Config

admin = Blueprint('admin', __name__, url_prefix=Config.ADMIN_PREFIX)

VALID_LOAN_STATES = {'activo', 'retencion', 'finalizado', 'decomisado'}
VALID_PAYMENT_TYPES = {'interes', 'total'}
MAX_ALLOWED_INTEREST = 25.0


def obtener_fecha_actual():
    return get_bolivia_time()


def obtener_fecha_vencimiento(fecha_inicio):
    return fecha_inicio + relativedelta(months=1)


def admin_required(func):
    @wraps(func)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.es_admin:
            flash('Acceso restringido', 'danger')
            return redirect(url_for('auth.login'))
        return func(*args, **kwargs)

    return decorated_function


def clean_text(value):
    return (value or '').strip()


def create_inactive_password_hash():
    return generate_password_hash(secrets.token_hex(16))


def parse_positive_float(value, field_name):
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'El campo {field_name} debe ser numerico.') from exc

    if parsed <= 0:
        raise ValueError(f'El campo {field_name} debe ser mayor a 0.')

    return round(parsed, 2)


def parse_non_negative_int(value, field_name):
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'El campo {field_name} debe ser entero.') from exc

    if parsed < 0:
        raise ValueError(f'El campo {field_name} no puede ser negativo.')

    return parsed


def get_tasa_configurada(clave, default):
    """Lee una tasa guardada en la tabla configuracion (clave/valor).

    Devuelve el default si no esta configurada o el valor guardado no es
    numerico. Import local para evitar import circular durante el arranque.
    """
    from app.models import Configuracion

    valor = Configuracion.get_valor(clave, None)
    if valor is None:
        return default
    try:
        return round(float(valor), 2)
    except (TypeError, ValueError):
        return default


def parse_interest(value, max_allowed=None):
    interest = parse_positive_float(value, 'interes')
    limite = max_allowed if max_allowed is not None else get_tasa_configurada('interes_maximo', MAX_ALLOWED_INTEREST)
    if interest > limite:
        raise ValueError(f'El interes no puede superar {limite:.1f}%.')
    return interest


def resolve_total_payment_due(prestamo):
    return prestamo.monto_liquidacion_actual


def build_prestamo_alerts(prestamo, hoy=None):
    hoy = hoy or get_bolivia_time()
    alerts = []

    if prestamo.estado == 'decomisado':
        alerts.append({
            'level': 'danger',
            'icon': 'bi-box-arrow-right',
            'title': 'Artículo Decomisado',
            'message': 'Este préstamo fue decomisado y su garantía pasó al inventario de venta.',
        })
        return alerts

    if prestamo.estado == 'finalizado':
        alerts.append({
            'level': 'success',
            'icon': 'bi-check-circle-fill',
            'title': 'Préstamo Liquidado',
            'message': f'Cancelado en su totalidad con Bs. {prestamo.total_pagado:.2f} registrados en pagos.',
        })
        return alerts

    if prestamo.dias_para_vencimiento < 0:
        meses_txt = f"{prestamo.meses_adeudados} mes{'es' if prestamo.meses_adeudados != 1 else ''}"
        alerts.append({
            'level': 'danger',
            'icon': 'bi-exclamation-octagon-fill',
            'title': 'Préstamo Vencido / En Retención',
            'message': f'Venció hace {prestamo.dias_vencido} día(s). Adeuda {meses_txt} de interés acumulado (Bs. {prestamo.interes_acumulado_pendiente:.2f}).',
        })
    elif prestamo.dias_para_vencimiento == 0:
        alerts.append({
            'level': 'warning',
            'icon': 'bi-exclamation-triangle-fill',
            'title': 'Vence Hoy',
            'message': 'Fecha límite alcanzada hoy. Se requiere renovación de interés o liquidación.',
        })
    elif prestamo.dias_para_vencimiento <= 7:
        alerts.append({
            'level': 'warning',
            'icon': 'bi-clock-history',
            'title': 'Próximo a Vencer',
            'message': f'Quedan {prestamo.dias_para_vencimiento} día(s) para la fecha de vencimiento.',
        })

    return alerts


def build_prestamo_timeline(prestamo):
    items = [{
        'date': prestamo.fecha_inicio,
        'icon': 'bi bi-file-earmark-plus',
        'title': f'Creacion del prestamo {prestamo.numero_documento}',
        'description': f'Capital inicial Bs. {prestamo.monto_prestado:.2f}.',
        'variant': 'primary',
    }]

    for pago in sorted(prestamo.pagos, key=lambda item: item.fecha_pago):
        if pago.tipo_pago == 'interes':
            description = f'Pago de interes por Bs. {pago.monto_pagado:.2f}.'
            icon = 'bi bi-cash-coin'
            variant = 'warning'
        else:
            description = f'Pago total por Bs. {pago.monto_pagado:.2f}.'
            icon = 'bi bi-check-circle'
            variant = 'success'

        items.append({
            'date': pago.fecha_pago,
            'icon': icon,
            'title': f'Pago {pago.tipo_pago}',
            'description': description,
            'variant': variant,
        })

    items.append({
        'date': prestamo.fecha_finalizacion,
        'icon': 'bi bi-calendar-event',
        'title': 'Fecha de vencimiento vigente',
        'description': prestamo.fecha_finalizacion.strftime('%d/%m/%Y'),
        'variant': 'secondary',
    })

    items.sort(key=lambda item: item['date'], reverse=True)
    return items


def list_backup_files():
    if not os.path.isdir(Config.BACKUP_DIR):
        return []

    backups = []
    for entry in os.listdir(Config.BACKUP_DIR):
        if not entry.lower().endswith('.db'):
            continue

        path = os.path.join(Config.BACKUP_DIR, entry)
        if not os.path.isfile(path):
            continue

        stat_info = os.stat(path)
        backups.append({
            'name': entry,
            'path': path,
            'size_mb': round(stat_info.st_size / (1024 * 1024), 2),
            'modified_at': datetime.fromtimestamp(stat_info.st_mtime),
        })

    backups.sort(key=lambda item: item['modified_at'], reverse=True)
    return backups


def get_safe_backup_path(filename):
    safe_name = os.path.basename(filename or '')
    if not safe_name:
        return None

    candidate = os.path.abspath(os.path.join(Config.BACKUP_DIR, safe_name))
    backup_root = os.path.abspath(Config.BACKUP_DIR)
    if not candidate.startswith(backup_root):
        return None
    if not os.path.isfile(candidate):
        return None
    return candidate
