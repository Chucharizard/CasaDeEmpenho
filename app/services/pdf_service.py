"""
Servicio para la generación de documentos PDF (contratos de empeño, comprobantes, etc.)
utilizando ReportLab.
"""
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

from app.utils import get_bolivia_time


def generar_documento_legal(data):
    """
    Genera un documento PDF formal (tamaño carta) que actúa como constancia
    privada del préstamo prendario y entrega de garantía.
    """
    buffer = BytesIO()
    
    fecha_inicio = data.get('fecha_inicio', get_bolivia_time())
    fecha_vencimiento = data.get('fecha_vencimiento', get_bolivia_time())

    dia_actual = fecha_inicio.strftime('%d')
    mes_actual = fecha_inicio.strftime('%m')
    anio_actual = fecha_inicio.strftime('%Y')
    dia_vencimiento = fecha_vencimiento.strftime('%d')
    mes_vencimiento = fecha_vencimiento.strftime('%m')
    anio_vencimiento = fecha_vencimiento.strftime('%Y')
    monto_con_interes = data.get('monto_prestado', 0)

    # Configuración de página con márgenes de 54pt (0.75 pulgadas)
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=54,
        leftMargin=54,
        topMargin=54,
        bottomMargin=54
    )
    
    styles = getSampleStyleSheet()
    
    # Estilo del Título Principal
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=15,
        leading=18,
        alignment=1,  # Centrado
        textColor=colors.HexColor('#2c3e50'),
        spaceAfter=10
    )
    
    subtitle_style = ParagraphStyle(
        'DocSubTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Oblique',
        fontSize=10,
        leading=13,
        alignment=1,  # Centrado
        textColor=colors.HexColor('#7f8c8d'),
        spaceAfter=25
    )
    
    # Estilos del contenido
    label_style = ParagraphStyle(
        'DocLabel',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=14,
        textColor=colors.HexColor('#34495e')
    )
    
    value_style = ParagraphStyle(
        'DocValue',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=11,
        leading=14,
        textColor=colors.HexColor('#2c3e50')
    )
    
    center_bold_style = ParagraphStyle(
        'DocCenterBold',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=12,
        alignment=1,  # Centrado
        textColor=colors.HexColor('#2c3e50')
    )

    story = []

    # Título y encabezado
    story.append(Paragraph("DOCUMENTO PRIVADO DE CONSTANCIA", title_style))
    story.append(Paragraph("Detalle de Préstamo Prendario y Recepción de Garantía", subtitle_style))
    
    # Estructura de filas para el contenido
    data_rows = [
        [Paragraph("Código Préstamo:", label_style), Paragraph(data.get('numero_documento', ''), value_style)],
        [Paragraph("Cliente / Deudor:", label_style), Paragraph(data.get('nombre_cliente', ''), value_style)],
        [Paragraph("Cédula de Identidad (CI):", label_style), Paragraph(data.get('ci_cliente', ''), value_style)],
        [Paragraph("Artículo en Garantía:", label_style), Paragraph(data.get('articulo_descripcion', ''), value_style)],
        [Paragraph("Monto Entregado:", label_style), Paragraph(f"Bs. {monto_con_interes:.2f}", value_style)],
        [Paragraph("Fecha de Desembolso:", label_style), Paragraph(f"{dia_actual}/{mes_actual}/{anio_actual}", value_style)],
        [Paragraph("Fecha de Vencimiento:", label_style), Paragraph(f"{dia_vencimiento}/{mes_vencimiento}/{anio_vencimiento}", value_style)],
    ]
    
    # Tabla de datos con autoenvoltorio
    table = Table(data_rows, colWidths=[130, 374])
    table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ('LINEBELOW', (0, 0), (-1, -2), 0.5, colors.HexColor('#ecf0f1')),
    ]))
    
    # Contenedor estético (recuadro) para la tabla
    outer_table = Table([[table]], colWidths=[504])
    outer_table.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#bdc3c7')),
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#fafafa')),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    
    story.append(outer_table)
    story.append(Spacer(1, 40))
    
    # Cláusula de conformidad
    disclaimer_style = ParagraphStyle(
        'DocDisclaimer',
        parent=styles['Normal'],
        fontName='Helvetica-Oblique',
        fontSize=9,
        leading=12,
        alignment=4,  # Justificado
        textColor=colors.HexColor('#7f8c8d'),
        spaceAfter=50
    )
    disclaimer_text = (
        "El deudor declara conformidad con los términos y condiciones del préstamo aquí detallados, "
        "así como con la entrega del artículo descrito en calidad de prenda/garantía. De no efectuarse "
        "la liquidación o renovación en las fechas pactadas, el artículo pasará a disposición de la administración."
    )
    story.append(Paragraph(disclaimer_text, disclaimer_style))
    
    # Firmas
    signature_data = [
        [
            Paragraph("________________________________________<br/>Firma del Deudor (Cliente)", center_bold_style),
            Paragraph("________________________________________<br/>Firma de la Administración", center_bold_style)
        ]
    ]
    signature_table = Table(signature_data, colWidths=[252, 252])
    signature_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
    ]))
    
    story.append(signature_table)
    
    doc.build(story)
    buffer.seek(0)
    return buffer


def _crear_bloque_recibo(data, copia_titulo, styles, ancho=532):
    """
    Construye los flowables de un talón de recibo (Original o Copia)
    diseñado para encajar dos talones en una sola hoja tamaño carta.
    """
    bloque = []

    title_bold = ParagraphStyle(
        f'ReciboTitle_{copia_titulo[:3]}',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=14,
        textColor=colors.HexColor('#1a365d')
    )
    badge_style = ParagraphStyle(
        f'ReciboBadge_{copia_titulo[:3]}',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=11,
        alignment=2,  # Derecha
        textColor=colors.HexColor('#2b6cb0')
    )
    lbl_style = ParagraphStyle(
        f'ReciboLbl_{copia_titulo[:3]}',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=10,
        textColor=colors.HexColor('#334155')
    )
    val_style = ParagraphStyle(
        f'ReciboVal_{copia_titulo[:3]}',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=10,
        textColor=colors.HexColor('#0f172a')
    )
    amount_val = ParagraphStyle(
        f'ReciboAmountVal_{copia_titulo[:3]}',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=13,
        leading=15,
        alignment=1,  # Centrado
        textColor=colors.HexColor('#14532d')
    )
    disclaimer_style = ParagraphStyle(
        f'ReciboDisclaimer_{copia_titulo[:3]}',
        parent=styles['Normal'],
        fontName='Helvetica-Oblique',
        fontSize=7,
        leading=9,
        alignment=1,
        textColor=colors.HexColor('#64748b')
    )
    sign_style = ParagraphStyle(
        f'ReciboSign_{copia_titulo[:3]}',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7.5,
        leading=9.5,
        alignment=1,
        textColor=colors.HexColor('#475569')
    )

    fecha_pago = data.get('fecha_pago')
    if hasattr(fecha_pago, 'strftime'):
        fecha_pago_str = fecha_pago.strftime('%d/%m/%Y %H:%M')
    else:
        fecha_pago_str = str(fecha_pago or '')

    fecha_venc = data.get('fecha_vencimiento')
    if hasattr(fecha_venc, 'strftime'):
        fecha_venc_str = fecha_venc.strftime('%d/%m/%Y')
    else:
        fecha_venc_str = str(fecha_venc or 'N/A')

    tipo_pago = data.get('tipo_pago', 'interes')
    if tipo_pago == 'total':
        concepto = "Liquidación Total / Retiro y Liberación de Prenda"
        prox_venc = "PRENDA LIBERADA (Préstamo Finalizado)"
    else:
        meses = data.get('meses_pagados', 1)
        concepto = f"Pago de Interés ({meses} mes/es) - Renovación de Plazo"
        prox_venc = f"Nuevo Vencimiento: {fecha_venc_str}"

    monto_pagado = float(data.get('monto_pagado', 0.0))

    # 1. Encabezado
    header_data = [
        [
            Paragraph("<b>CASA DE EMPEÑO</b><br/><font size=7 color='#64748b'>COMPROBANTE OFICIAL DE PAGO EN CAJA</font>", title_bold),
            Paragraph(f"<b>N° {data.get('numero_recibo', 'REC-00000')}</b><br/><font size=7.5 color='#475569'>{fecha_pago_str}</font><br/><font size=7.5 color='#2563eb'><b>[{copia_titulo}]</b></font>", badge_style)
        ]
    ]
    header_tbl = Table(header_data, colWidths=[ancho * 0.58, ancho * 0.42])
    header_tbl.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    bloque.append(header_tbl)
    bloque.append(Spacer(1, 3))

    # 2. Datos de Cliente y Préstamo
    info_data = [
        [
            Paragraph("Cliente:", lbl_style),
            Paragraph(f"<b>{data.get('nombre_cliente', '')}</b>", val_style),
            Paragraph("Cédula (CI):", lbl_style),
            Paragraph(str(data.get('ci_cliente', '')), val_style)
        ],
        [
            Paragraph("Préstamo N°:", lbl_style),
            Paragraph(f"<b>{data.get('numero_documento', '')}</b>", val_style),
            Paragraph("Teléfono:", lbl_style),
            Paragraph(str(data.get('telefono_cliente', 'N/A')), val_style)
        ],
        [
            Paragraph("Garantía / Prenda:", lbl_style),
            Paragraph(str(data.get('articulos_descripcion', '')), val_style),
            Paragraph("Monto Préstamo:", lbl_style),
            Paragraph(f"Bs. {float(data.get('monto_prestado', 0.0)):.2f}", val_style)
        ]
    ]
    info_tbl = Table(info_data, colWidths=[80, ancho * 0.5 - 80, 80, ancho * 0.5 - 80])
    info_tbl.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('INNERGRID', (0, 0), (-1, -1), 0.3, colors.HexColor('#e2e8f0')),
        ('TOPPADDING', (0, 0), (-1, -1), 2.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
    ]))
    bloque.append(info_tbl)
    bloque.append(Spacer(1, 3))

    # 3. Cuadro Financiero
    econ_data = [
        [
            Paragraph(f"<b>Concepto:</b> {concepto}<br/><b>Estado:</b> {prox_venc}", val_style),
            Paragraph(f"<font size=7.5 color='#166534'><b>TOTAL COBRADO</b></font><br/>Bs. {monto_pagado:.2f}", amount_val)
        ]
    ]
    econ_tbl = Table(econ_data, colWidths=[ancho * 0.65, ancho * 0.35])
    econ_tbl.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BACKGROUND', (0, 0), (0, 0), colors.HexColor('#ffffff')),
        ('BACKGROUND', (1, 0), (1, 0), colors.HexColor('#f0fdf4')),
        ('BOX', (0, 0), (-1, -1), 0.8, colors.HexColor('#16a34a')),
        ('LINEBEFORE', (1, 0), (1, 0), 0.8, colors.HexColor('#16a34a')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]))
    bloque.append(econ_tbl)
    bloque.append(Spacer(1, 4))

    # 4. Nota de constancia
    bloque.append(Paragraph(
        "Este comprobante acredita la recepción conforme del pago señalado. Consérvese para cualquier reclamo o renovación.",
        disclaimer_style
    ))
    bloque.append(Spacer(1, 14))

    # 5. Firmas
    firmas_data = [
        [
            Paragraph("___________________________________<br/>Firma Cliente / Interesado", sign_style),
            Paragraph("___________________________________<br/>Firma y Sello de Caja", sign_style)
        ]
    ]
    firmas_tbl = Table(firmas_data, colWidths=[ancho * 0.5, ancho * 0.5])
    firmas_tbl.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    bloque.append(firmas_tbl)

    return bloque


def generar_comprobante_pago(data):
    """
    Genera un comprobante de pago oficial en formato PDF.
    Incluye 2 talones en una sola hoja tamaño carta:
    1. Talón superior: Original para el Cliente
    2. Talón inferior: Copia para Administración / Caja
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=40,
        leftMargin=40,
        topMargin=26,
        bottomMargin=26
    )
    styles = getSampleStyleSheet()
    story = []

    # 1. Talón Original para el Cliente
    story.extend(_crear_bloque_recibo(data, "ORIGINAL - CLIENTE", styles, ancho=532))

    # Divisoria de corte
    story.append(Spacer(1, 10))
    linea_corte_style = ParagraphStyle(
        'CorteLine',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=6.5,
        alignment=1,
        textColor=colors.HexColor('#94a3b8')
    )
    story.append(Paragraph(
        "✂ - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - ✂",
        linea_corte_style
    ))
    story.append(Spacer(1, 10))

    # 2. Talón Copia para Caja
    story.extend(_crear_bloque_recibo(data, "COPIA - CAJA / ARCHIVO", styles, ancho=532))

    doc.build(story)
    buffer.seek(0)
    return buffer


def _obtener_fuente(nombre_bold, nombre_regular, tamano):
    """
    Intenta cargar fuentes tipográficas del sistema (Windows/Linux) o fallback a la predeterminada.
    """
    import os
    from PIL import ImageFont
    fuentes_dir = os.path.join(os.environ.get('WINDIR', 'C:\\Windows'), 'Fonts')
    candidatas = [nombre_bold, nombre_regular, 'arialbd.ttf', 'arial.ttf', 'DejaVuSans-Bold.ttf', 'DejaVuSans.ttf']
    for arch in candidatas:
        ruta = os.path.join(fuentes_dir, arch) if os.path.exists(fuentes_dir) else arch
        if os.path.exists(ruta):
            try:
                return ImageFont.truetype(ruta, tamano)
            except Exception:
                continue
    try:
        return ImageFont.truetype(nombre_regular, tamano)
    except Exception:
        return ImageFont.load_default()


def generar_comprobante_imagen(data):
    """
    Genera un comprobante de pago digital en formato imagen PNG de alta resolución (tipo ticket oficial)
    apto para compartir directamente por WhatsApp o copiar al portapapeles.
    Retorna un buffer BytesIO con la imagen PNG.
    """
    from PIL import Image, ImageDraw

    W, H = 640, 720
    img = Image.new('RGB', (W, H), color='#f1f5f9')
    draw = ImageDraw.Draw(img)

    f_title = _obtener_fuente('segoeuib.ttf', 'segoeui.ttf', 24)
    f_sub = _obtener_fuente('segoeui.ttf', 'segoeui.ttf', 13)
    f_badge = _obtener_fuente('segoeuib.ttf', 'segoeui.ttf', 14)
    f_lbl = _obtener_fuente('segoeuib.ttf', 'segoeui.ttf', 13)
    f_val = _obtener_fuente('segoeui.ttf', 'segoeui.ttf', 13)
    f_amount_lbl = _obtener_fuente('segoeuib.ttf', 'segoeui.ttf', 11)
    f_amount = _obtener_fuente('segoeuib.ttf', 'segoeui.ttf', 32)
    f_footer = _obtener_fuente('segoeui.ttf', 'segoeui.ttf', 11)

    # Tarjeta principal con borde suave
    draw.rounded_rectangle([20, 20, W - 20, H - 20], radius=16, fill='#ffffff', outline='#cbd5e1', width=2)

    # Banner superior azul marino
    draw.rounded_rectangle([20, 20, W - 20, 110], radius=16, fill='#1e3a8a')
    draw.rectangle([20, 90, W - 20, 110], fill='#1e3a8a')

    draw.text((W / 2, 50), 'CASA DE EMPEÑO', fill='#ffffff', font=f_title, anchor='mm')
    draw.text((W / 2, 80), 'COMPROBANTE OFICIAL DE PAGO EN CAJA', fill='#93c5fd', font=f_sub, anchor='mm')

    # Sub-encabezado: Recibo N° & Fecha
    num_recibo = data.get('numero_recibo', 'REC-00000')
    draw.text((45, 135), f"N° {num_recibo}", fill='#1e293b', font=f_badge)

    fecha_pago = data.get('fecha_pago')
    if hasattr(fecha_pago, 'strftime'):
        fecha_pago_str = fecha_pago.strftime('%d/%m/%Y %H:%M')
    else:
        fecha_pago_str = str(fecha_pago or '')
    draw.text((W - 45, 135), fecha_pago_str, fill='#64748b', font=f_val, anchor='ra')

    draw.line([(45, 160), (W - 45, 160)], fill='#e2e8f0', width=1)

    # Cuadro de Cliente y Préstamo
    draw.rounded_rectangle([45, 175, W - 45, 365], radius=10, fill='#f8fafc', outline='#e2e8f0', width=1)

    # Fila 1: Cliente & CI
    draw.text((65, 195), 'Cliente:', fill='#64748b', font=f_lbl)
    nombre = str(data.get('nombre_cliente', ''))
    if len(nombre) > 24:
        nombre = nombre[:22] + '..'
    draw.text((140, 195), nombre, fill='#0f172a', font=f_lbl)

    draw.text((360, 195), 'C.I.:', fill='#64748b', font=f_lbl)
    draw.text((410, 195), str(data.get('ci_cliente', '')), fill='#0f172a', font=f_val)

    # Fila 2: Préstamo N° & Teléfono
    draw.text((65, 235), 'Préstamo:', fill='#64748b', font=f_lbl)
    draw.text((140, 235), str(data.get('numero_documento', '')), fill='#2563eb', font=f_lbl)

    draw.text((360, 235), 'Teléfono:', fill='#64748b', font=f_lbl)
    draw.text((430, 235), str(data.get('telefono_cliente', 'N/A')), fill='#0f172a', font=f_val)

    # Fila 3: Prenda / Garantía
    draw.text((65, 275), 'Garantía:', fill='#64748b', font=f_lbl)
    garantia_texto = str(data.get('articulos_descripcion', ''))
    if len(garantia_texto) > 46:
        garantia_texto = garantia_texto[:43] + '...'
    draw.text((140, 275), garantia_texto, fill='#0f172a', font=f_val)

    # Fila 4: Monto Préstamo
    draw.text((65, 315), 'Monto Inicial:', fill='#64748b', font=f_lbl)
    draw.text((160, 315), f"Bs. {float(data.get('monto_prestado', 0)):.2f}", fill='#0f172a', font=f_val)

    # Cuadro Financiero (Verde destacado)
    draw.rounded_rectangle([45, 385, W - 45, 520], radius=10, fill='#f0fdf4', outline='#16a34a', width=2)

    tipo_pago = data.get('tipo_pago', 'interes')
    fecha_venc = data.get('fecha_vencimiento')
    if hasattr(fecha_venc, 'strftime'):
        fecha_venc_str = fecha_venc.strftime('%d/%m/%Y')
    else:
        fecha_venc_str = str(fecha_venc or 'N/A')

    if tipo_pago == 'total':
        concepto = 'Liquidación Total / Retiro de Prenda'
        estado_msg = 'PRENDA LIBERADA Y RETIRADA'
    else:
        meses = data.get('meses_pagados', 1)
        concepto = f'Pago Interés ({meses} mes/es) - Renovación'
        estado_msg = f'Nuevo Vencimiento: {fecha_venc_str}'

    draw.text((65, 410), 'CONCEPTO:', fill='#166534', font=f_amount_lbl)
    draw.text((65, 430), concepto, fill='#0f172a', font=f_lbl)

    draw.text((65, 465), 'ESTADO:', fill='#166534', font=f_amount_lbl)
    draw.text((65, 485), estado_msg, fill='#15803d', font=f_lbl)

    # Total Pagado a la derecha
    draw.text((W - 65, 420), 'TOTAL PAGADO', fill='#166534', font=f_amount_lbl, anchor='ra')
    monto_pagado = float(data.get('monto_pagado', 0))
    draw.text((W - 65, 465), f"Bs. {monto_pagado:.2f}", fill='#14532d', font=f_amount, anchor='ra')

    # Placa de validación
    draw.rounded_rectangle([45, 540, W - 45, 585], radius=8, fill='#e0f2fe', outline='#bae6fd', width=1)
    draw.text((W / 2, 562), '[ EMISIÓN CONFORME Y REGISTRADA EN CAJA ]', fill='#0369a1', font=f_lbl, anchor='mm')

    # Pie informativo
    draw.text((W / 2, 610), 'Documento digital generado automáticamente por el sistema.', fill='#64748b', font=f_footer, anchor='mm')
    draw.text((W / 2, 628), 'Conserve este comprobante como constancia legal de su pago.', fill='#64748b', font=f_footer, anchor='mm')
    draw.text((W / 2, 660), '¡Muchas gracias por su preferencia!', fill='#1e3a8a', font=f_lbl, anchor='mm')

    buffer = BytesIO()
    img.save(buffer, format='PNG', optimize=True)
    buffer.seek(0)
    return buffer

