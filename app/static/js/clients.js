/* Búsqueda en el directorio completo y páginas de 24 tarjetas. */
(() => {
    'use strict';
    const directory = document.getElementById('clientDirectory');
    if (!directory) return;
    const search = document.getElementById('searchCliente');
    const order = document.getElementById('sortCliente');
    const grid = document.getElementById('clientesGrid');
    const cards = Array.from(grid.querySelectorAll('.directory-client'));
    const filters = Array.from(directory.querySelectorAll('[data-filter]'));
    const pageSize = 24;
    const number = new Intl.NumberFormat('es-BO');
    const collator = new Intl.Collator('es', { sensitivity: 'base', numeric: true });
    const normalize = value => value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase('es').trim();
    let filter = 'todos';
    let page = 1;
    cards.forEach(card => {
        card.searchText = normalize(`${card.dataset.nombre} ${card.dataset.ci} ${card.dataset.telefono}`);
        card.phoneDigits = card.dataset.telefono.replace(/\D/g, '');
        const words = card.dataset.nombre.match(/\p{L}+/gu) || [];
        card.querySelector('.client-initials').textContent = words.slice(0, 2).map(word => word[0]).join('').toLocaleUpperCase('es') || '?';
    });
    function render(scroll = false) {
        const query = normalize(search.value);
        const digits = query.replace(/\D/g, '');
        const phoneQuery = /^[+\d\s().-]+$/.test(query) && digits.length >= 3;
        const matches = cards.filter(card => {
            const passesSearch = card.searchText.includes(query) || (phoneQuery && card.phoneDigits.includes(digits));
            const active = Number(card.dataset.activos);
            return passesSearch && (filter === 'todos' || (filter === 'activos' && active > 0) ||
                (filter === 'sin_activos' && active === 0) || (filter === 'vip' && Number(card.dataset.prestamos) >= 5));
        }).sort((a, b) => {
            const key = order.value === 'mas_prestamos' ? 'prestamos' : order.value === 'mayor_monto' ? 'monto' : null;
            return (key && Number(b.dataset[key]) - Number(a.dataset[key])) || collator.compare(a.dataset.nombre, b.dataset.nombre) || collator.compare(a.dataset.ci, b.dataset.ci);
        });
        const pages = Math.max(1, Math.ceil(matches.length / pageSize));
        page = Math.max(1, Math.min(page, pages));
        cards.forEach(card => { card.hidden = true; });
        const start = (page - 1) * pageSize;
        const fragment = document.createDocumentFragment();
        matches.slice(start, start + pageSize).forEach((card, index) => {
            card.hidden = false;
            card.style.setProperty('--card-delay', `${Math.min(index, 5) * 35}ms`);
            fragment.appendChild(card);
        });
        grid.appendChild(fragment);
        document.getElementById('noResults').hidden = matches.length !== 0;
        document.getElementById('clientResults').textContent = matches.length ?
            `${number.format(start + 1)}–${number.format(Math.min(start + pageSize, matches.length))} de ${number.format(matches.length)} ${matches.length === 1 ? 'cliente' : 'clientes'}${matches.length !== cards.length ? ` · ${number.format(cards.length)} en total` : ''}` : '0 clientes encontrados';
        document.getElementById('clientPage').textContent = `Página ${page} de ${pages}`;
        document.getElementById('clientPagination').hidden = pages <= 1;
        document.getElementById('clientPrevious').disabled = page === 1;
        document.getElementById('clientNext').disabled = page === pages;
        filters.forEach(button => button.setAttribute('aria-pressed', String(button.dataset.filter === filter)));
        if (scroll) document.getElementById('directoryResults').scrollIntoView({ block: 'start', behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' });
    }
    function reset() { search.value = ''; filter = 'todos'; order.value = 'alfabetico'; page = 1; render(); }
    search.addEventListener('input', () => { page = 1; render(); });
    order.addEventListener('change', () => { page = 1; render(); });
    filters.forEach(button => button.addEventListener('click', () => { filter = button.dataset.filter; page = 1; render(); }));
    document.getElementById('clearClientes').addEventListener('click', reset);
    document.getElementById('resetEmptyClientes')?.addEventListener('click', () => { reset(); search.focus(); });
    document.getElementById('clientPrevious').addEventListener('click', () => { page--; render(true); });
    document.getElementById('clientNext').addEventListener('click', () => { page++; render(true); });
    document.addEventListener('keydown', event => {
        if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
            event.preventDefault(); search.focus(); search.select();
        } else if (event.key === 'Escape' && document.activeElement === search && search.value) {
            search.value = ''; page = 1; render();
        }
    });
    render();
})();
