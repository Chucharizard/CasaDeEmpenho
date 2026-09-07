from flask import Blueprint, request, flash, redirect, url_for
from flask_login import login_required, current_user
from app import db
from app.utils import format_bolivian_phone

client = Blueprint('client', __name__, url_prefix='/cliente')


@client.route('/actualizar-perfil', methods=['POST'])
@login_required
def actualizar_perfil():
    telefono = format_bolivian_phone(request.form.get('telefono'))

    if not telefono:
        flash('El teléfono es obligatorio.', 'warning')
        return redirect(request.referrer or url_for('public.index'))

    current_user.telefono = telefono
    db.session.commit()
    flash('Perfil actualizado correctamente.', 'success')
    return redirect(request.referrer or url_for('public.index'))
