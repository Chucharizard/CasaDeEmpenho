from app.utils import get_bolivia_time

from app import db


class Prestamo(db.Model):
    __tablename__ = 'prestamo'

    id = db.Column(db.Integer, primary_key=True)
    numero_prestamo = db.Column(db.Integer, unique=True, nullable=False)
    numero_documento = db.Column(db.String(20), unique=True, nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    monto_prestado = db.Column(db.Float, nullable=False)
    interes_mensual = db.Column(db.Float, default=10.0)
    fecha_inicio = db.Column(db.DateTime, nullable=False, default=get_bolivia_time)
    fecha_finalizacion = db.Column(db.DateTime, nullable=False)
    ultimo_pago = db.Column(db.DateTime)
    tipo_ultimo_pago = db.Column(db.String(20))
    monto_ultimo_pago = db.Column(db.Float)
    estado = db.Column(db.String(20), default='activo')
    tipo_prestamo = db.Column(db.String(20), default='prendario')

    pagos = db.relationship('Pago', backref='prestamo', lazy=True, cascade='all, delete-orphan')
    articulos = db.relationship('Articulo', backref='prestamo', lazy=True)

    @property
    def interes_un_mes(self):
        return round(self.monto_prestado * ((self.interes_mensual or 0) / 100), 2)

    @property
    def meses_transcurridos(self):
        ahora = get_bolivia_time()
        diff = (ahora.year - self.fecha_inicio.year) * 12 + (ahora.month - self.fecha_inicio.month)
        if ahora.day < self.fecha_inicio.day:
            diff -= 1
        return max(1, diff + 1)

    @property
    def meses_interes_pagados(self):
        if not self.interes_un_mes or self.interes_un_mes <= 0:
            return 0
        total_interes = sum(p.monto_pagado for p in self.pagos if p.tipo_pago == 'interes')
        return int(round(total_interes / self.interes_un_mes))

    @property
    def meses_adeudados(self):
        if self.estado == 'finalizado':
            return 0
        if not self.esta_vencido:
            return 1 if self.meses_interes_pagados == 0 else 0

        ahora = get_bolivia_time()
        diff = (ahora.year - self.fecha_finalizacion.year) * 12 + (ahora.month - self.fecha_finalizacion.month)
        if ahora.day < self.fecha_finalizacion.day:
            diff -= 1
        meses_mora = max(0, diff)
        return 1 + meses_mora

    @property
    def interes_acumulado_pendiente(self):
        if self.estado == 'finalizado':
            return 0.0
        return round(self.meses_adeudados * self.interes_un_mes, 2)

    @property
    def monto_liquidacion_actual(self):
        if self.estado == 'finalizado':
            return 0.0
        return round(self.monto_prestado + self.interes_acumulado_pendiente, 2)

    @property
    def monto_a_pagar(self):
        return self.monto_liquidacion_actual

    @property
    def monto_a_pagar_actual(self):
        return self.monto_liquidacion_actual

    @property
    def esta_vencido(self):
        return get_bolivia_time() > self.fecha_finalizacion

    @property
    def dias_vencido(self):
        if not self.esta_vencido:
            return 0
        ahora = get_bolivia_time()
        diff = ahora - self.fecha_finalizacion
        return diff.days

    @property
    def dias_para_vencimiento(self):
        hoy = get_bolivia_time().date()
        return (self.fecha_finalizacion.date() - hoy).days

    @property
    def total_pagado(self):
        return round(sum(pago.monto_pagado for pago in self.pagos), 2)

    @property
    def monto_objetivo_actual(self):
        return self.monto_liquidacion_actual

    @property
    def monto_pendiente_estimado(self):
        if self.estado in ['finalizado', 'decomisado']:
            return 0.0
        return max(0.0, round(self.monto_liquidacion_actual - self.total_pagado, 2))

    def __repr__(self):
        return f'<Prestamo {self.numero_documento}>'


class Pago(db.Model):
    __tablename__ = 'pago'

    id = db.Column(db.Integer, primary_key=True)
    prestamo_id = db.Column(db.Integer, db.ForeignKey('prestamo.id'), nullable=False)
    fecha_pago = db.Column(db.DateTime, default=get_bolivia_time)
    tipo_pago = db.Column(db.String(20), nullable=False)
    monto_pagado = db.Column(db.Float, nullable=False)

    def __repr__(self):
        return f'<Pago {self.tipo_pago} {self.monto_pagado}>'
