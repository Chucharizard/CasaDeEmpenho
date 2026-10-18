from app.utils import get_bolivia_time, format_bolivian_phone, normalize_ci, local_redirect_target
import logging
import os
import threading
import traceback
from datetime import datetime
from io import BytesIO

from flask import current_app, flash, redirect, render_template, request, send_file, session, url_for
from flask_login import login_required

from dateutil.relativedelta import relativedelta
from sqlalchemy.exc import IntegrityError
from app.services.receipt_service import capture_receipt, build_receipt_data
from app.services.loan_service import transition_loan, record_change, audit_snapshot, validate_operation_id

from app import db
from app.models import Articulo, Prestamo, Usuario, Configuracion
from app.models.prestamo import Pago
from app.services.pdf_service import generar_documento_legal, generar_comprobante_pago, generar_comprobante_imagen
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


@admin.route('/nuevo-prestamo', methods=['GET', 'POST'])
@login_required
@admin_required
def nuevo_prestamo():
    if request.method == 'POST':
        ci = normalize_ci(request.form.get('ci'))
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

            usuario = Usuario.por_ci(ci)
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
            record_change(prestamo, 'Crear préstamo')
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

    return render_template('admin/nuevo_prestamo.html', tasa_interes=get_tasa_configurada('interes_prendario', 10.0))


@admin.route('/prestamo-anterior', methods=['GET', 'POST'])
@login_required
@admin_required
def prestamo_anterior():
    if request.method == 'POST':
        ci = normalize_ci(request.form.get('ci'))
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
            if fecha_inicio.date() > get_bolivia_time().date():
                raise ValueError('La fecha de un préstamo anterior no puede ser futura.')

            usuario = Usuario.por_ci(ci)
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
            record_change(prestamo, 'Crear préstamo')
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

    return render_template('admin/prestamo_anterior.html', tasa_interes=get_tasa_configurada('interes_prendario', 10.0))


@admin.route('/descargar-documento/<int:prestamo_id>')
@login_required
@admin_required
def descargar_documento(prestamo_id):
    prestamo = db.get_or_404(Prestamo, prestamo_id)
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


@admin.route('/descargar-comprobante/<int:pago_id>')
@login_required
@admin_required
def descargar_comprobante_pago(pago_id):
    pago = db.session.get(Pago, pago_id)
    if not pago:
        flash('Pago no encontrado.', 'danger')
        return redirect(url_for('admin.dashboard'))

    prestamo = pago.prestamo
    pdf_data = generar_comprobante_pago(build_receipt_data(pago))

    pdf_stream = BytesIO(pdf_data.getvalue())
    pdf_stream.seek(0)
    filename = f"recibo_{pago.id:05d}_{prestamo.numero_documento}.pdf"
    return send_file(
        pdf_stream,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=filename,
    )


@admin.route('/recibo-imagen/<int:pago_id>')
@login_required
@admin_required
def recibo_imagen(pago_id):
    pago = db.session.get(Pago, pago_id)
    if not pago:
        flash('Pago no encontrado.', 'danger')
        return redirect(url_for('admin.dashboard'))

    prestamo = pago.prestamo
    img_data = generar_comprobante_imagen(build_receipt_data(pago))

    img_stream = BytesIO(img_data.getvalue())
    img_stream.seek(0)
    filename = f"recibo_{pago.id:05d}_{prestamo.numero_documento}.png"
    return send_file(
        img_stream,
        mimetype='image/png',
        as_attachment=False,
        download_name=filename,
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
    prestamo = db.get_or_404(Prestamo, prestamo_id)
    hoy = get_bolivia_time()

    if prestamo.estado == 'activo' and prestamo.fecha_finalizacion < hoy:
        prestamo.estado = 'retencion'
        db.session.commit()

    pdf_pago_id = session.pop('pdf_pago_id', None)
    pago_reciente = db.session.get(Pago, pdf_pago_id) if pdf_pago_id else None
    if pago_reciente and pago_reciente.prestamo_id != prestamo.id:
        pago_reciente = None
        pdf_pago_id = None

    prompt_pago_id = session.pop('preguntar_envio_whatsapp_pago_id', None)
    prompt_pago = db.session.get(Pago, prompt_pago_id) if prompt_pago_id else None
    if not prompt_pago or prompt_pago.prestamo_id != prestamo.id:
        prompt_pago_id = None

    return render_template(
        'admin/ver_prestamo.html',
        prestamo=prestamo,
        hoy=hoy,
        alertas=build_prestamo_alerts(prestamo, hoy),
        timeline=build_prestamo_timeline(prestamo),
        total_pago_requerido=resolve_total_payment_due(prestamo),
        whatsapp_url=prestamo.whatsapp_url,
        pdf_pago_id=pdf_pago_id,
        pago_reciente=pago_reciente,
        prompt_pago_id=prompt_pago_id,
        interes_maximo=get_tasa_configurada('interes_maximo', 25.0),
    )


@admin.route('/editar-prestamo/<int:prestamo_id>', methods=['POST'])
@login_required
@admin_required
def editar_prestamo(prestamo_id):
    prestamo = db.get_or_404(Prestamo, prestamo_id)

    try:
        before = audit_snapshot(prestamo)
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

        record_change(prestamo, 'Editar préstamo', before)
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
    usuario = db.get_or_404(Usuario, usuario_id)
    try:
        before = audit_snapshot(usuario)
        nombre = clean_text(request.form.get('nombre'))
        telefono = format_bolivian_phone(request.form.get('telefono'))
        if not nombre:
            raise ValueError('El nombre no puede estar vacío.')
        usuario.nombre = nombre
        usuario.telefono = telefono or None
        record_change(usuario, 'Editar cliente', before)
        db.session.commit()
        flash('Cliente actualizado exitosamente.', 'success')
    except Exception as exc:
        db.session.rollback()
        flash(f'Error al actualizar el cliente: {exc}', 'danger')
    next_url = local_redirect_target(request.form.get('next'), url_for('admin.dashboard'))
    return redirect(next_url)


logger = logging.getLogger(__name__)


def _enviar_recibo_whatsapp(pago_id, app):
    if app.config.get('TESTING'):
        return
    from app.services.delivery_service import send_receipt
    with app.app_context(), app.extensions['database_lock']:
        send_receipt(pago_id)


@admin.route('/registrar-pago/<int:prestamo_id>', methods=['POST'])
@login_required
@admin_required
def registrar_pago(prestamo_id):
    prestamo = db.get_or_404(Prestamo, prestamo_id)
    operacion_id = None
    try:
        operacion_id = validate_operation_id(request.form.get('operacion_id'))
        tipo_pago = clean_text(request.form.get('tipo_pago'))
        if tipo_pago not in VALID_PAYMENT_TYPES:
            raise ValueError('Tipo de pago no válido.')
        monto = parse_positive_float(request.form.get('monto'), 'monto')
        meses = 0
        if tipo_pago == 'interes':
            try:
                meses = int(request.form.get('meses_interes', 1))
            except (ValueError, TypeError) as exc:
                raise ValueError('Los meses de interés deben ser enteros.') from exc
            if not 1 <= meses <= 1200:
                raise ValueError('La cantidad de meses debe estar entre 1 y 1200.')
        anterior = Pago.query.filter_by(operacion_id=operacion_id).first()
        if anterior:
            if (anterior.prestamo_id, anterior.tipo_pago, anterior.monto_pagado, anterior.meses_pagados) != (prestamo_id, tipo_pago, monto, meses):
                raise ValueError('El identificador ya pertenece a otra operación.')
            session['pdf_pago_id'] = anterior.id
            flash('Este pago ya fue registrado. Se muestra el comprobante original.', 'info')
            return redirect(url_for('admin.ver_prestamo', prestamo_id=prestamo_id))
        if prestamo.estado not in {'activo', 'retencion'}:
            raise ValueError('Solo se pueden registrar pagos en préstamos activos o en retención.')
        requerido = round(prestamo.interes_un_mes * meses, 2) if tipo_pago == 'interes' else prestamo.monto_liquidacion_actual
        if monto < requerido:
            raise ValueError(f'El monto ingresado (Bs. {monto:.2f}) es menor al requerido (Bs. {requerido:.2f}).')
        ahora = get_bolivia_time()
        before = audit_snapshot(prestamo)
        if tipo_pago == 'interes':
            prestamo.fecha_finalizacion += relativedelta(months=meses)
            transition_loan(prestamo, 'activo' if prestamo.fecha_finalizacion >= ahora else 'retencion', before=before)
        else:
            transition_loan(prestamo, 'finalizado', before=before)
        prestamo.ultimo_pago = ahora
        prestamo.tipo_ultimo_pago = tipo_pago
        prestamo.monto_ultimo_pago = monto
        automatico = Configuracion.get_valor('whatsapp_auto_envio', 'true') == 'true'
        pago = Pago(prestamo_id=prestamo.id, tipo_pago=tipo_pago, monto_pagado=monto,
                    fecha_pago=ahora, meses_pagados=meses, operacion_id=operacion_id,
                    whatsapp_estado='pendiente' if automatico else 'no_solicitado')
        db.session.add(pago)
        db.session.flush()
        capture_receipt(pago, prestamo, meses=meses, importe_requerido=requerido)
        record_change(pago, 'Registrar pago')
        db.session.commit()
        session['pdf_pago_id'] = pago.id
        if automatico:
            if not current_app.config.get('TESTING'):
                try:
                    threading.Thread(target=_enviar_recibo_whatsapp,
                                     args=(pago.id, current_app._get_current_object()), daemon=True).start()
                except RuntimeError:
                    logger.exception('Pago guardado; el recibo queda pendiente de envío')
        else:
            session['preguntar_envio_whatsapp_pago_id'] = pago.id
        if tipo_pago == 'interes':
            flash(f'Pago de interés ({meses} mes/es) registrado exitosamente. Nuevo vencimiento: {prestamo.fecha_finalizacion:%d/%m/%Y}.', 'success')
        else:
            flash('Pago total registrado exitosamente. El préstamo fue finalizado y la prenda liberada.', 'success')
    except IntegrityError:
        db.session.rollback()
        anterior = Pago.query.filter_by(operacion_id=operacion_id).first() if operacion_id else None
        if anterior and anterior.prestamo_id == prestamo_id:
            session['pdf_pago_id'] = anterior.id
            flash('Este pago ya fue registrado.', 'info')
        else:
            logger.exception('No se pudo registrar el pago')
            flash('No se pudo registrar el pago. Recarga la página e intenta nuevamente.', 'danger')
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), 'danger')
    except Exception:
        db.session.rollback()
        logger.exception('Error al registrar pago')
        flash('No se pudo registrar el pago. Intenta nuevamente.', 'danger')
    return redirect(url_for('admin.ver_prestamo', prestamo_id=prestamo_id))


@admin.route('/cambiar-estado/<int:prestamo_id>', methods=['POST'])
@login_required
@admin_required
def cambiar_estado(prestamo_id):
    prestamo = db.get_or_404(Prestamo, prestamo_id)
    nuevo_estado = clean_text(request.form.get('estado'))

    if nuevo_estado not in VALID_LOAN_STATES:
        flash('Estado no válido.', 'danger')
        return redirect(url_for('admin.ver_prestamo', prestamo_id=prestamo.id))

    try:
        transition_loan(prestamo, nuevo_estado, motivo=clean_text(request.form.get('motivo')))
        db.session.commit()
        estado_visible = {'activo': 'Activo', 'retencion': 'En retención',
                          'finalizado': 'Finalizado', 'decomisado': 'En venta'}[nuevo_estado]
        flash(f'Estado del préstamo actualizado a: {estado_visible}.', 'success')
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), 'danger')
    return redirect(url_for('admin.ver_prestamo', prestamo_id=prestamo.id))


@admin.route('/decomisar-a-inventario/<int:prestamo_id>', methods=['POST'])
@login_required
@admin_required
def decomisar_a_inventario(prestamo_id):
    prestamo = db.get_or_404(Prestamo, prestamo_id)
    if prestamo.estado not in {'retencion', 'activo'}:
        flash('Solo se pueden poner en venta garantías de préstamos activos o en retención.', 'warning')
        return redirect(url_for('admin.ver_prestamo', prestamo_id=prestamo.id))

    try:
        precio_venta_input = request.form.get('precio_venta')
        precio_venta = parse_positive_float(precio_venta_input, 'precio de venta') if precio_venta_input else prestamo.monto_prestado

        transition_loan(prestamo, 'decomisado', precio_venta=precio_venta,
                        motivo=clean_text(request.form.get('motivo')))
        db.session.commit()
        flash(f'Garantía puesta en venta a Bs. {precio_venta:.2f}.', 'success')
    except Exception as exc:
        db.session.rollback()
        flash(f'Error al poner el artículo en venta: {exc}', 'danger')

    return redirect(url_for('admin.ver_prestamo', prestamo_id=prestamo.id))
