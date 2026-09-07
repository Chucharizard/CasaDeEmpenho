from app import db


class Articulo(db.Model):
    __tablename__ = 'articulo'

    id = db.Column(db.Integer, primary_key=True)
    prestamo_id = db.Column(db.Integer, db.ForeignKey('prestamo.id'), nullable=False)
    nombre = db.Column(db.String(100), nullable=False)
    descripcion = db.Column(db.Text)
    fotos = db.Column(db.String(500))
    estado = db.Column(db.String(20), default='empenado')

    def __repr__(self):
        return f'<Articulo {self.nombre}>'
