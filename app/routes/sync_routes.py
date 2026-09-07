from flask import Blueprint, jsonify
from flask_login import login_required
from app.routes.admin_shared import admin_required

sync_bp = Blueprint('sync', __name__, url_prefix='/sync')

@sync_bp.route('/status', methods=['GET'])
@login_required
@admin_required
def sync_status():
    """
    Retorna el estado actual del servicio de sincronización.
    """
    return jsonify({
        'status': 'offline',
        'message': 'Modulo de sincronizacion local activo. Pendiente configuracion del servidor central.',
        'pending_sync_count': 0
    })
