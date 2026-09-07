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

    import_match = re.search(r'^from datetime import (.*)$', content, re.MULTILINE)
    
    if import_match:
        import_stmt = import_match.group(0)
        # Check if 'datetime' is used elsewhere
        content_without_import = content.replace(import_stmt, '')
        
        # We only want to remove 'datetime' from the import if 'datetime' doesn't appear in the rest of the file
        # Check if '\bdatetime\b' appears in content_without_import
        if not re.search(r'\bdatetime\b', content_without_import):
            # Safe to remove 'datetime' from imports
            imports = [x.strip() for x in import_match.group(1).split(',')]
            if 'datetime' in imports:
                imports.remove('datetime')
            if imports:
                new_import = f"from datetime import {', '.join(imports)}"
                content = content.replace(import_stmt, new_import)
            else:
                # Remove the whole line
                # It might have a trailing newline
                content = content.replace(import_stmt + '\n', '')
                content = content.replace(import_stmt, '')

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"Processed imports for {file_rel}")
