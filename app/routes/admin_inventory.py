from app.utils import get_bolivia_time

from flask import flash, redirect, render_template, request, url_for
from flask_login import login_required

from app import db
from app.models import Articulo, Prestamo, ProductoVenta
from app.routes.admin_shared import admin, admin_required, clean_text, parse_non_negative_int, parse_positive_float


@admin.route('/inventario')
@login_required
@admin_required
def inventario():
    tab = request.args.get('tab', 'venta')

    if tab == 'compra':
        productos = ProductoVenta.query.filter_by(tipo='compra').all()
    elif tab == 'vendidos':
        productos = ProductoVenta.query.filter_by(estado='vendido').all()
    else:
        productos = ProductoVenta.query.filter_by(estado='disponible').all()

    total_invertido = db.session.query(
        db.func.sum(ProductoVenta.precio_compra * ProductoVenta.stock)
    ).filter(
        ProductoVenta.estado.in_(['compra', 'disponible']),
        ProductoVenta.precio_compra.isnot(None),
    ).scalar() or 0

    ventas = ProductoVenta.query.filter_by(estado='vendido').all()
    for venta in ventas:
        venta.ganancia = (venta.precio or 0) - (venta.precio_compra or 0)

    total_vendido = sum(venta.precio for venta in ventas)
    total_costo = sum(venta.precio_compra or 0 for venta in ventas)
    ganancia_total = total_vendido - total_costo
    articulos_stock = Articulo.query.join(Prestamo).filter(Prestamo.estado == 'retencion').all()

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
    )


@admin.route('/nuevo-producto', methods=['GET', 'POST'])
@login_required
@admin_required
def nuevo_producto():
    if request.method == 'POST':
        try:
            tipo = clean_text(request.form.get('tipo') or 'venta')
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
    producto = ProductoVenta.query.get_or_404(producto_id)
    if request.method == 'POST':
        try:
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
    producto = ProductoVenta.query.get_or_404(producto_id)

    try:
        precio_final = parse_positive_float(request.form.get('precio_final', producto.precio), 'precio final')
        if not producto.stock or producto.stock <= 0:
            raise ValueError('No hay stock disponible.')

        producto.stock -= 1
        if producto.stock == 0:
            producto.estado = 'vendido'
        producto.precio = precio_final
        producto.fecha_venta = get_bolivia_time()
        db.session.commit()
        flash(f'Producto vendido exitosamente a Bs. {precio_final:.2f}.', 'success')
    except Exception as exc:
        db.session.rollback()
        flash(str(exc), 'danger')

    return redirect(url_for('admin.inventario', tab='venta'))


@admin.route('/poner-en-venta/<int:producto_id>', methods=['POST'])
@login_required
@admin_required
def poner_en_venta(producto_id):
    producto = ProductoVenta.query.get_or_404(producto_id)

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
    producto = ProductoVenta.query.get_or_404(producto_id)
    db.session.delete(producto)
    db.session.commit()
    flash('Producto eliminado exitosamente.', 'success')
    return redirect(url_for('admin.inventario'))
