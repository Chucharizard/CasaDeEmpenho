from app import db
from flask_login import UserMixin


class Usuario(UserMixin, db.Model):
    __tablename__ = 'usuario'

    id = db.Column(db.Integer, primary_key=True)
    ci = db.Column(db.String(20), unique=True, nullable=False)
    nombre = db.Column(db.String(100), nullable=False)
    telefono = db.Column(db.String(15))
    password = db.Column(db.String(200), nullable=False)
    es_admin = db.Column(db.Boolean, default=False)
    cuenta_activa = db.Column(db.Boolean, default=False)
    email = db.Column(db.String(120), unique=True, nullable=True)

    prestamos = db.relationship('Prestamo', backref='usuario', lazy=True)

    def __repr__(self):
        return f'<Usuario {self.nombre}>'
