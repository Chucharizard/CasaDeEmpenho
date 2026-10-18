import os
import secrets
import sys
from dotenv import load_dotenv

IS_FROZEN = getattr(sys, 'frozen', False)

if IS_FROZEN:
    BASEDIR = os.path.dirname(sys.executable)
else:
    BASEDIR = os.path.abspath(os.path.dirname(__file__))

load_dotenv(os.path.join(BASEDIR, '.env'))
DATA_DIR = os.path.abspath(os.path.join(BASEDIR, os.getenv('CASAEMPENO_DATA_DIR') or '.'))


def _load_or_create_secret(filename, env_name, token_bytes=32):
    """Use env var when present, otherwise persist a local secret for this install."""
    env_value = (os.getenv(env_name) or '').strip()
    if env_value:
        return env_value

    secret_path = os.path.join(DATA_DIR, filename)

    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        if os.path.exists(secret_path):
            with open(secret_path, 'r', encoding='utf-8') as secret_file:
                value = secret_file.read().strip()
            if value:
                return value

        value = secrets.token_urlsafe(token_bytes)
        with open(secret_path, 'w', encoding='utf-8') as secret_file:
            secret_file.write(value)
        return value
    except OSError:
        return secrets.token_urlsafe(token_bytes)


class Config:
    IS_FROZEN = IS_FROZEN
    BASEDIR = BASEDIR
    DATA_DIR = DATA_DIR
    SECRET_KEY = _load_or_create_secret('.secret_key', 'SECRET_KEY')

    # Base de datos
    DB_NAME = os.getenv('DB_NAME', 'casa_empeno.db')
    SQLITE_DB_PATH = os.path.join(DATA_DIR, DB_NAME)
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + SQLITE_DB_PATH
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Uploads
    UPLOAD_FOLDER = os.path.join(DATA_DIR, 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    TEMPLATES_AUTO_RELOAD = True

    # Backups
    USER_HOME = os.path.expanduser('~')
    ONEDRIVE_DIR = os.path.join(USER_HOME, 'OneDrive')
    if os.path.isdir(ONEDRIVE_DIR):
        BACKUP_DIR = os.path.join(ONEDRIVE_DIR, 'Respaldo')
    else:
        BACKUP_DIR = os.path.join(USER_HOME, 'RespaldoCasaEmpeno')
    BACKUP_DIR = os.path.abspath(os.path.join(BASEDIR, os.getenv('BACKUP_DIR'))) if os.getenv('BACKUP_DIR') else BACKUP_DIR

    # Admin y arranque local
    ADMIN_URL_KEY = _load_or_create_secret('.admin_url_key', 'ADMIN_URL_KEY', token_bytes=18)
    ADMIN_PREFIX = (os.getenv('ADMIN_PREFIX') or '/admin').strip() or '/admin'
    if not ADMIN_PREFIX.startswith('/'):
        ADMIN_PREFIX = f'/{ADMIN_PREFIX}'

    APP_HOST = (os.getenv('APP_HOST') or '127.0.0.1').strip() or '127.0.0.1'
    APP_PORT = int(os.getenv('APP_PORT', '5000'))

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = 'Lax'

    ENABLE_DEV_LOGIN = os.getenv('ENABLE_DEV_LOGIN', '0').strip().lower() in ('1', 'true', 'yes')
    CSRF_ENABLED = True
    CLIENT_ACCESS_ENABLED = os.getenv('CLIENT_ACCESS_ENABLED', '0').lower() in ('1', 'true', 'yes')
    WHATSAPP_BOT_URL = 'http://127.0.0.1:3001'
    WHATSAPP_API_TOKEN = _load_or_create_secret('.whatsapp_api_token', 'WHATSAPP_API_TOKEN')

    @classmethod
    def init_app(cls, app):
        pass
