import re
from datetime import datetime
from zoneinfo import ZoneInfo

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
