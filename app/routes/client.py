from flask import Blueprint, abort, current_app, render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user
from app import db
from app.utils import format_bolivian_phone, local_redirect_target

client = Blueprint('client', __name__, url_prefix='/cliente')


@client.route('/panel')
@login_required
def panel():
    if not current_app.config['CLIENT_ACCESS_ENABLED']:
        abort(404)
    return render_template('client/panel.html', prestamos=[p for p in current_user.prestamos if p.estado in {'activo', 'retencion'}])


@client.route('/actualizar-perfil', methods=['POST'])
@login_required
def actualizar_perfil():
    telefono = format_bolivian_phone(request.form.get('telefono'))

    if not telefono:
        flash('El teléfono es obligatorio.', 'warning')
        return redirect(local_redirect_target(request.referrer, url_for('public.index'), origin=request.host_url))

    current_user.telefono = telefono
    db.session.commit()
    flash('Perfil actualizado correctamente.', 'success')
    return redirect(url_for('client.panel') if current_app.config['CLIENT_ACCESS_ENABLED'] and not current_user.es_admin else url_for('admin.dashboard'))
