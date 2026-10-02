"""
Casa de Empeno - Launcher
Punto de entrada del sistema: arranca Flask y abre el navegador.
"""
import os
import socket
import sys
import threading
import time
import traceback
import webbrowser
from config import Config


def pause_if_interactive(message='\nPresiona Enter para salir...'):
    """Pausa solo si existe una consola interactiva disponible."""
    try:
        if sys.stdin and sys.stdin.isatty():
            input(message)
    except Exception:
        pass


def get_base_path():
    """Obtiene el path base, funciona tanto en desarrollo como en ejecutable."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.abspath(os.path.dirname(__file__))


def ensure_output_streams():
    """En modo ventana (sin consola) PyInstaller deja sys.stdout/stderr en None
    y cualquier print() o logging crashea la app. Redirigimos a un archivo de log
    junto al ejecutable para no perder los mensajes ni romper el arranque."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    try:
        log_path = os.path.join(get_base_path(), 'casa_empeno.log')
        log_file = open(log_path, 'a', encoding='utf-8', buffering=1)
    except Exception:
        log_file = open(os.devnull, 'w', encoding='utf-8')
    if sys.stdout is None:
        sys.stdout = log_file
    if sys.stderr is None:
        sys.stderr = log_file


def is_port_in_use(port):
    """Verifica si un puerto esta en uso."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex(('localhost', port)) == 0


def get_browser_host():
    if Config.APP_HOST in {'0.0.0.0', '::'}:
        return '127.0.0.1'
    return Config.APP_HOST


def open_browser(port):
    """Abre el navegador despues de un pequeno delay."""
    time.sleep(1.5)
    url = f'http://{get_browser_host()}:{port}'
    print(f'\nAbriendo navegador en {url}')
    webbrowser.open(url)


def main():
    ensure_output_streams()
    base_path = get_base_path()
    os.chdir(base_path)
    sys.path.insert(0, base_path)

    host = Config.APP_HOST
    port = Config.APP_PORT
    browser_url = f'http://{get_browser_host()}:{port}'

    print('=' * 50)
    print('   CASA DE EMPENO - Sistema de Gestion')
    print('=' * 50)
    print(f'\nDirectorio: {base_path}')

    if is_port_in_use(port):
        print(f'\nEl puerto {port} ya esta en uso.')
        print(f'Ya hay una instancia corriendo en {browser_url}')
        webbrowser.open(browser_url)
        pause_if_interactive('\nPresiona Enter para salir...')
        return

    from app import create_app, db

    app = create_app()

    with app.app_context():
        try:
            os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
            print(f'\nDirectorio uploads: {Config.UPLOAD_FOLDER}')
        except OSError:
            pass
        try:
            os.makedirs(Config.BACKUP_DIR, exist_ok=True)
            print(f'Directorio respaldos: {Config.BACKUP_DIR}')
        except OSError:
            pass
        db.create_all()
        print('Base de datos inicializada')

    print(f'\nServidor iniciando en {browser_url}')
    print(f'Host de escucha: {host}')
    print('Presiona Ctrl+C para detener el servidor\n')
    print('-' * 50)

    # Iniciar bot de WhatsApp en segundo plano si está disponible
    try:
        if not is_port_in_use(3001):
            bot_dir = os.path.join(base_path, 'whatsapp-bot')
            server_js = os.path.join(bot_dir, 'server.js')
            if os.path.exists(server_js):
                import subprocess
                subprocess.Popen(['node', 'server.js'], cwd=bot_dir, shell=True)
                print('🤖 Bot de WhatsApp iniciado en segundo plano (puerto 3001)')
    except Exception as e:
        print(f'Nota: No se pudo auto-iniciar WhatsApp Bot: {e}')

    browser_thread = threading.Thread(target=open_browser, args=(port,))
    browser_thread.daemon = True
    browser_thread.start()

    try:
        app.run(host=host, port=port, debug=False, use_reloader=False)
    except Exception as exc:
        print(f'\nError al iniciar: {exc}')
        traceback.print_exc()
        pause_if_interactive('\nPresiona Enter para salir...')


if __name__ == '__main__':
    main()
