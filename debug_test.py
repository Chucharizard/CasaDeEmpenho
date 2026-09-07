import os
import sys
import traceback

os.chdir(r'C:\Users\willy\Downloads\dist\dist\CasaEmpeno_rebuilt')
sys.path.insert(0, r'C:\Users\willy\Downloads\dist\dist\CasaEmpeno_rebuilt')

from app import create_app
from config import Config

app = create_app()
app.config['DEBUG'] = True
app.config['PROPAGATE_EXCEPTIONS'] = True

with app.test_client() as client:
    with app.app_context():
        from app.models import Usuario

        admin = Usuario.query.filter_by(es_admin=True).first()
        print('Admin:', admin.nombre if admin else 'No encontrado')

        with client.session_transaction() as session:
            session['_user_id'] = str(admin.id)
            session['_fresh'] = True

        rutas = [
            f'{Config.ADMIN_PREFIX}/dashboard',
            f'{Config.ADMIN_PREFIX}/clientes',
            f'{Config.ADMIN_PREFIX}/inventario',
            f'{Config.ADMIN_PREFIX}/prestamos-personales',
            f'{Config.ADMIN_PREFIX}/configuracion',
        ]

        for ruta in rutas:
            try:
                response = client.get(ruta)
                print(f'{ruta}: {response.status_code}')
                if response.status_code == 500:
                    data = response.data.decode('utf-8', errors='replace')
                    if 'Traceback' in data:
                        idx = data.find('Traceback')
                        print(data[idx:idx + 800])
                    else:
                        print(data[:600])
            except Exception:
                print(f'ERROR en {ruta}:')
                traceback.print_exc()
