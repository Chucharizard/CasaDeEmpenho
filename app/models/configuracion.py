from app import db

class Configuracion(db.Model):
    __tablename__ = 'configuracion'
    
    id = db.Column(db.Integer, primary_key=True)
    clave = db.Column(db.String(50), unique=True, nullable=False)
    valor = db.Column(db.String(255), nullable=True)

    @staticmethod
    def get_valor(clave, default=None):
        config = Configuracion.query.filter_by(clave=clave).first()
        return config.valor if config else default

    @staticmethod
    def set_valor(clave, valor):
        config = Configuracion.query.filter_by(clave=clave).first()
        if config:
            config.valor = valor
        else:
            config = Configuracion(clave=clave, valor=valor)
            db.session.add(config)
        db.session.commit()
