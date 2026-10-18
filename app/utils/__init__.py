import re
from datetime import datetime
from zoneinfo import ZoneInfo


def normalize_ci(value):
    return str(value or '').strip().upper()


def local_redirect_target(value, default, origin=None):
    from urllib.parse import urlsplit
    if not value or '\\' in value or any(ord(character) < 32 or ord(character) == 127 for character in value):
        return default
    try:
        parsed = urlsplit(value)
        if origin and parsed.scheme and parsed.netloc:
            expected = urlsplit(origin)
            if (parsed.scheme, parsed.netloc) == (expected.scheme, expected.netloc):
                value = (parsed.path or '/') + (f'?{parsed.query}' if parsed.query else '')
                parsed = urlsplit(value)
    except ValueError:
        return default
    if value.startswith('/') and not value.startswith('//') and not parsed.netloc and not parsed.scheme:
        return value
    return default

def get_bolivia_time():
    """
    Retorna la fecha y hora actual en la zona horaria de Bolivia 
    como un datetime naive (sin tzinfo) para compatibilidad con la BD SQLite.
    """
    return datetime.now(ZoneInfo('America/La_Paz')).replace(tzinfo=None)

def format_bolivian_phone(phone_str):
    """
    Limpia y formatea un número de teléfono al estándar de Bolivia para WhatsApp (+591...).
    Retorna el número formateado si es válido, o el string original modificado si no lo es.
    """
    if not phone_str:
        return None
    
    # Remover todo excepto dígitos y el signo +
    cleaned = re.sub(r'[^\d+]', '', str(phone_str))
    
    # Si ya tiene +591 y 8 dígitos después, asumimos que está bien
    if re.match(r'^\+591[67]\d{7}$', cleaned):
        return cleaned
        
    # Si empieza con 591 y le siguen 8 dígitos, agregar +
    if re.match(r'^591[67]\d{7}$', cleaned):
        return f"+{cleaned}"
        
    # Si solo son 8 dígitos y empieza con 6 o 7, agregar +591
    if re.match(r'^[67]\d{7}$', cleaned):
        return f"+591{cleaned}"
        
    # En cualquier otro caso (fijos, errores), devolver lo que quede
    return cleaned if cleaned else None
