import os
import sys

os.chdir(r'C:\Users\willy\Downloads\dist\dist\CasaEmpeno_rebuilt')
sys.path.insert(0, r'C:\Users\willy\Downloads\dist\dist\CasaEmpeno_rebuilt')

from app import create_app, db
from config import Config

app = create_app()

with app.app_context():
    from sqlalchemy import inspect
    from app.models import Articulo, Prestamo, ProductoVenta, Usuario

    inspector = inspect(db.engine)
    tables = inspector.get_table_names()
    print('Tablas en la BD:', tables)
    print(f'Usuarios: {Usuario.query.count()}')
    print(f'Prestamos: {Prestamo.query.count()}')
    print(f'Articulos: {Articulo.query.count()}')
    print(f'Productos: {ProductoVenta.query.count()}')
    print(f'Prefijo admin: {Config.ADMIN_PREFIX}')
    print('App inicializada correctamente')
