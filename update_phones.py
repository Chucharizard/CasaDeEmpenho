import sys
sys.path.insert(0, '.')
from app import create_app, db
from app.models import Usuario
from app.utils import format_bolivian_phone

app = create_app()
with app.app_context():
    users = Usuario.query.all()
    updated = 0
    for u in users:
        if u.telefono:
            new_phone = format_bolivian_phone(u.telefono)
            if new_phone != u.telefono:
                u.telefono = new_phone
                updated += 1
    
    db.session.commit()
    print(f'Updated {updated} phone numbers.')
