"""
Servicio de WhatsApp para comunicarse con el bot local de Node.js (Baileys).
Expone funciones simples para enviar imágenes y textos vía WhatsApp
sin que el cajero tenga que hacer nada manualmente.
"""
import base64
import logging
import urllib.request
import urllib.error
import json
from flask import current_app, has_app_context
from config import Config

logger = logging.getLogger(__name__)

WHATSAPP_BOT_URL = 'http://127.0.0.1:3001'
REQUEST_TIMEOUT = 15  # segundos


def _hacer_peticion(endpoint, method='GET', data=None):
    """
    Realiza una petición HTTP al bot de WhatsApp local.
    Usa solo urllib para evitar dependencias externas (requests).
    """
    config = current_app.config if has_app_context() else Config.__dict__
    url = f"{config.get('WHATSAPP_BOT_URL', WHATSAPP_BOT_URL)}{endpoint}"
    headers = {'Content-Type': 'application/json', 'X-API-Key': config['WHATSAPP_API_TOKEN']}

    try:
        body = json.dumps(data).encode('utf-8') if data else None
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8', errors='replace')
        logger.warning(f'WhatsApp Bot HTTP {e.code}: {error_body}')
        try:
            return json.loads(error_body)
        except Exception:
            return {'success': False, 'error': f'HTTP {e.code}: {error_body}'}
    except urllib.error.URLError as e:
        logger.warning(f'WhatsApp Bot no disponible: {e.reason}')
        return {'success': False, 'error': f'Bot no disponible: {e.reason}'}
    except Exception as e:
        logger.error(f'Error al conectar con WhatsApp Bot: {e}')
        return {'success': False, 'error': str(e)}


def obtener_estado():
    """
    Consulta el estado de la conexión del bot.
    Retorna dict con: status (disconnected|qr_pending|connected), linkedNumber, hasQR
    """
    return _hacer_peticion('/status')


def esta_conectado():
    """Verifica si el bot está conectado y listo para enviar mensajes."""
    estado = obtener_estado()
    return estado.get('status') == 'connected'


def obtener_qr_data():
    """
    Obtiene el código QR como Data URI (base64) para incrustar en una imagen HTML.
    Retorna dict con: qr (data:image/png;base64,...), status
    """
    return _hacer_peticion('/qr-data')


def enviar_imagen(telefono, imagen_bytes, caption=None):
    """
    Envía una imagen PNG a un número de WhatsApp.

    Args:
        telefono: Número de teléfono (8 dígitos Bolivia o con código de país)
        imagen_bytes: bytes de la imagen PNG (contenido del buffer)
        caption: Texto opcional que acompaña la imagen

    Returns:
        dict con 'success' (bool) y 'message' o 'error'
    """
    if not telefono:
        return {'success': False, 'error': 'No se proporcionó número de teléfono.'}

    imagen_b64 = base64.b64encode(imagen_bytes).decode('ascii')

    data = {
        'phone': telefono,
        'imageBase64': imagen_b64,
    }
    if caption:
        data['caption'] = caption

    resultado = _hacer_peticion('/send-image', method='POST', data=data)
    if resultado.get('success'):
        logger.info(f'WhatsApp: Imagen enviada a {telefono}')
    else:
        logger.warning(f'WhatsApp: Fallo al enviar imagen a {telefono}: {resultado.get("error")}')

    return resultado


def enviar_texto(telefono, mensaje):
    """
    Envía un mensaje de texto a un número de WhatsApp.

    Args:
        telefono: Número de teléfono
        mensaje: Texto del mensaje

    Returns:
        dict con 'success' (bool) y 'message' o 'error'
    """
    if not telefono or not mensaje:
        return {'success': False, 'error': 'Teléfono y mensaje son requeridos.'}

    data = {
        'phone': telefono,
        'message': mensaje,
    }

    return _hacer_peticion('/send-text', method='POST', data=data)


def cerrar_sesion():
    """Cierra la sesión de WhatsApp (desvincula el QR)."""
    return _hacer_peticion('/logout', method='POST')


def reconectar():
    return _hacer_peticion('/reconnect', method='POST')
