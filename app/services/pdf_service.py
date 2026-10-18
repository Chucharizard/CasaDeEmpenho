"""
Servicio para la generación de documentos PDF (contratos de empeño, comprobantes, etc.)
utilizando ReportLab.
"""
from io import BytesIO
from xml.sax.saxutils import escape
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as PdfImage
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

from app.utils import get_bolivia_time


def generar_documento_legal(data):
    """
    Genera un documento PDF formal (tamaño carta) que actúa como constancia
    privada del préstamo prendario y entrega de garantía.
    """
    data = {k: escape(v) if isinstance(v, str) else v for k, v in data.items()}
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
    data = {k: escape(v) if isinstance(v, str) else v for k, v in data.items()}
    bloque = []

    title_bold = ParagraphStyle(
        f'ReciboTitle_{copia_titulo[:3]}',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=14,
        textColor=colors.HexColor('#202a25')
    )
    badge_style = ParagraphStyle(
        f'ReciboBadge_{copia_titulo[:3]}',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=11,
        alignment=2,  # Derecha
        textColor=colors.HexColor('#3d5944')
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
        fecha_venc_str = str(fecha_venc or 'No registrado')

    tipo_pago = data.get('tipo_pago', 'interes')
    if tipo_pago == 'total':
        concepto = "Liquidación Total / Retiro y Liberación de Prenda"
        prox_venc = "PRENDA LIBERADA (Préstamo Finalizado)"
    else:
        meses = data.get('meses_pagados', 1)
        concepto = f"Pago de Interés ({meses} mes/es) - Renovación de Plazo" if meses is not None else "Pago de Interés (registro histórico)"
        prox_venc = (f"Vencimiento tras este pago: {fecha_venc_str}" if data.get('fecha_vencimiento')
                     else "Plazo original no registrado")

    monto_pagado = float(data.get('monto_pagado', 0.0))

    # 1. Encabezado
    from app.services.receipt_image import LOGO_PATH
    logo = PdfImage(str(LOGO_PATH), width=66, height=44) if LOGO_PATH.is_file() else ''
    header_data = [
        [
            logo,
            Paragraph("<b>PANDA</b><br/><font size=8 color='#59665d'>CASA DE EMPEÑO</font><br/><font size=7 color='#59665d'>COMPROBANTE DE PAGO</font>", title_bold),
            Paragraph(f"<b>N° {data.get('numero_recibo', 'REC-00000')}</b><br/><font size=7.5 color='#475569'>{fecha_pago_str}</font><br/><font size=7.5 color='#3d5944'><b>[{copia_titulo}]</b></font>", badge_style)
        ]
    ]
    header_tbl = Table(header_data, colWidths=[76, ancho * 0.58 - 76, ancho * 0.42])
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
        ('BACKGROUND', (1, 0), (1, 0), colors.HexColor('#e9f0e4')),
        ('BOX', (0, 0), (-1, -1), 0.8, colors.HexColor('#78927b')),
        ('LINEBEFORE', (1, 0), (1, 0), 0.8, colors.HexColor('#78927b')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]))
    bloque.append(econ_tbl)
    bloque.append(Spacer(1, 4))

    if data.get('historico_sin_plazo'):
        bloque.append(Paragraph('Registro histórico: el plazo original no está disponible. Los datos identificativos corresponden a la información conservada.', disclaimer_style))
    if data.get('excedente'):
        bloque.append(Paragraph(f"Importe adicional recibido: Bs. {data['excedente']:.2f}. No amplía los meses indicados.", disclaimer_style))
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
        bottomMargin=26,
        title=f"Panda - Comprobante {data.get('numero_recibo', '')}",
        author='Panda · Casa de Empeño',
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
        "- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -",
        linea_corte_style
    ))
    story.append(Spacer(1, 10))

    # 2. Talón Copia para Caja
    story.extend(_crear_bloque_recibo(data, "COPIA - CAJA / ARCHIVO", styles, ancho=532))

    doc.build(story)
    buffer.seek(0)
    return buffer



def generar_comprobante_imagen(data):
    """PNG Panda, generado desde la misma instantánea inmutable que el PDF."""
    from app.services.receipt_image import generar_imagen_panda
    return generar_imagen_panda(data)
