/* Mensajes del sistema: texto seguro, teclado y tiempo para leer. */
function showToast(message, type = 'info', duration) {
    const container = document.getElementById('toast-container');
    if (!container) return;
    if (type === 'error') type = 'danger';
    const variants = {
        success: { icon: 'bi-check2-circle', title: 'Todo listo', time: 5000 },
        info: { icon: 'bi-info-circle', title: 'Para tener en cuenta', time: 6500 },
        warning: { icon: 'bi-exclamation-triangle', title: 'Revisa este detalle', time: 9000 },
        danger: { icon: 'bi-x-octagon', title: 'No se pudo completar', time: 0 },
    };
    if (!variants[type]) type = 'info';
    const variant = variants[type];
    const toast = document.createElement('div');
    toast.className = `toast-notification ${type}`;
    toast.setAttribute('role', type === 'danger' || type === 'warning' ? 'alert' : 'status');
    toast.setAttribute('aria-atomic', 'true');
    const icon = document.createElement('span');
    icon.className = 'toast-icon';
    icon.setAttribute('aria-hidden', 'true');
    const glyph = document.createElement('i');
    glyph.className = `bi ${variant.icon}`;
    icon.append(glyph);
    const copy = document.createElement('div');
    copy.className = 'toast-copy';
    const title = document.createElement('strong');
    title.className = 'toast-title';
    title.textContent = variant.title;
    const text = document.createElement('span');
    text.className = 'toast-message';
    text.textContent = String(message);
    copy.append(title, text);
    const close = document.createElement('button');
    close.type = 'button';
    close.className = 'toast-close';
    close.setAttribute('aria-label', 'Cerrar notificación');
    close.textContent = '×';
    close.addEventListener('click', () => closeToast(toast));
    toast.append(icon, copy, close);
    const lifetime = duration === undefined ? variant.time : Math.max(0, Number(duration) || 0);
    if (lifetime > 0) {
        const progress = document.createElement('div');
        progress.className = 'toast-progress';
        progress.setAttribute('aria-hidden', 'true');
        toast.append(progress);
        let remaining = lifetime;
        let started;
        let timer;
        function pause() {
            if (!timer) return;
            clearTimeout(timer);
            timer = null;
            remaining = Math.max(0, remaining - (performance.now() - started));
            progress.style.transition = 'none';
            progress.style.transform = `scaleX(${remaining / lifetime})`;
        }
        function resume() {
            if (timer || toast.matches(':hover') || toast.contains(document.activeElement) || toast.classList.contains('closing')) return;
            started = performance.now();
            progress.style.transition = `transform ${remaining}ms linear`;
            progress.style.transform = 'scaleX(0)';
            timer = setTimeout(() => closeToast(toast), remaining);
        }
        toast.addEventListener('mouseenter', pause);
        toast.addEventListener('mouseleave', resume);
        toast.addEventListener('focusin', pause);
        toast.addEventListener('focusout', () => setTimeout(resume, 0));
        toast._stopNoticeTimer = pause;
        container.append(toast);
        progress.getBoundingClientRect();
        requestAnimationFrame(resume);
    } else {
        container.append(toast);
    }
    return toast;
}

function closeToast(toast) {
    if (!toast || toast.classList.contains('closing')) return;
    toast._stopNoticeTimer?.();
    toast.classList.add('closing');
    setTimeout(() => toast.remove(), 160);
}
