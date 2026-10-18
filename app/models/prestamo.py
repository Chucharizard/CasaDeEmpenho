import re
import urllib.parse

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
        pagos = [p for p in self.pagos if p.tipo_pago == 'interes']
        registrados = sum(p.meses_pagados for p in pagos if p.meses_pagados is not None)
        historicos = sum(p.monto_pagado for p in pagos if p.meses_pagados is None)
        return registrados + int(round(historicos / self.interes_un_mes))

    @property
    def meses_adeudados(self):
        if self.estado in {'finalizado', 'decomisado'}:
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
        if self.estado in {'finalizado', 'decomisado'}:
            return 0.0
        return round(self.meses_adeudados * self.interes_un_mes, 2)

    @property
    def monto_liquidacion_actual(self):
        if self.estado in {'finalizado', 'decomisado'}:
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
    def total_interes_pagado(self):
        return round(sum(pago.monto_pagado for pago in self.pagos if pago.tipo_pago == 'interes'), 2)

    @property
    def monto_objetivo_actual(self):
        return self.monto_liquidacion_actual

    @property
    def monto_pendiente_estimado(self):
        if self.estado in ['finalizado', 'decomisado']:
            return 0.0
        return self.monto_liquidacion_actual

    @property
    def telefono_whatsapp(self):
        if not self.usuario or not self.usuario.telefono:
            return None
        numeros = re.sub(r'\D', '', str(self.usuario.telefono))
        if not numeros:
            return None
        # Celular Bolivia (8 dígitos empezando con 6 o 7): anteponer 591
        if len(numeros) == 8 and numeros[0] in ('6', '7'):
            return f"591{numeros}"
        # Completo con código de país 591
        if len(numeros) == 11 and numeros.startswith('591'):
            return numeros
        # Si tiene al menos 8 dígitos en general
        if len(numeros) >= 8:
            return numeros
        return None

    @property
    def whatsapp_mensaje(self):
        if not self.usuario:
            return ""

        nombre = self.usuario.nombre or "Estimado/a cliente"
        doc = self.numero_documento or f"#{self.numero_prestamo}"
        articulos_desc = ", ".join(a.nombre for a in self.articulos) if self.articulos else "su artículo en prenda"
        fecha_limite = self.fecha_finalizacion.strftime('%d/%m/%Y') if self.fecha_finalizacion else "a convenir"
        monto_pagar = self.monto_liquidacion_actual

        if self.estado == 'finalizado':
            return f'¡Hola *{nombre}*! Su préstamo *{doc}* está *finalizado* y su garantía fue liberada. Gracias por su preferencia.'
        if self.estado == 'decomisado':
            return f'¡Hola *{nombre}*! Su préstamo *{doc}* figura como *decomisado*. Puede comunicarse con administración para consultar su registro.'

        if self.esta_vencido:
            dias_v = self.dias_vencido
            meses_d = self.meses_adeudados
            interes_pend = self.interes_acumulado_pendiente

            return (
                f"¡Hola *{nombre}*! Le saludamos de *Panda · Casa de Empeño*.\n\n"
                f"Le informamos que su préstamo *{doc}* con garantía de *{articulos_desc}* "
                f"se encuentra *vencido* desde el *{fecha_limite}* ({dias_v} días de mora).\n\n"
                f"📋 *Detalle de su deuda:*\n"
                f"• Meses de interés adeudados: *{meses_d} mes(es)*\n"
                f"• Interés acumulado a pagar: *Bs. {interes_pend:.2f}*\n"
                f"• Monto total para liquidar y retirar: *Bs. {monto_pagar:.2f}*\n\n"
                f"⚠️ *AVISO IMPORTANTE:*\n"
                f"Le recordamos ponerse al día con el pago de sus intereses a la brevedad posible "
                f"para evitar el decomiso de su artículo y su pase a venta en inventario.\n\n"
                f"Puede pasar por nuestra sucursal para regularizar su cuenta o comunicarse por este medio si tiene alguna duda. ¡Muchas gracias!"
            )
        else:
            dias_restantes = max(0, self.dias_para_vencimiento)
            interes_mes = self.interes_un_mes

            return (
                f"¡Hola *{nombre}*! Le saludamos de *Panda · Casa de Empeño*.\n\n"
                f"Le recordamos que su préstamo *{doc}* con garantía de *{articulos_desc}* "
                f"tiene como fecha límite de pago el *{fecha_limite}* (en {dias_restantes} días).\n\n"
                f"📋 *Opciones de pago:*\n"
                f"• Cuota de interés para renovar (1 mes): *Bs. {interes_mes:.2f}*\n"
                f"• Monto total para liquidar y retirar: *Bs. {monto_pagar:.2f}*\n\n"
                f"Le recordamos realizar su pago a tiempo para mantener su garantía al día y evitar recargos o decomiso de su prenda. "
                f"¡Muchas gracias por su preferencia!"
            )

    @property
    def whatsapp_url(self):
        tel = self.telefono_whatsapp
        if not tel:
            return None
        return f"https://wa.me/{tel}?text={urllib.parse.quote(self.whatsapp_mensaje)}"

    def __repr__(self):
        return f'<Prestamo {self.numero_documento}>'


class Pago(db.Model):
    __tablename__ = 'pago'

    id = db.Column(db.Integer, primary_key=True)
    prestamo_id = db.Column(db.Integer, db.ForeignKey('prestamo.id'), nullable=False)
    fecha_pago = db.Column(db.DateTime, default=get_bolivia_time)
    tipo_pago = db.Column(db.String(20), nullable=False)
    monto_pagado = db.Column(db.Float, nullable=False)
    meses_pagados = db.Column(db.Integer)
    operacion_id = db.Column(db.String(64), unique=True, index=True)
    comprobante_json = db.Column(db.Text)
    whatsapp_estado = db.Column(db.String(24), nullable=False, default='no_solicitado', server_default='no_solicitado')
    whatsapp_error = db.Column(db.Text)
    whatsapp_ultimo_intento = db.Column(db.DateTime)
    whatsapp_intentos = db.Column(db.Integer, nullable=False, default=0, server_default='0')

    @property
    def datos_comprobante(self):
        from app.services.receipt_service import build_receipt_data
        return build_receipt_data(self)

    @property
    def whatsapp_mensaje(self):
        from app.services.receipt_service import payment_message
        return payment_message(self) if self.prestamo else ''

    @property
    def whatsapp_url(self):
        if not self.prestamo:
            return None
        tel = self.prestamo.telefono_whatsapp
        if not tel:
            return None
        return f"https://wa.me/{tel}?text={urllib.parse.quote(self.whatsapp_mensaje)}"

    def __repr__(self):
        return f'<Pago {self.tipo_pago} {self.monto_pagado}>'
