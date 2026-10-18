"""Esquema heredado reconocido; las instalaciones nuevas usan initialize_database."""
from alembic import op
import sqlalchemy as sa

revision = 'f8a9b0c1d2e3'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('usuario',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('ci', sa.String(20), nullable=False, unique=True),
        sa.Column('nombre', sa.String(100), nullable=False),
        sa.Column('telefono', sa.String(15)), sa.Column('password', sa.String(200), nullable=False),
        sa.Column('es_admin', sa.Boolean), sa.Column('cuenta_activa', sa.Boolean),
        sa.Column('email', sa.String(120), unique=True))
    op.create_table('prestamo',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('numero_prestamo', sa.Integer, unique=True, nullable=False),
        sa.Column('numero_documento', sa.String(20), unique=True, nullable=False),
        sa.Column('usuario_id', sa.Integer, sa.ForeignKey('usuario.id'), nullable=False),
        sa.Column('monto_prestado', sa.Float, nullable=False), sa.Column('interes_mensual', sa.Float),
        sa.Column('fecha_inicio', sa.DateTime, nullable=False), sa.Column('fecha_finalizacion', sa.DateTime, nullable=False),
        sa.Column('ultimo_pago', sa.DateTime), sa.Column('tipo_ultimo_pago', sa.String(20)),
        sa.Column('monto_ultimo_pago', sa.Float), sa.Column('estado', sa.String(20)), sa.Column('tipo_prestamo', sa.String(20)))
    op.create_table('articulo',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('prestamo_id', sa.Integer, sa.ForeignKey('prestamo.id'), nullable=False),
        sa.Column('nombre', sa.String(100), nullable=False), sa.Column('descripcion', sa.Text),
        sa.Column('fotos', sa.String(500)), sa.Column('estado', sa.String(20)))
    op.create_table('pago',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('prestamo_id', sa.Integer, sa.ForeignKey('prestamo.id'), nullable=False),
        sa.Column('fecha_pago', sa.DateTime), sa.Column('tipo_pago', sa.String(20), nullable=False),
        sa.Column('monto_pagado', sa.Float, nullable=False))
    op.create_table('producto_venta',
        sa.Column('id', sa.Integer, primary_key=True), sa.Column('nombre', sa.String(100), nullable=False),
        sa.Column('descripcion', sa.Text), sa.Column('precio', sa.Float, nullable=False),
        sa.Column('fotos', sa.String(500)), sa.Column('fecha_publicacion', sa.DateTime),
        sa.Column('estado', sa.String(20)), sa.Column('destacado', sa.Boolean), sa.Column('tipo', sa.String(20)),
        sa.Column('precio_compra', sa.Float), sa.Column('stock', sa.Integer), sa.Column('proveedor', sa.String(100)),
        sa.Column('fecha_venta', sa.DateTime), sa.Column('stock_inicial', sa.Integer))
    op.create_table('configuracion', sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('clave', sa.String(50), unique=True, nullable=False), sa.Column('valor', sa.String(255)))


def downgrade():
    raise RuntimeError('La eliminación del esquema requiere una restauración explícita desde respaldo.')
