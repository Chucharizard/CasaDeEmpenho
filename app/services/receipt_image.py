"""Presentación de recibos Panda. Solo dibuja los datos conservados del pago."""
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
import reportlab


LOGO_PATH = Path(__file__).resolve().parents[1] / 'static' / 'brand' / 'panda-logo.png'
INK = '#202a25'
MUTED = '#59665d'
LINE = '#d8ded4'
PAPER = '#fffefa'
SAGE = '#e9f0e4'


def _font(size, bold=False):
    # ReportLab ya se distribuye con la aplicación, incluidas estas fuentes.
    path = Path(reportlab.__file__).parent / 'fonts' / ('VeraBd.ttf' if bold else 'Vera.ttf')
    return ImageFont.truetype(str(path), size)


def _wrap_lines(text, font, width, draw):
    """Ajusta por píxeles, incluyendo identificadores sin espacios, sin recortar."""
    lines = []
    for paragraph in str(text or 'No registrado').splitlines():
        current = ''
        for word in paragraph.split():
            candidate = f'{current} {word}'.strip()
            if draw.textlength(candidate, font=font) <= width:
                current = candidate
                continue
            if current:
                lines.append(current)
                current = ''
            for char in word:
                if current and draw.textlength(current + char, font=font) > width:
                    lines.append(current)
                    current = ''
                current += char
        lines.append(current)
    return lines or ['No registrado']


def _date(value, time=False):
    if hasattr(value, 'strftime'):
        return value.strftime('%d/%m/%Y · %H:%M' if time else '%d/%m/%Y')
    return str(value or 'No registrado')


def generar_imagen_panda(data):
    width = 960
    left, right = 76, 884
    content_width = right - left
    fonts = {size: _font(size) for size in (17, 19, 21, 22, 24)}
    bold = {size: _font(size, True) for size in (17, 19, 22, 24, 27, 32, 62, 70)}
    measure = ImageDraw.Draw(Image.new('RGB', (1, 1)))
    commands = []

    def text(value, x, y, font, color=INK, max_width=content_width, spacing=7):
        lines = _wrap_lines(value, font, max_width, measure)
        line_height = font.size + spacing
        for index, line in enumerate(lines):
            commands.append(('text', (x, y + index * line_height), line, font, color))
        return y + len(lines) * line_height

    def box(bounds, fill, radius=18, outline=None):
        commands.append(('box', bounds, fill, radius, outline))

    def rule(y):
        commands.append(('line', (left, y, right, y), LINE))

    def field(label, value, x, y, available=content_width, strong=False):
        end = text(label.upper(), x, y, bold[17], MUTED, available)
        return text(value, x, end + 8, bold[24] if strong else fonts[22], INK, available)

    # Identidad fija: un recibo compartido no depende del tema personal del operador.
    box((32, 32, 928, 238), '#000000', 24)
    text('PANDA', 280, 72, bold[62], '#ffffff', 560)
    text('CASA DE EMPEÑO', 284, 151, fonts[19], '#c6d6c0', 550)
    text('Comprobante de pago', left, 268, bold[27])
    meta_y = 316
    meta_bottom = max(
        text(data.get('numero_recibo', 'REC-00000'), left, meta_y, bold[19], max_width=340),
        text(_date(data.get('fecha_pago'), time=True), 490, meta_y, fonts[19], MUTED, right - 490),
    )

    amount_y = meta_bottom + 24
    box((left, amount_y, right, amount_y + 178), SAGE, 20)
    text('TOTAL PAGADO', left + 28, amount_y + 23, bold[17], '#3d5944', content_width - 56)
    amount = f"Bs. {float(data.get('monto_pagado', 0)):,.2f}"
    amount_font = bold[70]
    while measure.textlength(amount, font=amount_font) > content_width - 56 and amount_font.size > 30:
        amount_font = _font(amount_font.size - 2, True)
    text(amount, left + 26, amount_y + 62, amount_font, INK, content_width - 52)

    total = data.get('tipo_pago') == 'total'
    months = data.get('meses_pagados')
    concept = ('Liquidación total' if total else 'Pago de interés · registro histórico'
               if data.get('historico_sin_plazo') else 'Pago de interés · renovación')
    y = field('Concepto', concept, left, amount_y + 212, strong=True)
    if not total and months is not None:
        y = text(f"{months} {'mes registrado' if months == 1 else 'meses registrados'} en este pago.", left, y + 7, fonts[19], MUTED)
    rule(y + 23)

    y = field('Cliente', data.get('nombre_cliente'), left, y + 49, strong=True)
    half = (content_width - 32) // 2
    y = max(
        field('Cédula de identidad', data.get('ci_cliente'), left, y + 22, half),
        field('Teléfono', data.get('telefono_cliente'), left + half + 32, y + 22, half),
    )
    y = max(
        field('Préstamo', data.get('numero_documento'), left, y + 24, half, True),
        field('Creado el', _date(data.get('fecha_inicio')), left + half + 32, y + 24, half),
    )
    y = field('Garantía', data.get('articulos_descripcion'), left, y + 24)

    # Un pago de intereses no acredita por sí solo que se haya cubierto toda la mora.
    if total:
        status_label = 'PRÉSTAMO FINALIZADO'
        status = 'Garantía liberada para retiro'
    elif data.get('historico_sin_plazo') or not data.get('fecha_vencimiento'):
        status_label = 'REGISTRO HISTÓRICO'
        status = 'Plazo original no disponible'
    else:
        status_label = 'VENCIMIENTO TRAS ESTE PAGO'
        status = _date(data['fecha_vencimiento'])
    status_y = y + 30
    status_lines = _wrap_lines(status, bold[32], content_width - 56, measure)
    status_height = 76 + len(status_lines) * 39
    box((left, status_y, right, status_y + status_height), '#f2f3ed', 16, LINE)
    text(status_label, left + 26, status_y + 22, bold[17], MUTED, content_width - 52)
    y = text(status, left + 26, status_y + 55, bold[32], INK, content_width - 52) + 22

    summary = data.get('resumen_interes')
    if summary and not total:
        panel_y = y + 8
        # Se mide primero para que incluso importes grandes quepan sin superponerse.
        start = len(commands)
        col_width = (content_width - 84) // 2
        text(f"RESUMEN AL {_date(data.get('fecha_pago'))}", left + 26, panel_y + 24, bold[17], MUTED, content_width - 52)
        amounts_y = panel_y + 65
        end = max(
            field('Cuota mensual', f"Bs. {summary['cuota_mensual']:,.2f}", left + 26, amounts_y, col_width, True),
            field('Interés pendiente', f"Bs. {summary['interes_pendiente']:,.2f}", left + 58 + col_width, amounts_y, col_width, True),
        )
        pending = summary['meses_pendientes']
        detail = (f"{pending} {'cuota pendiente' if pending == 1 else 'cuotas pendientes'} después de este pago."
                  if pending else 'Sin cuotas de interés pendientes después de este pago.')
        end = text(detail, left + 26, end + 18, fonts[19], MUTED, content_width - 52)
        end = text('Importes de interés; no incluyen la liquidación del préstamo.', left + 26, end + 7, fonts[17], MUTED, content_width - 52)
        commands.insert(start, ('box', (left, panel_y, right, end + 24), SAGE, 16, None))
        y = end + 24

    history = data.get('historial_pagos', [])
    if history:
        rule(y + 28)
        y = text('HISTORIAL DE PAGOS', left, y + 54, bold[17], MUTED)
        count = data.get('total_pagos_hasta_recibo', len(history))
        caption = f'Últimos {len(history)} de {count} pagos hasta este recibo.' if count > len(history) else 'Pagos registrados hasta este recibo.'
        y = text(caption, left, y + 7, fonts[19], MUTED) + 20
        for index, payment in enumerate(history):
            row_top = y
            current = payment.get('actual', False)
            text_x = left + 52
            amount_x = right - 264
            row_width = amount_x - text_x - 22
            day = _date(payment.get('fecha_pago'))
            label = f'{day} · este pago' if current else day
            bottom = text(label, text_x, y, bold[19] if current else fonts[19], INK if current else MUTED, row_width)
            months_paid = payment.get('meses_pagados')
            kind = ('Liquidación total' if payment.get('tipo_pago') == 'total' else
                    f"Interés · {months_paid} {'mes' if months_paid == 1 else 'meses'}" if months_paid is not None else 'Interés registrado')
            bottom = text(kind, text_x, bottom + 6, fonts[19], MUTED, row_width)
            bottom = max(bottom, text(f"Bs. {payment['monto_pagado']:,.2f}", amount_x, row_top, bold[22], INK, right - amount_x))
            center = row_top + 10
            if index < len(history) - 1:
                commands.append(('line', (left + 14, center, left + 14, bottom + 32), LINE))
            commands.append(('dot', (left + 5, center - 9, left + 23, center + 9), '#4d7258' if current else '#d8ded4'))
            y = bottom + 26

    notes = []
    if data.get('excedente'):
        notes.append(f"Importe adicional recibido: Bs. {data['excedente']:,.2f}. No amplía los meses indicados.")
    paid, due = data.get('fecha_pago'), data.get('fecha_vencimiento')
    if not summary and not total and hasattr(paid, 'date') and hasattr(due, 'date') and due.date() < paid.date():
        notes.append('El vencimiento registrado es anterior a la fecha del pago. Puede existir interés pendiente.')
    if data.get('historico_sin_plazo'):
        notes.append('Los datos corresponden al registro histórico conservado. No se infiere un plazo nuevo.')
    for note in notes:
        y = text(note, left, y + 17, fonts[19], MUTED) + 3

    rule(y + 24)
    y = text('Gracias por confiar en Panda.', left, y + 51, bold[24])
    y = text('Conserva este comprobante como constancia de tu pago.', left, y + 12, fonts[19], MUTED)
    y = text('PANDA · CASA DE EMPEÑO', left, y + 29, fonts[17], MUTED)
    height = y + 74

    image = Image.new('RGB', (width, height), '#efefe9')
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((32, 32, 928, height - 32), radius=24, fill=PAPER, outline=LINE, width=2)
    for command in commands:
        if command[0] == 'text':
            _, position, value, font, color = command
            draw.text(position, value, font=font, fill=color, anchor='lt')
        elif command[0] == 'box':
            _, bounds, fill, radius, outline = command
            draw.rounded_rectangle(bounds, radius=radius, fill=fill, outline=outline, width=2)
        elif command[0] == 'dot':
            draw.ellipse(command[1], fill=command[2])
        else:
            draw.line(command[1], fill=command[2], width=2)
    if LOGO_PATH.is_file():
        # Se compone el archivo original sin retocarlo ni cambiar sus proporciones.
        with Image.open(LOGO_PATH) as source:
            logo = source.convert('RGB')
            logo.thumbnail((222, 148), Image.Resampling.LANCZOS)
            image.paste(logo, (46 + (222 - logo.width) // 2, 60 + (148 - logo.height) // 2))
    buffer = BytesIO()
    image.save(buffer, 'PNG', optimize=True)
    buffer.seek(0)
    return buffer
