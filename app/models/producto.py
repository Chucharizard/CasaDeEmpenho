from app.utils import get_bolivia_time
from app import db


class ProductoVenta(db.Model):
    __tablename__ = 'producto_venta'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    descripcion = db.Column(db.Text)
    precio = db.Column(db.Float, nullable=False)
    fotos = db.Column(db.String(500))
    fecha_publicacion = db.Column(db.DateTime, default=get_bolivia_time)
    estado = db.Column(db.String(20), default='disponible')
    destacado = db.Column(db.Boolean, default=False)
    tipo = db.Column(db.String(20))
    precio_compra = db.Column(db.Float)
    stock = db.Column(db.Integer, default=1)
    proveedor = db.Column(db.String(100))
    fecha_venta = db.Column(db.DateTime)
    stock_inicial = db.Column(db.Integer)

    def __repr__(self):
        return f'<ProductoVenta {self.nombre}>'
