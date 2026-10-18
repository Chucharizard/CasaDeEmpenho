from app.utils import get_bolivia_time, normalize_ci

from dateutil.relativedelta import relativedelta
from flask import jsonify, render_template, request, session, url_for
from flask_login import login_required
from sqlalchemy import func, or_
from sqlalchemy.orm import joinedload, selectinload

from app import db
from app.models import Articulo, Prestamo, Usuario
from app.routes.admin_shared import admin, admin_required


@admin.route('/dashboard')
@login_required
@admin_required
def dashboard():
    search_ci = (request.args.get('search_ci') or '').strip()
    search_nombre = (request.args.get('search_nombre') or '').strip()
    search_cliente = (request.args.get('search_cliente') or '').strip()
    estado_filter = request.args.get('estado', 'todos')
    order = request.args.get('order', 'fecha_desc')

    if search_cliente:
        search_ci = search_cliente
        search_nombre = search_cliente

    query = Prestamo.query.join(Usuario).options(joinedload(Prestamo.usuario), selectinload(Prestamo.articulos), selectinload(Prestamo.pagos))

    if search_ci:
        query = query.filter(
            or_(
                Usuario.ci.ilike(f'%{search_ci}%'),
                Usuario.nombre.ilike(f'%{search_ci}%'),
                Prestamo.articulos.any(Articulo.nombre.ilike(f'%{search_ci}%')),
            )
        )
    if search_nombre and search_nombre != search_ci:
        query = query.filter(
            or_(
                Usuario.nombre.ilike(f'%{search_nombre}%'),
                Prestamo.articulos.any(Articulo.nombre.ilike(f'%{search_nombre}%')),
            )
        )

    hoy = get_bolivia_time()
    limite_vencimiento = hoy + relativedelta(days=7)

    if estado_filter == 'por_vencer':
        query = query.filter(
            Prestamo.estado == 'activo',
            Prestamo.fecha_finalizacion <= limite_vencimiento,
            Prestamo.fecha_finalizacion >= hoy,
        )
    elif estado_filter != 'todos':
        query = query.filter(Prestamo.estado == estado_filter)

    query = query.filter(Prestamo.tipo_prestamo == 'prendario')

    if order == 'fecha_asc':
        query = query.order_by(Prestamo.fecha_inicio.asc())
    elif order == 'monto_desc':
        query = query.order_by(Prestamo.monto_prestado.desc())
    elif order == 'monto_asc':
        query = query.order_by(Prestamo.monto_prestado.asc())
    elif order == 'nombre_asc':
        query = query.order_by(Usuario.nombre.asc())
    elif order == 'nombre_desc':
        query = query.order_by(Usuario.nombre.desc())
    else:
        query = query.order_by(Prestamo.fecha_inicio.desc())

    # Actualización por lotes optimizada en la base de datos para préstamos vencidos
    actualizados_count = Prestamo.query.filter(
        Prestamo.estado == 'activo',
        Prestamo.fecha_finalizacion < hoy
    ).update({Prestamo.estado: 'retencion'}, synchronize_session=False)

    if actualizados_count > 0:
        db.session.commit()

    chart_counts = dict(query.order_by(None).with_entities(Prestamo.estado, func.count(Prestamo.id)).group_by(Prestamo.estado).all())
    prestamos_por_vencer_count = query.order_by(None).filter(
        Prestamo.estado == 'activo', Prestamo.fecha_finalizacion >= hoy,
        Prestamo.fecha_finalizacion <= limite_vencimiento).count()
    pagination = query.order_by(Prestamo.id.desc()).paginate(
        page=max(1, request.args.get('page', 1, type=int)), per_page=50, error_out=False)
    prestamos = pagination.items
    def page_url(page):
        args = request.args.to_dict()
        args['page'] = page
        return url_for('admin.dashboard', **args)

    totales = {'activo': {'cantidad': 0, 'total': 0.0}, 'retencion': {'cantidad': 0, 'total': 0.0}}
    totales_query = (
        db.session.query(
            Prestamo.estado,
            func.count(Prestamo.id),
            func.coalesce(func.sum(Prestamo.monto_prestado), 0.0)
        )
        .filter(Prestamo.tipo_prestamo == 'prendario', Prestamo.estado.in_(['activo', 'retencion']))
        .group_by(Prestamo.estado)
        .all()
    )
    for estado, cant, total in totales_query:
        if estado in totales:
            totales[estado] = {'cantidad': cant, 'total': float(total)}

    pdf_prestamo_id = session.pop('pdf_prestamo_id', None) or session.pop('pdf_prestamo_anterior_id', None)

    return render_template(
        'admin/dashboard.html',
        prestamos=prestamos,
        pagination=pagination,
        page_url=page_url,
        chart_counts=[chart_counts.get(estado, 0) for estado in ('activo', 'retencion', 'finalizado', 'decomisado')],
        hoy=hoy,
        total_activos=totales['activo']['total'],
        total_retencion=totales['retencion']['total'],
        total_prestado=totales['activo']['total'] + totales['retencion']['total'],
        count_activos=totales['activo']['cantidad'],
        count_retencion=totales['retencion']['cantidad'],
        count_total=totales['activo']['cantidad'] + totales['retencion']['cantidad'],
        pdf_prestamo_id=pdf_prestamo_id,
        search_ci=search_ci,
        search_nombre=search_nombre,
        estado_filter=estado_filter,
        order=order,
        prestamos_por_vencer=prestamos_por_vencer_count,
    )


@admin.route('/clientes')
@login_required
@admin_required
def clientes():
    clientes_list = Usuario.query.filter_by(es_admin=False).options(selectinload(Usuario.prestamos)).all()
    total_clientes = len(clientes_list)
    clientes_activos = sum(1 for cliente in clientes_list if any(prestamo.estado == 'activo' for prestamo in cliente.prestamos))
    total_prestamos = sum(len(cliente.prestamos) for cliente in clientes_list)
    monto_total = sum(sum(prestamo.monto_prestado for prestamo in cliente.prestamos) for cliente in clientes_list)

    return render_template(
        'admin/clientes.html',
        clientes=clientes_list,
        total_clientes=total_clientes,
        clientes_activos=clientes_activos,
        total_prestamos=total_prestamos,
        monto_total=monto_total,
    )


@admin.route('/api/buscar-usuario/<ci>')
@login_required
@admin_required
def buscar_usuario_por_ci(ci):
    usuario = Usuario.por_ci(ci)
    if usuario:
        total_prestamos = len(usuario.prestamos)
        prestamos_activos = sum(1 for prestamo in usuario.prestamos if prestamo.estado == 'activo')
        return jsonify({
            'encontrado': True,
            'ci': usuario.ci,
            'nombre': usuario.nombre,
            'telefono': usuario.telefono or '',
            'total_prestamos': total_prestamos,
            'mensaje': f'Cliente encontrado con {total_prestamos} prestamo(s)',
            'prestamos_activos': prestamos_activos,
        })

    return jsonify({'encontrado': False, 'mensaje': 'Cliente nuevo - Complete los datos'})
