from app.utils import get_bolivia_time, format_bolivian_phone
import logging
import os
import threading
import traceback
from datetime import datetime
from io import BytesIO
import urllib.parse

from flask import current_app, flash, redirect, render_template, request, send_file, session, url_for
from flask_login import login_required

from dateutil.relativedelta import relativedelta
from sqlalchemy.orm import joinedload

from app import db
from app.models import Articulo, Prestamo, ProductoVenta, Usuario, Configuracion
from app.models.prestamo import Pago
from app.services.pdf_service import generar_documento_legal, generar_comprobante_pago, generar_comprobante_imagen
from app.services import whatsapp_service
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


@admin.route('/descargar-comprobante/<int:pago_id>')
@login_required
@admin_required
def descargar_comprobante_pago(pago_id):
    pago = db.session.get(Pago, pago_id)
    if not pago:
        flash('Pago no encontrado.', 'danger')
        return redirect(url_for('admin.dashboard'))

    prestamo = pago.prestamo
    usuario = prestamo.usuario
    articulos_desc = ", ".join(a.nombre for a in prestamo.articulos) if prestamo.articulos else 'Garantía prendaria'

    meses_pagados = 1
    if pago.tipo_pago == 'interes' and prestamo.interes_un_mes > 0:
        meses_pagados = max(1, int(round(pago.monto_pagado / prestamo.interes_un_mes)))

    pdf_data = generar_comprobante_pago({
        'numero_recibo': f"REC-{pago.id:05d}",
        'fecha_pago': pago.fecha_pago,
        'numero_documento': prestamo.numero_documento,
        'numero_prestamo': prestamo.numero_prestamo,
        'nombre_cliente': usuario.nombre if usuario else 'N/A',
        'ci_cliente': usuario.ci if usuario else 'N/A',
        'telefono_cliente': usuario.telefono if (usuario and usuario.telefono) else 'No registrado',
        'articulos_descripcion': articulos_desc,
        'tipo_pago': pago.tipo_pago,
        'meses_pagados': meses_pagados,
        'monto_pagado': pago.monto_pagado,
        'monto_prestado': prestamo.monto_prestado,
        'fecha_vencimiento': prestamo.fecha_finalizacion,
    })

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
    usuario = prestamo.usuario
    articulos_desc = ", ".join(a.nombre for a in prestamo.articulos) if prestamo.articulos else 'Garantía prendaria'

    meses_pagados = 1
    if pago.tipo_pago == 'interes' and prestamo.interes_un_mes > 0:
        meses_pagados = max(1, int(round(pago.monto_pagado / prestamo.interes_un_mes)))

    img_data = generar_comprobante_imagen({
        'numero_recibo': f"REC-{pago.id:05d}",
        'fecha_pago': pago.fecha_pago,
        'numero_documento': prestamo.numero_documento,
        'numero_prestamo': prestamo.numero_prestamo,
        'nombre_cliente': usuario.nombre if usuario else 'N/A',
        'ci_cliente': usuario.ci if usuario else 'N/A',
        'telefono_cliente': usuario.telefono if (usuario and usuario.telefono) else 'No registrado',
        'articulos_descripcion': articulos_desc,
        'tipo_pago': pago.tipo_pago,
        'meses_pagados': meses_pagados,
        'monto_pagado': pago.monto_pagado,
        'monto_prestado': prestamo.monto_prestado,
        'fecha_vencimiento': prestamo.fecha_finalizacion,
    })

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
    prestamo = Prestamo.query.get_or_404(prestamo_id)
    hoy = get_bolivia_time()

    if prestamo.estado == 'activo' and prestamo.fecha_finalizacion < hoy:
        prestamo.estado = 'retencion'
        db.session.commit()

    pdf_pago_id = session.pop('pdf_pago_id', None)
    pago_reciente = db.session.get(Pago, pdf_pago_id) if pdf_pago_id else None

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


logger = logging.getLogger(__name__)


def _enviar_recibo_whatsapp(pago_id, app):
    """Envía el recibo como imagen por WhatsApp en un hilo de fondo.

    Se ejecuta en un thread separado para no bloquear la respuesta HTTP.
    Si el bot no está conectado o falla, simplemente logueamos y seguimos.
    """
    if app.config.get('TESTING'):
        return

    try:
        with app.app_context():
            if not whatsapp_service.esta_conectado():
                logger.info('WhatsApp Bot no conectado — recibo no enviado.')
                return

            pago = Pago.query.get(pago_id)
            if not pago or not pago.prestamo:
                return

            prestamo = pago.prestamo
            usuario = prestamo.usuario

            telefono = prestamo.telefono_whatsapp
            if not telefono:
                logger.info(f'Pago #{pago_id}: cliente sin teléfono registrado.')
                return

            # Construir el dict con los datos necesarios para la imagen
            articulos_desc = ", ".join(
                a.nombre for a in prestamo.articulos
            ) if prestamo.articulos else 'Garantía prendaria'

            meses_pagados = 1
            if pago.tipo_pago == 'interes' and prestamo.interes_un_mes > 0:
                meses_pagados = max(1, int(round(pago.monto_pagado / prestamo.interes_un_mes)))

            img_buffer = generar_comprobante_imagen({
                'numero_recibo': f"REC-{pago.id:05d}",
                'fecha_pago': pago.fecha_pago,
                'numero_documento': prestamo.numero_documento,
                'numero_prestamo': prestamo.numero_prestamo,
                'nombre_cliente': usuario.nombre if usuario else 'N/A',
                'ci_cliente': usuario.ci if usuario else 'N/A',
                'telefono_cliente': usuario.telefono if (usuario and usuario.telefono) else 'No registrado',
                'articulos_descripcion': articulos_desc,
                'tipo_pago': pago.tipo_pago,
                'meses_pagados': meses_pagados,
                'monto_pagado': pago.monto_pagado,
                'monto_prestado': prestamo.monto_prestado,
                'fecha_vencimiento': prestamo.fecha_finalizacion,
            })

            if not img_buffer:
                logger.warning(f'Pago #{pago_id}: no se pudo generar imagen.')
                return

            imagen_bytes = img_buffer.getvalue()

            # Preparar caption
            tipo_label = 'Pago Total (Liquidación)' if pago.tipo_pago == 'total' else 'Pago de Interés'
            caption = f'🧾 {tipo_label} - Casa de Empeño'

            resultado = whatsapp_service.enviar_imagen(telefono, imagen_bytes, caption)
            if resultado.get('success'):
                logger.info(f'✅ Recibo #{pago_id} enviado por WhatsApp a +{telefono}')
            else:
                logger.warning(f'❌ Recibo #{pago_id} NO enviado: {resultado.get("error")}')
    except Exception as e:
        logger.error(f'Error al enviar recibo WhatsApp (pago #{pago_id}): {e}')


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

            nuevo_pago = Pago(
                prestamo_id=prestamo_id,
                tipo_pago='interes',
                monto_pagado=monto,
                fecha_pago=ahora,
            )
            db.session.add(nuevo_pago)
            db.session.commit()
            session['pdf_pago_id'] = nuevo_pago.id

            # Despachar automáticamente o solicitar confirmación según configuración
            whatsapp_auto = Configuracion.get_valor('whatsapp_auto_envio', 'true') == 'true'
            if whatsapp_auto:
                threading.Thread(
                    target=_enviar_recibo_whatsapp,
                    args=(nuevo_pago.id, current_app._get_current_object()),
                    daemon=True,
                ).start()
            else:
                session['preguntar_envio_whatsapp_pago_id'] = nuevo_pago.id

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
            nuevo_pago = Pago(
                prestamo_id=prestamo_id,
                tipo_pago='total',
                monto_pagado=monto,
                fecha_pago=ahora,
            )
            db.session.add(nuevo_pago)
            prestamo.estado = 'finalizado'
            prestamo.ultimo_pago = ahora
            prestamo.tipo_ultimo_pago = 'total'
            prestamo.monto_ultimo_pago = monto
            db.session.commit()
            session['pdf_pago_id'] = nuevo_pago.id

            # Despachar automáticamente o solicitar confirmación según configuración
            whatsapp_auto = Configuracion.get_valor('whatsapp_auto_envio', 'true') == 'true'
            if whatsapp_auto:
                threading.Thread(
                    target=_enviar_recibo_whatsapp,
                    args=(nuevo_pago.id, current_app._get_current_object()),
                    daemon=True,
                ).start()
            else:
                session['preguntar_envio_whatsapp_pago_id'] = nuevo_pago.id

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
