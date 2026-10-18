"""Comprobantes históricos, operaciones únicas, ventas y trazabilidad."""
from alembic import op
import sqlalchemy as sa

revision = 'ce_20261017_01'
down_revision = 'f8a9b0c1d2e3'
branch_labels = None
depends_on = None


def upgrade():
    for column in (
        sa.Column('meses_pagados', sa.Integer), sa.Column('operacion_id', sa.String(64)),
        sa.Column('comprobante_json', sa.Text),
        sa.Column('whatsapp_estado', sa.String(24), nullable=False, server_default='no_solicitado'),
        sa.Column('whatsapp_error', sa.Text), sa.Column('whatsapp_ultimo_intento', sa.DateTime),
        sa.Column('whatsapp_intentos', sa.Integer, nullable=False, server_default='0'),
    ):
        op.add_column('pago', column)
    op.create_index('ix_pago_operacion_id', 'pago', ['operacion_id'], unique=True)
    with op.batch_alter_table('producto_venta') as batch:
        batch.add_column(sa.Column('prestamo_origen_id', sa.Integer))
        batch.create_foreign_key('fk_producto_prestamo', 'prestamo', ['prestamo_origen_id'], ['id'])
        batch.create_unique_constraint('uq_producto_prestamo', ['prestamo_origen_id'])
    op.create_table('venta',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('producto_id', sa.Integer, sa.ForeignKey('producto_venta.id'), nullable=False),
        sa.Column('operacion_id', sa.String(64), unique=True, nullable=False),
        sa.Column('nombre', sa.String(100), nullable=False), sa.Column('descripcion', sa.Text),
        sa.Column('cantidad', sa.Integer, nullable=False), sa.Column('precio_unitario', sa.Float, nullable=False),
        sa.Column('costo_unitario', sa.Float, nullable=False), sa.Column('fecha_venta', sa.DateTime, nullable=False))
    op.create_index('ix_venta_producto_id', 'venta', ['producto_id'])
    op.create_index('ix_venta_fecha_venta', 'venta', ['fecha_venta'])
    op.create_table('registro_auditoria',
        sa.Column('id', sa.Integer, primary_key=True), sa.Column('fecha', sa.DateTime, nullable=False),
        sa.Column('usuario_id', sa.Integer, sa.ForeignKey('usuario.id')),
        sa.Column('entidad', sa.String(32), nullable=False), sa.Column('entidad_id', sa.Integer, nullable=False),
        sa.Column('accion', sa.String(100), nullable=False), sa.Column('antes_json', sa.Text),
        sa.Column('despues_json', sa.Text), sa.Column('motivo', sa.Text))
    op.create_index('ix_registro_auditoria_entidad_id', 'registro_auditoria', ['entidad_id'])
    # No inferir importes de ventas pasadas ni plazos históricos de los pagos.


def downgrade():
    raise RuntimeError('Esta revisión conserva evidencia financiera. Restaurar un respaldo en lugar de eliminarla.')
