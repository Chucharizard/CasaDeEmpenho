/* Vista previa local: las preferencias se guardan solo al enviar el formulario. */
document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('theme-form');
    if (!form) return;
    const themes = JSON.parse(document.getElementById('appearance-data').textContent);
    const root = document.documentElement;
    const saved = { theme: form.elements.tema.value, style: form.elements.estilo.value };
    const status = document.getElementById('appearance-status');
    function preview() {
        const theme = themes[form.elements.tema.value];
        if (!theme) return;
        for (const [key, value] of Object.entries(theme.variables)) root.style.setProperty(key, value, 'important');
        root.dataset.theme = form.elements.tema.value;
        root.dataset.dark = theme.is_dark ? '1' : '0';
        root.dataset.design = form.elements.estilo.value;
        const changed = saved.theme !== root.dataset.theme || saved.style !== root.dataset.design;
        status.textContent = changed ? 'Vista previa · guarda el diseño para conservarlo.' : 'Estás viendo el diseño guardado.';
        document.getElementById('appearance-reset').disabled = !changed;
    }
    form.addEventListener('change', preview);
    document.getElementById('appearance-reset').addEventListener('click', () => {
        form.elements.tema.value = saved.theme;
        form.elements.estilo.value = saved.style;
        preview();
    });
    document.querySelectorAll('[data-demo-toast]').forEach(button => button.addEventListener('click', () => {
        const type = button.dataset.demoToast;
        const messages = {
            success: 'Ejemplo: los cambios se guardaron correctamente.',
            info: 'Ejemplo: tu respaldo está listo para consultar.',
            warning: 'Ejemplo: revisa los datos antes de continuar.',
            danger: 'Ejemplo: la operación no pudo completarse. Puedes revisar los datos e intentarlo de nuevo.',
        };
        showToast(messages[type], type);
    }));
    preview();
});
