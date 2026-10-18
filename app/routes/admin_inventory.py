from app.utils import get_bolivia_time

from flask import flash, redirect, render_template, request, url_for
from flask_login import login_required

from app import db
from app.models import Articulo, Prestamo, ProductoVenta, Venta
from app.services.loan_service import audit_snapshot, record_change, validate_operation_id
from app.routes.admin_shared import admin, admin_required, clean_text, parse_non_negative_int, parse_positive_float


@admin.route('/inventario')
@login_required
@admin_required
def inventario():
    tab = request.args.get('tab', 'venta')

    if tab == 'compra':
        productos = ProductoVenta.query.filter_by(tipo='compra').all()
    elif tab == 'vendidos':
        productos = Venta.query.order_by(Venta.fecha_venta.desc()).all()
    else:
        productos = ProductoVenta.query.filter_by(estado='disponible').all()

    total_invertido = db.session.query(
        db.func.sum(ProductoVenta.precio_compra * ProductoVenta.stock)
    ).filter(
        ProductoVenta.estado.in_(['compra', 'disponible']),
        ProductoVenta.precio_compra.isnot(None),
    ).scalar() or 0

    ventas = Venta.query.order_by(Venta.fecha_venta.desc()).all()
    total_vendido = sum(venta.precio for venta in ventas)
    total_costo = sum(venta.precio_compra or 0 for venta in ventas)
    ganancia_total = total_vendido - total_costo
    articulos_stock = Articulo.query.join(Prestamo).filter(Prestamo.estado == 'retencion').all()
    historial_incompleto = ProductoVenta.query.filter(
        ProductoVenta.fecha_venta.isnot(None),
        ~ProductoVenta.id.in_(db.session.query(Venta.producto_id)),
    ).all()

    return render_template(
        'admin/inventario.html',
        productos=productos,
        tab=tab,
        total_invertido=total_invertido,
        ventas=ventas,
        total_vendido=total_vendido,
        total_costo=total_costo,
        ganancia_total=ganancia_total,
        articulos_stock=articulos_stock,
        historial_incompleto=historial_incompleto,
    )


@admin.route('/nuevo-producto', methods=['GET', 'POST'])
@login_required
@admin_required
def nuevo_producto():
    if request.method == 'POST':
        try:
            tipo = clean_text(request.form.get('tipo') or 'venta')
            if tipo not in {'compra', 'venta'}:
                raise ValueError('Tipo de producto no válido.')
            nombre = clean_text(request.form.get('nombre'))
            descripcion = clean_text(request.form.get('descripcion'))
            proveedor = clean_text(request.form.get('proveedor'))
            stock = parse_non_negative_int(request.form.get('stock', 1), 'stock')

            if not nombre:
                raise ValueError('El nombre del producto es obligatorio.')
            if stock <= 0:
                raise ValueError('El stock debe ser mayor a 0.')

            if tipo == 'venta':
                precio = parse_positive_float(request.form.get('precio'), 'precio de venta')
                precio_compra = None
                estado = 'disponible'
            else:
                precio_compra = parse_positive_float(request.form.get('precio_compra'), 'precio de compra')
                precio = precio_compra
                estado = 'compra'

            producto = ProductoVenta(
                nombre=nombre,
                descripcion=descripcion,
                precio=precio,
                precio_compra=precio_compra,
                stock=stock,
                stock_inicial=stock,
                proveedor=proveedor,
                tipo=tipo,
                estado=estado,
                fecha_publicacion=get_bolivia_time(),
            )
            db.session.add(producto)
            db.session.commit()
            flash('Producto agregado exitosamente.', 'success')
            return redirect(url_for('admin.inventario', tab=tipo))
        except Exception as exc:
            db.session.rollback()
            flash(f'Error al guardar producto: {exc}', 'danger')

    return render_template('admin/nuevo_producto.html', tipo=request.args.get('tipo', 'venta'))


@admin.route('/editar-producto/<int:producto_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def editar_producto(producto_id):
    producto = db.get_or_404(ProductoVenta, producto_id)
    if request.method == 'POST':
        try:
            before = audit_snapshot(producto)
            nombre = clean_text(request.form.get('nombre'))
            if not nombre:
                raise ValueError('El nombre del producto es obligatorio.')

            producto.nombre = nombre
            producto.descripcion = clean_text(request.form.get('descripcion'))
            producto.precio = parse_positive_float(request.form.get('precio'), 'precio de venta')

            if request.form.get('precio_compra'):
                producto.precio_compra = parse_positive_float(request.form.get('precio_compra'), 'precio de compra')

            producto.stock = parse_non_negative_int(request.form.get('stock', producto.stock), 'stock')
            proveedor = clean_text(request.form.get('proveedor'))
            if proveedor:
                producto.proveedor = proveedor
            record_change(producto, 'Editar producto', before)
            db.session.commit()
            flash('Producto actualizado exitosamente.', 'success')
            return redirect(url_for('admin.inventario', tab=producto.tipo))
        except Exception as exc:
            db.session.rollback()
            flash(f'Error al actualizar producto: {exc}', 'danger')

    return render_template('admin/editar_producto.html', producto=producto)


@admin.route('/vender-producto/<int:producto_id>', methods=['POST'])
@login_required
@admin_required
def vender_producto(producto_id):
    producto = db.get_or_404(ProductoVenta, producto_id)

    try:
        operacion_id = validate_operation_id(request.form.get('operacion_id'))
        precio_final = parse_positive_float(request.form.get('precio_final', producto.precio), 'precio final')
        existente = Venta.query.filter_by(operacion_id=operacion_id).first()
        if existente:
            if existente.producto_id != producto.id or existente.precio_unitario != precio_final:
                raise ValueError('El identificador pertenece a otra venta.')
            flash('Esta venta ya fue registrada.', 'info')
            return redirect(url_for('admin.inventario', tab='venta'))
        if producto.estado != 'disponible' or producto.tipo != 'venta':
            raise ValueError('El producto no está disponible para venta.')
        before = audit_snapshot(producto)
        # La condición también evita vender la última unidad desde dos procesos.
        updated = ProductoVenta.query.filter(ProductoVenta.id == producto.id, ProductoVenta.stock > 0,
                                            ProductoVenta.estado == 'disponible').update(
            {ProductoVenta.stock: ProductoVenta.stock - 1}, synchronize_session=False)
        if not updated:
            raise ValueError('No hay stock disponible.')
        db.session.refresh(producto)
        if producto.stock == 0:
            producto.estado = 'vendido'
        producto.fecha_venta = get_bolivia_time()
        db.session.add(Venta(producto_id=producto.id, operacion_id=operacion_id,
                             nombre=producto.nombre, descripcion=producto.descripcion or '', cantidad=1,
                             precio_unitario=precio_final, costo_unitario=producto.precio_compra or 0,
                             fecha_venta=producto.fecha_venta))
        record_change(producto, 'Vender una unidad', before)
        db.session.commit()
        flash(f'Producto vendido exitosamente a Bs. {precio_final:.2f}.', 'success')
    except Exception as exc:
        db.session.rollback()
        flash(str(exc) if isinstance(exc, ValueError) else 'No se pudo registrar la venta. Recarga e intenta nuevamente.', 'danger')

    return redirect(url_for('admin.inventario', tab='venta'))


@admin.route('/poner-en-venta/<int:producto_id>', methods=['POST'])
@login_required
@admin_required
def poner_en_venta(producto_id):
    producto = db.get_or_404(ProductoVenta, producto_id)

    if producto.tipo != 'compra':
        flash('Este producto ya esta en venta.', 'info')
        return redirect(url_for('admin.inventario'))

    try:
        precio_venta = parse_positive_float(request.form.get('precio_venta'), 'precio de venta')
        producto.precio = precio_venta
        producto.estado = 'disponible'
        producto.tipo = 'venta'
        db.session.commit()
        flash(f'Producto puesto en venta a Bs. {precio_venta:.2f}.', 'success')
    except Exception as exc:
        db.session.rollback()
        flash(str(exc), 'danger')

    return redirect(url_for('admin.inventario'))


@admin.route('/eliminar-producto/<int:producto_id>', methods=['POST'])
@login_required
@admin_required
def eliminar_producto(producto_id):
    producto = db.get_or_404(ProductoVenta, producto_id)
    before = audit_snapshot(producto)
    if producto.ventas or producto.prestamo_origen_id:
        producto.estado = 'archivado'
        record_change(producto, 'Archivar producto', before)
        flash('Producto archivado. Se conserva su historial de ventas y origen.', 'success')
    else:
        record_change(producto, 'Eliminar producto', before)
        db.session.delete(producto)
        flash('Producto eliminado exitosamente.', 'success')
    db.session.commit()
    return redirect(url_for('admin.inventario'))
