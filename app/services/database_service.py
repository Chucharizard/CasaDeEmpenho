"""Respaldo y restauración mediante SQLite, con migraciones versionadas."""
import os
import sqlite3
import tempfile
import time
from contextlib import closing
from functools import wraps
from pathlib import Path

from flask import current_app
from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy import inspect, text

from app import db
from app.utils import get_bolivia_time


LEGACY_REVISION = 'f8a9b0c1d2e3'
CURRENT_REVISION = 'ce_20261017_01'
BASE_TABLES = {'usuario', 'prestamo', 'articulo', 'pago', 'producto_venta', 'configuracion'}


def migration_config():
    directory = Path(current_app.root_path).parent / 'migrations'
    config = AlembicConfig(str(directory / 'alembic.ini'))
    config.set_main_option('script_location', str(directory))
    return config


def database_path():
    if db.engine.dialect.name != 'sqlite' or db.engine.url.database in (None, '', ':memory:'):
        raise ValueError('Esta operación requiere una base SQLite en archivo.')
    return Path(db.engine.url.database).resolve()


def backup_connection(source, destination):
    deadline = time.monotonic() + 30
    def progress(status, remaining, total):
        if time.monotonic() > deadline:
            raise TimeoutError('La base sigue ocupada. Intenta nuevamente en unos segundos.')
    with closing(sqlite3.connect(str(destination), timeout=5)) as target:
        source.backup(target, pages=256, progress=progress, sleep=0.05)


def create_backup(prefix='backup'):
    root = Path(current_app.config['BACKUP_DIR'])
    root.mkdir(parents=True, exist_ok=True)
    name = f"{prefix}_{get_bolivia_time():%Y-%m-%d_%H-%M-%S_%f}.db"
    target = root / name
    db.session.remove()
    with tempfile.NamedTemporaryFile(dir=root, suffix='.pending', delete=False) as temporary:
        staging = Path(temporary.name)
    try:
        with closing(db.engine.raw_connection()) as raw:
            backup_connection(raw.driver_connection, staging)
        validate_database(staging)
        staging.replace(target)
    finally:
        staging.unlink(missing_ok=True)
    return target


def validate_database(path):
    uri = Path(path).resolve().as_uri() + '?mode=ro'
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        if connection.execute('PRAGMA quick_check').fetchall() != [('ok',)]:
            raise ValueError('El respaldo no superó la verificación de integridad.')
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not BASE_TABLES.issubset(tables):
            raise ValueError('El archivo no contiene una base de Casa de Empeño compatible.')
        required = {
            'usuario': {'id', 'ci', 'nombre', 'password', 'cuenta_activa', 'es_admin', 'telefono', 'email'},
            'prestamo': {'id', 'usuario_id', 'numero_prestamo', 'numero_documento', 'monto_prestado', 'fecha_inicio', 'fecha_finalizacion', 'interes_mensual', 'estado', 'tipo_prestamo', 'ultimo_pago', 'tipo_ultimo_pago', 'monto_ultimo_pago'},
            'pago': {'id', 'prestamo_id', 'fecha_pago', 'tipo_pago', 'monto_pagado'},
            'articulo': {'id', 'prestamo_id', 'nombre', 'descripcion', 'fotos', 'estado'},
            'producto_venta': {'id', 'nombre', 'descripcion', 'precio', 'precio_compra', 'stock', 'stock_inicial', 'estado', 'tipo', 'fecha_venta', 'fecha_publicacion', 'fotos', 'destacado', 'proveedor'},
            'configuracion': {'id', 'clave', 'valor'},
        }
        for table, columns in required.items():
            present = {row[1] for row in connection.execute(f'PRAGMA table_info({table})')}
            if not columns.issubset(present):
                raise ValueError(f'El esquema de {table} no es compatible.')
        if connection.execute('PRAGMA foreign_key_check').fetchone():
            raise ValueError('El respaldo contiene referencias rotas.')
        versions = set()
        if 'alembic_version' in tables:
            versions = {row[0] for row in connection.execute('SELECT version_num FROM alembic_version')}
            if not versions.issubset({LEGACY_REVISION, CURRENT_REVISION}):
                raise ValueError('El respaldo pertenece a una versión de esquema no compatible.')
        if CURRENT_REVISION in versions:
            for table in db.metadata.sorted_tables:
                present = {row[1] for row in connection.execute(f'PRAGMA table_info({table.name})')}
                if not {column.name for column in table.columns}.issubset(present):
                    raise ValueError(f'El respaldo no contiene el esquema completo de {table.name}.')


def initialize_database(make_backup=True):
    tables = set(inspect(db.engine).get_table_names())
    if not tables:
        db.create_all()
        command.stamp(migration_config(), CURRENT_REVISION)
        return
    if not BASE_TABLES.issubset(tables):
        raise ValueError('Base existente incompleta: no se modificó el esquema.')
    version = db.session.execute(text('SELECT version_num FROM alembic_version')).scalar() if 'alembic_version' in tables else None
    db.session.remove()
    if version not in (None, LEGACY_REVISION, CURRENT_REVISION):
        raise ValueError('Versión de base de datos desconocida. No se modificaron datos.')
    if version is None:
        inspector = inspect(db.engine)
        complete = all(table.name in tables and {column.name for column in table.columns}.issubset(
            {column['name'] for column in inspector.get_columns(table.name)}) for table in db.metadata.sorted_tables)
        if complete:
            command.stamp(migration_config(), CURRENT_REVISION)
            version = CURRENT_REVISION
    if version != CURRENT_REVISION:
        validate_database(database_path())
        if make_backup:
            create_backup('pre_migracion')
        if version is None:
            command.stamp(migration_config(), LEGACY_REVISION)
        command.upgrade(migration_config(), CURRENT_REVISION)
    from app.models import Pago
    from app.services.receipt_service import capture_receipt
    from sqlalchemy.orm import selectinload
    from app.models import Prestamo
    pendientes = Pago.query.filter(Pago.comprobante_json.is_(None)).options(
        selectinload(Pago.prestamo).selectinload(Prestamo.articulos),
        selectinload(Pago.prestamo).selectinload(Prestamo.usuario),
    ).all()
    for pago in pendientes:
        capture_receipt(pago, pago.prestamo, legacy=True)
    if pendientes:
        db.session.commit()


def exclusive_maintenance(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        with current_app.extensions['database_lock'].exclusive():
            return function(*args, **kwargs)
    return wrapped


@exclusive_maintenance
def restore_backup(path):
    validate_database(path)
    destination = database_path()
    if Path(path).resolve() == destination:
        raise ValueError('No se puede restaurar la base sobre sí misma.')
    # Preparar y migrar una copia antes de tocar la base activa.
    from app import create_app
    with tempfile.TemporaryDirectory(prefix='casaempeno_restore_') as temporary:
        staged = Path(temporary) / 'restaurar.db'
        with closing(sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)) as source:
            backup_connection(source, staged)
        stage_app = create_app({
            'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite:///' + str(staged),
            'BACKUP_DIR': temporary, 'UPLOAD_FOLDER': os.path.join(temporary, 'uploads'),
        })
        with stage_app.app_context():
            try:
                initialize_database(make_backup=False)
            finally:
                db.session.remove()
                db.engine.dispose()
        validate_database(staged)
        previous = create_backup('pre_restore')
        db.session.remove()
        db.engine.dispose()
        with closing(sqlite3.connect(staged)) as source, closing(sqlite3.connect(destination, timeout=5)) as target:
            deadline = time.monotonic() + 30
            def progress(status, remaining, total):
                if time.monotonic() > deadline:
                    raise TimeoutError('La base está ocupada por otra instancia.')
            source.backup(target, pages=256, progress=progress, sleep=0.05)
        db.engine.dispose()
        return previous
