THEMES = {
    'default': {
        'name': 'Esmeralda (Default)',
        'is_dark': False,
        'variables': {
            '--primario': '#10b981',
            '--primario-hover': '#059669',
            '--bg-sidebar': '#0f172a',
            '--bg-sidebar-hover': '#1e293b',
            '--bg-corporativo': '#f8fafc',
            '--color-texto-principal': '#0f172a',
            '--color-texto-secundario': '#475569',
            '--color-texto-sidebar': '#f8fafc',
            '--color-texto-secundario-sidebar': '#94a3b8',
            '--borde': '#e2e8f0',
            '--bg-tarjeta': '#ffffff'
        }
    },
    'dark': {
        'name': 'Noche Oscura',
        'is_dark': True,
        'variables': {
            '--primario': '#3b82f6',
            '--primario-hover': '#2563eb',
            '--bg-sidebar': '#090d16',
            '--bg-sidebar-hover': '#141d30',
            '--bg-corporativo': '#0b1120',
            '--color-texto-principal': '#f8fafc',
            '--color-texto-secundario': '#94a3b8',
            '--color-texto-sidebar': '#ffffff',
            '--color-texto-secundario-sidebar': '#64748b',
            '--borde': '#1e293b',
            '--bg-tarjeta': '#11192e'
        }
    },
    'purple': {
        'name': 'Amatista (Oscuro)',
        'is_dark': True,
        'variables': {
            '--primario': '#a855f7',
            '--primario-hover': '#9333ea',
            '--bg-sidebar': '#140b24',
            '--bg-sidebar-hover': '#24143f',
            '--bg-corporativo': '#0d0718',
            '--color-texto-principal': '#f5f3ff',
            '--color-texto-secundario': '#c4b5fd',
            '--color-texto-sidebar': '#ffffff',
            '--color-texto-secundario-sidebar': '#a78bfa',
            '--borde': '#2d184d',
            '--bg-tarjeta': '#190e2e'
        }
    },
    'midnight': {
        'name': 'Medianoche (Oscuro)',
        'is_dark': True,
        'variables': {
            '--primario': '#6366f1',
            '--primario-hover': '#4f46e5',
            '--bg-sidebar': '#090d20',
            '--bg-sidebar-hover': '#141b3a',
            '--bg-corporativo': '#070b18',
            '--color-texto-principal': '#f1f5f9',
            '--color-texto-secundario': '#94a3b8',
            '--color-texto-sidebar': '#ffffff',
            '--color-texto-secundario-sidebar': '#818cf8',
            '--borde': '#1c2548',
            '--bg-tarjeta': '#0f1733'
        }
    },
    'cyber': {
        'name': 'Neón Cian (Oscuro)',
        'is_dark': True,
        'variables': {
            '--primario': '#06b6d4',
            '--primario-hover': '#0891b2',
            '--bg-sidebar': '#031217',
            '--bg-sidebar-hover': '#06262e',
            '--bg-corporativo': '#020d12',
            '--color-texto-principal': '#ecfeff',
            '--color-texto-secundario': '#7dd3fc',
            '--color-texto-sidebar': '#ffffff',
            '--color-texto-secundario-sidebar': '#22d3ee',
            '--borde': '#0c3540',
            '--bg-tarjeta': '#071d24'
        }
    },
    'forest': {
        'name': 'Bosque',
        'is_dark': False,
        'variables': {
            '--primario': '#16a34a',
            '--primario-hover': '#15803d',
            '--bg-sidebar': '#0f291e',
            '--bg-sidebar-hover': '#164332',
            '--bg-corporativo': '#f4fbf7',
            '--color-texto-principal': '#0f291e',
            '--color-texto-secundario': '#166534',
            '--color-texto-sidebar': '#f0fdf4',
            '--color-texto-secundario-sidebar': '#a7f3d0',
            '--borde': '#d1fae5',
            '--bg-tarjeta': '#ffffff'
        }
    },
    'ocean': {
        'name': 'Océano',
        'is_dark': False,
        'variables': {
            '--primario': '#0284c7',
            '--primario-hover': '#0369a1',
            '--bg-sidebar': '#072b42',
            '--bg-sidebar-hover': '#0b3d5d',
            '--bg-corporativo': '#f0f9ff',
            '--color-texto-principal': '#0c4a6e',
            '--color-texto-secundario': '#0369a1',
            '--color-texto-sidebar': '#f0f9ff',
            '--color-texto-secundario-sidebar': '#7dd3fc',
            '--borde': '#e0f2fe',
            '--bg-tarjeta': '#ffffff'
        }
    },
    'corporate': {
        'name': 'Corporativo',
        'is_dark': False,
        'variables': {
            '--primario': '#334155',
            '--primario-hover': '#1e293b',
            '--bg-sidebar': '#0f172a',
            '--bg-sidebar-hover': '#1e293b',
            '--bg-corporativo': '#f8fafc',
            '--color-texto-principal': '#0f172a',
            '--color-texto-secundario': '#475569',
            '--color-texto-sidebar': '#f8fafc',
            '--color-texto-secundario-sidebar': '#94a3b8',
            '--borde': '#e2e8f0',
            '--bg-tarjeta': '#ffffff'
        }
    }
}

# El color y la forma se eligen por separado para poder combinarlos.
DESIGN_STYLES = {
    'brutalist': {'name': 'Brutalista', 'description': 'Bordes firmes, bloques de color y sombras sólidas.', 'icon': 'bi-square-half'},
    'handdrawn': {'name': 'Dibujado', 'description': 'Papel, trazos orgánicos y detalles de cuaderno.', 'icon': 'bi-pencil'},
    'flat': {'name': 'Flat clásico', 'description': 'Superficies limpias y detalles discretos.', 'icon': 'bi-grid'},
}

# Un oscuro neutro con acentos cálidos y menos saturación.
THEMES['graphite'] = {
    'name': 'Grafito y salvia (Oscuro)',
    'is_dark': True,
    'variables': {
        '--primario': '#adc6b0',
        '--primario-hover': '#bfd3c1',
        '--secundario': '#d1b48c',
        '--bg-sidebar': '#191e1b',
        '--bg-sidebar-hover': '#303b33',
        '--bg-corporativo': '#151918',
        '--bg-tarjeta': '#202624',
        '--color-texto-principal': '#edf1e9',
        '--color-texto-secundario': '#b1bcb3',
        '--color-texto-sidebar': '#edf1e9',
        '--color-texto-secundario-sidebar': '#b1bcb3',
        '--borde': '#48534a',
    },
}

for key, name, primary, secondary, background in [
    ('citrus', 'Lima editorial', '#d5f365', '#7856d8', '#f6f5ee'),
    ('coral', 'Coral y tinta', '#ff927e', '#336cdb', '#fff6ef'),
    ('lavender', 'Lavanda y crema', '#c3b2f5', '#17806b', '#f8f5ff'),
]:
    THEMES[key] = {'name': name, 'is_dark': False, 'variables': {
        '--primario': primary, '--primario-hover': primary,
        '--secundario': secondary, '--bg-sidebar': '#191c24',
        '--bg-sidebar-hover': '#2a2f3a', '--bg-corporativo': background,
        '--bg-tarjeta': '#ffffff', '--color-texto-principal': '#20232c',
        '--color-texto-secundario': '#545966', '--color-texto-sidebar': '#f9f8f2',
        '--color-texto-secundario-sidebar': '#b3b9c6', '--borde': '#d8d9d3',
    }}


def _luminance(hex_color):
    channels = [int(hex_color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4 for value in channels]
    return sum(value * weight for value, weight in zip(linear, (0.2126, 0.7152, 0.0722)))


THEMES = {key: THEMES[key] for key in ('citrus', 'coral', 'lavender', 'graphite', *[key for key in THEMES if key not in ('citrus', 'coral', 'lavender', 'graphite')])}

for theme in THEMES.values():
    variables = theme['variables']
    variables.setdefault('--secundario', '#7861d9')
    # Contraste de texto para los botones, incluso con acentos claros.
    variables['--sobre-primario'] = '#ffffff' if 1.05 / (_luminance(variables['--primario']) + 0.05) >= 4.5 else '#000000'
    variables['--sobre-secundario'] = '#ffffff' if 1.05 / (_luminance(variables['--secundario']) + 0.05) >= 4.5 else '#000000'
