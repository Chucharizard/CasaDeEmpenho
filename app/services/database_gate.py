"""Lectores concurrentes y mantenimiento exclusivo dentro de la instalación."""
from contextlib import contextmanager
from threading import Condition, RLock, get_ident


class DatabaseGate:
    def __init__(self):
        self._condition = Condition(RLock())
        self._readers = {}
        self._writer = None
        self._write_depth = 0
        self._waiting_writers = 0

    def acquire(self):
        identity = get_ident()
        with self._condition:
            while self._writer not in (None, identity) or (
                self._waiting_writers and identity not in self._readers and self._writer != identity
            ):
                self._condition.wait()
            self._readers[identity] = self._readers.get(identity, 0) + 1

    def release(self):
        identity = get_ident()
        with self._condition:
            depth = self._readers[identity] - 1
            if depth:
                self._readers[identity] = depth
            else:
                del self._readers[identity]
            self._condition.notify_all()

    def acquire_exclusive(self):
        identity = get_ident()
        with self._condition:
            if self._writer == identity:
                self._write_depth += 1
                return
            if identity in self._readers:
                raise RuntimeError('No se puede iniciar mantenimiento desde una operación de lectura activa.')
            self._waiting_writers += 1
            try:
                while self._writer is not None or self._readers:
                    self._condition.wait()
                self._writer = identity
                self._write_depth = 1
            finally:
                self._waiting_writers -= 1

    def release_exclusive(self):
        with self._condition:
            if self._writer != get_ident():
                raise RuntimeError('El mantenimiento pertenece a otra operación.')
            self._write_depth -= 1
            if not self._write_depth:
                self._writer = None
                self._condition.notify_all()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *error):
        self.release()

    @contextmanager
    def exclusive(self):
        self.acquire_exclusive()
        try:
            yield self
        finally:
            self.release_exclusive()
