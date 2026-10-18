"""Arranque local y apagado autenticado del bot, conservando su sesión."""
import logging
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time

from flask import current_app

from app.services import whatsapp_service

logger = logging.getLogger(__name__)


def _port_open():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
        connection.settimeout(.5)
        return connection.connect_ex(('127.0.0.1', 3001)) == 0


def start_bot():
    if not whatsapp_service.esta_habilitado():
        return whatsapp_service.deshabilitado()
    if current_app.testing:
        return {'success': True, 'message': 'Arranque simulado en pruebas.'}
    process = current_app.extensions.get('whatsapp_process')
    if process is not None and process.poll() is None and not _port_open():
        return {'success': True, 'message': 'El bot está iniciándose.'}
    if _port_open():
        state = whatsapp_service.obtener_estado()
        if state.get('status') in {'connected', 'connecting', 'qr_pending'}:
            return {'success': True, 'message': 'El bot ya está iniciado.'}
        if state.get('status') == 'disconnected':
            return whatsapp_service.reconectar()
        return {'success': False, 'error': 'El puerto del bot está ocupado por otro servicio o instalación.'}
    directory = Path(current_app.config['BASEDIR']) / 'whatsapp-bot'
    server = directory / 'server.js'
    node = directory / 'node.exe'
    executable = str(node) if node.is_file() else shutil.which('node')
    if not server.is_file() or not executable:
        return {'success': False, 'error': 'No se encontraron los archivos necesarios para iniciar el bot.'}
    environment = os.environ.copy()
    environment['WHATSAPP_API_TOKEN'] = current_app.config['WHATSAPP_API_TOKEN']
    # La misma ruta absoluta sirve a Python y Node, incluso si .env usa una ruta relativa.
    if os.environ.get('CASAEMPENO_DATA_DIR'):
        environment['CASAEMPENO_DATA_DIR'] = current_app.config['DATA_DIR']
    try:
        log_directory = Path(current_app.config['DATA_DIR'])
        log_directory.mkdir(parents=True, exist_ok=True)
        with (log_directory / 'whatsapp-bot.log').open('a', encoding='utf-8') as log:
            process = subprocess.Popen(
                [executable, str(server)], cwd=str(directory), env=environment,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                stdout=log, stderr=subprocess.STDOUT,
            )
        current_app.extensions['whatsapp_process'] = process
        return {'success': True, 'message': 'Bot iniciado. La conexión puede tardar unos segundos.'}
    except OSError:
        logger.exception('No se pudo iniciar el bot local')
        return {'success': False, 'error': 'No se pudo iniciar el bot. Revisa su registro o vuelve a intentarlo.'}


def stop_bot():
    if current_app.testing:
        return {'success': True, 'message': 'El bot está apagado.'}
    if not _port_open():
        # Un arranque recién solicitado puede seguir cargando antes de escuchar.
        # Solo se termina el proceso creado por esta aplicación, nunca un PID ajeno.
        process = current_app.extensions.get('whatsapp_process')
        if process is not None and process.poll() is None:
            try:
                process.terminate()
                try:
                    process.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
            except (OSError, subprocess.SubprocessError):
                logger.exception('No se pudo terminar el arranque del bot')
                return {'success': False, 'error': 'Los envíos están bloqueados, pero no se pudo terminar el proceso del bot.'}
        current_app.extensions.pop('whatsapp_process', None)
        return {'success': True, 'message': 'El bot está apagado.'}
    result = whatsapp_service._hacer_peticion('/shutdown', method='POST')
    if not result.get('success'):
        return result
    deadline = time.monotonic() + 4
    while _port_open() and time.monotonic() < deadline:
        time.sleep(.05)
    if _port_open():
        return {'success': False, 'error': 'Los envíos están bloqueados, pero el bot aún no terminó de apagarse.'}
    current_app.extensions.pop('whatsapp_process', None)
    return {'success': True, 'message': 'Bot apagado; la sesión vinculada se conserva.'}
