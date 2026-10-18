"""Las rutas portátiles dependen de la instalación, no de la carpeta del acceso directo."""
import json
from pathlib import Path
import os
import subprocess
import sys


def test_config_portatil_resuelve_rutas_junto_al_ejecutable(tmp_path):
    executable = tmp_path / 'Instalación Panda' / 'CasaEmpeno.exe'
    executable.parent.mkdir()
    other_cwd = tmp_path / 'Otra carpeta'
    other_cwd.mkdir()
    root = Path(__file__).resolve().parents[1]
    environment = dict(os.environ, CASAEMPENO_DATA_DIR='Datos', BACKUP_DIR='Respaldos',
                       SECRET_KEY='ficticia', ADMIN_URL_KEY='ficticia', WHATSAPP_API_TOKEN='ficticia',
                       PYTHONPATH=str(root))
    code = '''
import sys, json
sys.frozen = True
sys.executable = sys.argv[1]
from config import Config
print(json.dumps([Config.DATA_DIR, Config.BACKUP_DIR]))
'''
    output = subprocess.check_output([sys.executable, '-c', code, str(executable)],
                                     cwd=other_cwd, env=environment, text=True)
    data, backup = json.loads(output)
    assert Path(data) == executable.parent / 'Datos'
    assert Path(backup) == executable.parent / 'Respaldos'
    assert not (other_cwd / 'Datos').exists()
