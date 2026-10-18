import json
import re
from datetime import date, datetime

from flask_login import current_user
from flask import has_request_context

from app import db
from app.models import ProductoVenta, RegistroAuditoria
from app.utils import get_bolivia_time


def validate_operation_id(value):
    if not re.fullmatch(r'[A-Za-z0-9_-]{16,64}', value or ''):
        raise ValueError('El formulario de la operación expiró. Recarga la página e intenta nuevamente.')
    return value


def audit_snapshot(obj):
    ignored = {'password', 'comprobante_json'}
    return {column.name: getattr(obj, column.name) for column in obj.__table__.columns if column.name not in ignored}


def record_change(obj, action, before=None, motivo=None):
    def encode(value):
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        raise TypeError(type(value).__name__)
    actor = current_user.id if has_request_context() and current_user.is_authenticated else None
    db.session.add(RegistroAuditoria(
        usuario_id=actor, entidad=obj.__tablename__, entidad_id=obj.id, accion=action,
        antes_json=json.dumps(before, default=encode, ensure_ascii=False) if before else None,
        despues_json=json.dumps(audit_snapshot(obj), default=encode, ensure_ascii=False),
        motivo=motivo or None,
    ))


def transition_loan(prestamo, estado, precio_venta=None, motivo=None, before=None):
    before = before if before is not None else audit_snapshot(prestamo)
    producto = ProductoVenta.query.filter_by(prestamo_origen_id=prestamo.id).first()
    if prestamo.estado == 'decomisado' and estado != 'decomisado' and producto:
        if producto.ventas or producto.estado == 'vendido':
            raise ValueError('La garantía ya tiene ventas registradas. No se puede reactivar ni liberar el préstamo.')
        db.session.delete(producto)
    if estado == 'decomisado' and not producto:
        articulos = prestamo.articulos
        nombre = ', '.join(a.nombre for a in articulos) or f'Garantía {prestamo.numero_documento}'
        descripcion = '; '.join(a.descripcion or a.nombre for a in articulos) or nombre
        db.session.add(ProductoVenta(
            nombre=nombre[:100], descripcion=descripcion,
            precio=precio_venta if precio_venta is not None else prestamo.monto_prestado,
            precio_compra=prestamo.monto_prestado, stock=1, stock_inicial=1,
            proveedor=f'Empeño {prestamo.numero_documento}', tipo='venta', estado='disponible',
            prestamo_origen_id=prestamo.id,
            fotos=articulos[0].fotos if articulos else None,
            fecha_publicacion=get_bolivia_time(),
        ))
    prestamo.estado = estado
    for articulo in prestamo.articulos:
        articulo.estado = {'finalizado': 'liberado', 'decomisado': 'decomisado'}.get(estado, 'empenado')
    record_change(prestamo, f'Estado a {estado}', before, motivo)
