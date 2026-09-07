import os
import re

files = [
    "app/models/prestamo.py",
    "app/models/producto.py",
    "app/routes/admin_config.py",
    "app/routes/admin_dashboard.py",
    "app/routes/admin_inventory.py",
    "app/routes/admin_loans.py",
    "app/routes/admin_reports.py",
    "app/routes/admin_shared.py"
]

base_dir = r"C:\Users\willy\Downloads\dist\dist\CasaEmpeno_rebuilt"

for file_rel in files:
    file_path = os.path.join(base_dir, file_rel)
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Replace datetime.now
    content = content.replace("datetime.now", "get_bolivia_time")

    # Check if 'datetime' is still used in code
    words = re.findall(r'\bdatetime\b', content)
    
    import_match = re.search(r'^from datetime import (.*)$', content, re.MULTILINE)
    
    if import_match:
        if words.count('datetime') == 1:
            import_stmt = import_match.group(0)
            imports = [x.strip() for x in import_match.group(1).split(',')]
            if 'datetime' in imports:
                imports.remove('datetime')
            if imports:
                new_import = f"from datetime import {', '.join(imports)}"
                content = content.replace(import_stmt, new_import)
            else:
                # Remove the whole line
                content = content.replace(import_stmt + '\n', '')
                content = content.replace(import_stmt, '')

    # Add import at the beginning
    if "from app.utils import get_bolivia_time" not in content:
        # Add it right after the first line (or at the top)
        lines = content.split('\n')
        insert_idx = 0
        for i, line in enumerate(lines):
            if line.startswith('import ') or line.startswith('from '):
                insert_idx = i + 1
        # It's better to just put it at line 1.
        lines.insert(0, "from app.utils import get_bolivia_time")
        content = '\n'.join(lines)

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"Processed {file_rel}")
