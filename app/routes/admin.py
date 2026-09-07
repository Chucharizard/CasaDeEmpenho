from app.routes.admin_shared import admin

from app.routes import admin_config  # noqa: F401
from app.routes import admin_dashboard  # noqa: F401
from app.routes import admin_inventory  # noqa: F401
from app.routes import admin_loans  # noqa: F401
from app.routes import admin_reports  # noqa: F401

__all__ = ['admin']
