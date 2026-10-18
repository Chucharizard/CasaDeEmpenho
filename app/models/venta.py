from app import db
from app.utils import get_bolivia_time


class Venta(db.Model):
    __tablename__ = 'venta'

    id = db.Column(db.Integer, primary_key=True)
    producto_id = db.Column(db.Integer, db.ForeignKey('producto_venta.id'), nullable=False, index=True)
    operacion_id = db.Column(db.String(64), unique=True, nullable=False)
    nombre = db.Column(db.String(100), nullable=False)
    descripcion = db.Column(db.Text)
    cantidad = db.Column(db.Integer, nullable=False, default=1)
    precio_unitario = db.Column(db.Float, nullable=False)
    costo_unitario = db.Column(db.Float, nullable=False, default=0)
    fecha_venta = db.Column(db.DateTime, nullable=False, default=get_bolivia_time, index=True)
    producto = db.relationship('ProductoVenta', backref='ventas')

    @property
    def precio(self):
        return round(self.precio_unitario * self.cantidad, 2)

    @property
    def precio_compra(self):
        return round(self.costo_unitario * self.cantidad, 2)

    @property
    def ganancia(self):
        return round(self.precio - self.precio_compra, 2)

    estado = 'vendido'


class RegistroAuditoria(db.Model):
    __tablename__ = 'registro_auditoria'

    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.DateTime, nullable=False, default=get_bolivia_time)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'))
    entidad = db.Column(db.String(32), nullable=False)
    entidad_id = db.Column(db.Integer, nullable=False, index=True)
    accion = db.Column(db.String(100), nullable=False)
    antes_json = db.Column(db.Text)
    despues_json = db.Column(db.Text)
    motivo = db.Column(db.Text)
