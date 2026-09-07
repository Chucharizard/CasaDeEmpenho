from app.utils import get_bolivia_time, format_bolivian_phone
import os
import traceback
from datetime import datetime
from io import BytesIO
import urllib.parse

from flask import current_app, flash, redirect, render_template, request, send_file, session, url_for
from flask_login import login_required
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

from dateutil.relativedelta import relativedelta
from sqlalchemy.orm import joinedload

from app import db
from app.models import Articulo, Prestamo, ProductoVenta, Usuario
from app.models.prestamo import Pago
from app.routes.admin_shared import (
    VALID_LOAN_STATES,
    VALID_PAYMENT_TYPES,
    admin,
    admin_required,
    build_prestamo_alerts,
    build_prestamo_timeline,
    clean_text,
    create_inactive_password_hash,
    get_tasa_configurada,
    obtener_fecha_vencimiento,
    parse_interest,
    parse_positive_float,
    resolve_total_payment_due,
)


def generar_documento_legal(data):
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
    
    # Creación de tabla con autoenvoltorio (las columnas son 130pt y 374pt, totalizando 504pt, que cabe en 612pt del ancho carta - 108pt márgenes)
    table = Table(data_rows, colWidths=[130, 374])
    table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ('LINEBELOW', (0, 0), (-1, -2), 0.5, colors.HexColor('#ecf0f1')), # Línea delgada divisoria entre celdas
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


@admin.route('/nuevo-prestamo', methods=['GET', 'POST'])
@login_required
@admin_required
def nuevo_prestamo():
    if request.method == 'POST':
        ci = clean_text(request.form.get('ci'))
        nombre = clean_text(request.form.get('nombre'))
        telefono = format_bolivian_phone(request.form.get('telefono'))
        articulo_nombre = clean_text(request.form.get('articulo_nombre'))
        articulo_descripcion = clean_text(request.form.get('articulo_descripcion'))
        imprimir_documento = request.form.get('imprimir_documento') == 'on'

        if not all([ci, nombre, articulo_nombre]):
            flash('CI, nombre y articulo son obligatorios.', 'danger')
            return redirect(url_for('admin.nuevo_prestamo'))

        try:
            monto = parse_positive_float(request.form.get('monto'), 'monto')

            usuario = Usuario.query.filter_by(ci=ci).first()
            if not usuario:
                usuario = Usuario(
                    ci=ci,
                    nombre=nombre,
                    telefono=telefono,
                    password=create_inactive_password_hash(),
                    es_admin=False,
                    cuenta_activa=False,
                )
                db.session.add(usuario)
                db.session.flush()
            else:
                if telefono:
                    usuario.telefono = telefono
                if nombre:
                    usuario.nombre = nombre

            ultimo_prestamo = Prestamo.query.order_by(Prestamo.numero_prestamo.desc()).first()
            nuevo_numero_prestamo = (ultimo_prestamo.numero_prestamo + 1) if ultimo_prestamo else 1
            nuevo_numero_documento = f'PREST-{nuevo_numero_prestamo:04}'

            fecha_inicio = get_bolivia_time()
            prestamo = Prestamo(
                numero_prestamo=nuevo_numero_prestamo,
                numero_documento=nuevo_numero_documento,
                usuario_id=usuario.id,
                monto_prestado=monto,
                interes_mensual=get_tasa_configurada('interes_prendario', 10.0),
                fecha_inicio=fecha_inicio,
                fecha_finalizacion=obtener_fecha_vencimiento(fecha_inicio),
                tipo_prestamo='prendario',
                estado='activo',
            )
            db.session.add(prestamo)
            db.session.flush()

            db.session.add(
                Articulo(
                    nombre=articulo_nombre,
                    descripcion=articulo_descripcion or articulo_nombre[:50],
                    prestamo_id=prestamo.id,
                    estado='empenado',
                )
            )
            db.session.commit()

            if imprimir_documento:
                session['pdf_prestamo_id'] = prestamo.id
                flash(f'Préstamo {nuevo_numero_documento} creado exitosamente. Descargando documento...', 'success')
            else:
                flash(f'Préstamo {nuevo_numero_documento} creado exitosamente.', 'success')

            return redirect(url_for('admin.dashboard'))
        except Exception as exc:
            db.session.rollback()
            flash(f'Error al crear el préstamo: {exc}', 'danger')
            traceback.print_exc()

    return render_template('admin/nuevo_prestamo.html')


@admin.route('/prestamo-anterior', methods=['GET', 'POST'])
@login_required
@admin_required
def prestamo_anterior():
    if request.method == 'POST':
        ci = clean_text(request.form.get('ci'))
        nombre = clean_text(request.form.get('nombre'))
        telefono = format_bolivian_phone(request.form.get('telefono'))
        articulo_nombre = clean_text(request.form.get('articulo_nombre'))
        articulo_descripcion = clean_text(request.form.get('articulo_descripcion'))
        fecha_inicio_str = clean_text(request.form.get('fecha_inicio'))
        imprimir_documento = request.form.get('imprimir_documento') == 'on'

        if not all([ci, nombre, articulo_nombre, fecha_inicio_str]):
            flash('Todos los campos principales son obligatorios.', 'danger')
            return redirect(url_for('admin.prestamo_anterior'))

        try:
            monto = parse_positive_float(request.form.get('monto'), 'monto')
            fecha_inicio = datetime.strptime(fecha_inicio_str, '%Y-%m-%d')

            usuario = Usuario.query.filter_by(ci=ci).first()
            if not usuario:
                usuario = Usuario(
                    ci=ci,
                    nombre=nombre,
                    telefono=telefono,
                    password=create_inactive_password_hash(),
                    es_admin=False,
                    cuenta_activa=False,
                )
                db.session.add(usuario)
                db.session.flush()
            else:
                if telefono:
                    usuario.telefono = telefono
                if nombre:
                    usuario.nombre = nombre

            ultimo_prestamo = Prestamo.query.order_by(Prestamo.numero_prestamo.desc()).first()
            nuevo_numero_prestamo = (ultimo_prestamo.numero_prestamo + 1) if ultimo_prestamo else 1
            nuevo_numero_documento = f'PREST-{nuevo_numero_prestamo:04}'

            prestamo = Prestamo(
                numero_prestamo=nuevo_numero_prestamo,
                numero_documento=nuevo_numero_documento,
                usuario_id=usuario.id,
                monto_prestado=monto,
                interes_mensual=get_tasa_configurada('interes_prendario', 10.0),
                fecha_inicio=fecha_inicio,
                fecha_finalizacion=obtener_fecha_vencimiento(fecha_inicio),
                tipo_prestamo='prendario',
                estado='activo',
            )
            db.session.add(prestamo)
            db.session.flush()
            db.session.add(
                Articulo(
                    nombre=articulo_nombre,
                    descripcion=articulo_descripcion or articulo_nombre[:50],
                    prestamo_id=prestamo.id,
                    estado='empenado',
                )
            )
            db.session.commit()

            if imprimir_documento:
                session['pdf_prestamo_anterior_id'] = prestamo.id
                flash(f'Préstamo {nuevo_numero_documento} registrado. Descargando documento...', 'success')
            else:
                flash(f'Préstamo {nuevo_numero_documento} registrado exitosamente.', 'success')

            return redirect(url_for('admin.dashboard'))
        except Exception as exc:
            db.session.rollback()
            flash(f'Error al registrar el préstamo: {exc}', 'danger')
            traceback.print_exc()

    return render_template('admin/prestamo_anterior.html')


@admin.route('/descargar-documento/<int:prestamo_id>')
@login_required
@admin_required
def descargar_documento(prestamo_id):
    prestamo = Prestamo.query.get_or_404(prestamo_id)
    usuario = prestamo.usuario
    articulo = prestamo.articulos[0] if prestamo.articulos else None

    pdf_data = generar_documento_legal({
        'numero_documento': prestamo.numero_documento,
        'nombre_cliente': usuario.nombre if usuario else 'N/A',
        'ci_cliente': usuario.ci if usuario else 'N/A',
        'articulo_descripcion': articulo.descripcion if articulo else 'N/A',
        'monto_prestado': prestamo.monto_prestado,
        'fecha_inicio': prestamo.fecha_inicio,
        'fecha_vencimiento': prestamo.fecha_finalizacion,
    })

    pdf_stream = BytesIO(pdf_data.getvalue())
    pdf_stream.seek(0)
    return send_file(
        pdf_stream,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'{prestamo.numero_documento}.pdf',
    )


@admin.route('/download-pdf/<documento>')
@login_required
@admin_required
def download_pdf(documento):
    pdf_path = os.path.join(current_app.root_path, 'static', 'pdf', f'{documento}.pdf')
    if not os.path.exists(pdf_path):
        flash('El documento no está disponible.', 'danger')
        return redirect(url_for('admin.dashboard'))
    return send_file(pdf_path, mimetype='application/pdf', as_attachment=True, download_name=f'{documento}.pdf')


@admin.route('/prestamo/<int:prestamo_id>')
@login_required
@admin_required
def ver_prestamo(prestamo_id):
    prestamo = Prestamo.query.get_or_404(prestamo_id)
    hoy = get_bolivia_time()

    if prestamo.estado == 'activo' and prestamo.fecha_finalizacion < hoy:
        prestamo.estado = 'retencion'
        db.session.commit()

    return render_template(
        'admin/ver_prestamo.html',
        prestamo=prestamo,
        hoy=hoy,
        alertas=build_prestamo_alerts(prestamo, hoy),
        timeline=build_prestamo_timeline(prestamo),
        total_pago_requerido=resolve_total_payment_due(prestamo),
        whatsapp_url=prestamo.whatsapp_url,
    )


@admin.route('/editar-prestamo/<int:prestamo_id>', methods=['POST'])
@login_required
@admin_required
def editar_prestamo(prestamo_id):
    prestamo = Prestamo.query.get_or_404(prestamo_id)

    try:
        prestamo.monto_prestado = parse_positive_float(request.form.get('monto_prestado'), 'monto prestado')
        prestamo.interes_mensual = parse_interest(request.form.get('interes_mensual'))

        fecha_finalizacion_str = clean_text(request.form.get('fecha_finalizacion'))
        if fecha_finalizacion_str:
            fecha_finalizacion = datetime.strptime(fecha_finalizacion_str, '%Y-%m-%d')
            if (fecha_finalizacion.date() != prestamo.fecha_finalizacion.date()
                    and fecha_finalizacion.date() < get_bolivia_time().date()):
                raise ValueError('La fecha de vencimiento no puede ser anterior a hoy.')
            fecha_finalizacion = fecha_finalizacion.replace(
                hour=prestamo.fecha_finalizacion.hour,
                minute=prestamo.fecha_finalizacion.minute,
                second=prestamo.fecha_finalizacion.second,
                microsecond=prestamo.fecha_finalizacion.microsecond,
            )
            prestamo.fecha_finalizacion = fecha_finalizacion

        articulo_nombre = clean_text(request.form.get('articulo_nombre'))
        articulo_descripcion = clean_text(request.form.get('articulo_descripcion'))
        articulo = prestamo.articulos[0] if prestamo.articulos else None

        if articulo:
            if articulo_nombre:
                articulo.nombre = articulo_nombre
            articulo.descripcion = articulo_descripcion or articulo_nombre or articulo.descripcion
        elif articulo_nombre:
            db.session.add(
                Articulo(
                    prestamo_id=prestamo.id,
                    nombre=articulo_nombre,
                    descripcion=articulo_descripcion or articulo_nombre,
                    estado='empenado',
                )
            )

        db.session.commit()
        flash('Préstamo actualizado exitosamente.', 'success')
    except Exception as exc:
        db.session.rollback()
        flash(f'Error al editar préstamo: {exc}', 'danger')

    return redirect(url_for('admin.ver_prestamo', prestamo_id=prestamo.id))


@admin.route('/usuario/<int:usuario_id>/editar', methods=['POST'])
@login_required
@admin_required
def editar_usuario(usuario_id):
    usuario = Usuario.query.get_or_404(usuario_id)
    try:
        nombre = clean_text(request.form.get('nombre'))
        telefono = format_bolivian_phone(request.form.get('telefono'))
        if not nombre:
            raise ValueError('El nombre no puede estar vacío.')
        usuario.nombre = nombre
        usuario.telefono = telefono or None
        db.session.commit()
        flash('Cliente actualizado exitosamente.', 'success')
    except Exception as exc:
        db.session.rollback()
        flash(f'Error al actualizar el cliente: {exc}', 'danger')
    next_url = request.form.get('next') or url_for('admin.dashboard')
    return redirect(next_url)


@admin.route('/registrar-pago/<int:prestamo_id>', methods=['POST'])
@login_required
@admin_required
def registrar_pago(prestamo_id):
    prestamo = Prestamo.query.get_or_404(prestamo_id)

    try:
        tipo_pago = clean_text(request.form.get('tipo_pago'))
        if tipo_pago not in VALID_PAYMENT_TYPES:
            raise ValueError('Tipo de pago no válido.')
        if prestamo.estado not in {'activo', 'retencion'}:
            raise ValueError('Solo se pueden registrar pagos en préstamos activos o en retención.')

        monto = parse_positive_float(request.form.get('monto'), 'monto')

        if tipo_pago == 'interes':
            try:
                meses_pagados = max(1, int(request.form.get('meses_interes', 1)))
            except (ValueError, TypeError):
                meses_pagados = 1

            interes_requerido = round(prestamo.interes_un_mes * meses_pagados, 2)
            if monto < interes_requerido:
                raise ValueError(
                    f'El monto ingresado (Bs. {monto:.2f}) es menor al interés requerido para {meses_pagados} mes(es) (Bs. {interes_requerido:.2f}).'
                )

            nueva_fecha = prestamo.fecha_finalizacion + relativedelta(months=meses_pagados)
            prestamo.fecha_finalizacion = nueva_fecha
            ahora = get_bolivia_time()
            if nueva_fecha >= ahora:
                prestamo.estado = 'activo'
            prestamo.ultimo_pago = ahora
            prestamo.tipo_ultimo_pago = 'interes'
            prestamo.monto_ultimo_pago = monto

            db.session.add(Pago(
                prestamo_id=prestamo_id,
                tipo_pago='interes',
                monto_pagado=monto,
                fecha_pago=ahora,
            ))
            db.session.commit()
            flash(
                f'Pago de interés ({meses_pagados} mes/es) registrado exitosamente. Nuevo vencimiento: {prestamo.fecha_finalizacion.strftime("%d/%m/%Y")}.',
                'success',
            )
        else:
            total_a_pagar = round(prestamo.monto_liquidacion_actual, 2)
            if monto < total_a_pagar:
                raise ValueError(
                    f'El monto ingresado (Bs. {monto:.2f}) es menor al total requerido para liquidar (Bs. {total_a_pagar:.2f}).'
                )

            ahora = get_bolivia_time()
            db.session.add(Pago(
                prestamo_id=prestamo_id,
                tipo_pago='total',
                monto_pagado=monto,
                fecha_pago=ahora,
            ))
            prestamo.estado = 'finalizado'
            prestamo.ultimo_pago = ahora
            prestamo.tipo_ultimo_pago = 'total'
            prestamo.monto_ultimo_pago = monto
            db.session.commit()
            flash('Pago total registrado exitosamente. El préstamo fue finalizado y la prenda liberada.', 'success')
    except Exception as exc:
        db.session.rollback()
        flash(str(exc), 'danger')

    return redirect(url_for('admin.ver_prestamo', prestamo_id=prestamo_id))


@admin.route('/cambiar-estado/<int:prestamo_id>', methods=['POST'])
@login_required
@admin_required
def cambiar_estado(prestamo_id):
    prestamo = Prestamo.query.get_or_404(prestamo_id)
    nuevo_estado = clean_text(request.form.get('estado'))

    if nuevo_estado not in VALID_LOAN_STATES:
        flash('Estado no válido.', 'danger')
        return redirect(url_for('admin.ver_prestamo', prestamo_id=prestamo.id))

    prestamo.estado = nuevo_estado
    db.session.commit()
    flash(f'Estado del préstamo actualizado a: {nuevo_estado}.', 'success')
    return redirect(url_for('admin.ver_prestamo', prestamo_id=prestamo.id))


@admin.route('/decomisar-a-inventario/<int:prestamo_id>', methods=['POST'])
@login_required
@admin_required
def decomisar_a_inventario(prestamo_id):
    prestamo = Prestamo.query.get_or_404(prestamo_id)
    if prestamo.estado not in {'retencion', 'activo'}:
        flash('Solo se pueden decomisar préstamos activos o en retención.', 'warning')
        return redirect(url_for('admin.ver_prestamo', prestamo_id=prestamo.id))

    try:
        precio_venta_input = request.form.get('precio_venta')
        precio_venta = parse_positive_float(precio_venta_input, 'precio de venta') if precio_venta_input else prestamo.monto_prestado

        articulo = prestamo.articulos[0] if prestamo.articulos else None
        nombre_prod = articulo.nombre if articulo and articulo.nombre else f'Artículo de Préstamo {prestamo.numero_documento}'
        desc_prod = articulo.descripcion if articulo and articulo.descripcion else f'Garantía de préstamo {prestamo.numero_documento}'

        producto = ProductoVenta(
            nombre=nombre_prod,
            descripcion=desc_prod,
            precio=precio_venta,
            precio_compra=prestamo.monto_prestado,
            stock=1,
            stock_inicial=1,
            proveedor=f'Empeño {prestamo.numero_documento} ({prestamo.usuario.nombre})',
            tipo='venta',
            estado='disponible',
            fecha_publicacion=get_bolivia_time(),
        )
        prestamo.estado = 'decomisado'
        if articulo:
            articulo.estado = 'decomisado'

        db.session.add(producto)
        db.session.commit()
        flash(f'Artículo "{nombre_prod}" decomisado y añadido al inventario de venta a Bs. {precio_venta:.2f}.', 'success')
    except Exception as exc:
        db.session.rollback()
        flash(f'Error al decomisar artículo: {exc}', 'danger')

    return redirect(url_for('admin.ver_prestamo', prestamo_id=prestamo.id))
