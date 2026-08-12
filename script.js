/* Núcleo compartilhado do protótipo SYNERGIA. */
'use strict';

const NAV_ITEMS = [
    { group: 'VISÃO GERAL', items: [
        { id: 'dashboard', label: 'Dashboard', icon: 'dashboard', href: 'index.html' }
    ]},
    { group: 'OPERAÇÃO', items: [
        { id: 'consulta', label: 'Consulta por lote/WO', icon: 'batch', href: 'consulta.html' },
        { id: 'monitor', label: 'Monitor de execuções', icon: 'monitor', href: 'monitor.html' },
        { id: 'pendencias', label: 'Fila de pendências', icon: 'queue', href: 'pendencias.html' }
    ]},
    { group: 'RESULTADOS', items: [
        { id: 'relatorios', label: 'Relatórios', icon: 'report', href: 'relatorios.html' }
    ]},
    { group: 'SISTEMA', items: [
        { id: 'configuracoes', label: 'Configurações', icon: 'settings', href: 'configuracoes.html' }
    ]}
];

const ICON_ASSET_NAMES = new Set([
    'analytics', 'approve', 'assign', 'automation', 'batch', 'capacity',
    'chevron-down', 'chevron-right', 'clear', 'consolidate', 'dashboard',
    'data-source', 'decision', 'export', 'external-link', 'filter', 'history',
    'human-review', 'indicator', 'integration', 'inventory', 'layers', 'logs',
    'mail', 'monitor', 'mrp', 'notification', 'processing', 'production',
    'queue', 'refresh', 'reject', 'report', 'rules', 'run', 'schedule',
    'search', 'settings', 'shield', 'source-offline', 'spreadsheet',
    'state-alert', 'state-attention', 'state-error', 'state-info',
    'state-neutral', 'state-partial', 'state-success', 'state-unavailable',
    'supplier', 'sync', 'timer', 'validation', 'view'
]);

const INLINE_ICONS = {
    sun: '<circle cx="12" cy="12" r="4"></circle><path d="M12 2v2M12 20v2M4.93 4.93l1.42 1.42M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.42-1.42M17.66 6.34l1.41-1.41"></path>',
    moon: '<path d="M20.5 14.2A8.5 8.5 0 0 1 9.8 3.5 8.5 8.5 0 1 0 20.5 14.2Z"></path>',
    tv: '<rect x="3" y="5" width="18" height="12" rx="2"></rect><path d="M8 21h8M12 17v4"></path>',
    menu: '<path d="M4 7h16M4 12h16M4 17h16"></path>',
    bell: '<path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"></path>'
};

const iconCache = new Map();
let tvCarouselInterval = null;
let tvResumeTimeout = null;
let tvInteractionController = null;
let currentPanelIndex = 0;
let iconObserver = null;
let lastFocusedElement = null;
let focusTrapHandler = null;
let activeFocusTrap = null;
let globalHandlersReady = false;
let clockInterval = null;

const storage = {
    get(key) {
        try { return window.localStorage.getItem(key); } catch (_) { return null; }
    },
    set(key, value) {
        try { window.localStorage.setItem(key, value); } catch (_) { /* armazenamento opcional */ }
    },
    json(key, fallback = {}) {
        try { return JSON.parse(this.get(key) || '') || fallback; } catch (_) { return fallback; }
    }
};

function escapeHTML(value) {
    return String(value ?? '').replace(/[&<>'"]/g, character => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
    })[character]);
}

function normalizeText(value) {
    return String(value ?? '')
        .normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '')
        .trim()
        .toLocaleLowerCase('pt-BR');
}

function loadIcons() {
    ICON_ASSET_NAMES.forEach(name => iconCache.set(name, `assets/icons/${name}.svg`));
    Object.keys(INLINE_ICONS).forEach(name => iconCache.set(name, INLINE_ICONS[name]));
}

function getIcon(name, cls = '') {
    const safeName = ICON_ASSET_NAMES.has(name) || Object.hasOwn(INLINE_ICONS, name)
        ? name
        : 'state-neutral';
    const classNames = `icon icon-${safeName}${cls ? ` ${cls}` : ''}`;

    if (Object.hasOwn(INLINE_ICONS, safeName)) {
        return `<svg class="${escapeHTML(classNames)}" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false" data-icon-rendered="true">${INLINE_ICONS[safeName]}</svg>`;
    }

    const path = iconCache.get(safeName) || `assets/icons/${safeName}.svg`;
    return `<img class="${escapeHTML(classNames)} icon-asset" src="${escapeHTML(path)}" alt="" aria-hidden="true" draggable="false" data-icon-rendered="true">`;
}

function getIconEl(name, cls = '') {
    const wrapper = document.createElement('span');
    wrapper.innerHTML = getIcon(name, cls);
    return wrapper.firstElementChild;
}

function hydrateIconPlaceholders(root = document) {
    const candidates = [];
    if (root instanceof Element && root.matches('[data-icon], span[class^="icon-"], span[class*=" icon-"]')) {
        candidates.push(root);
    }
    if (root.querySelectorAll) {
        candidates.push(...root.querySelectorAll('[data-icon], span[class^="icon-"], span[class*=" icon-"]'));
    }

    candidates.forEach(element => {
        if (element.dataset.iconRendered === 'true' || element.classList.contains('icon-asset')) return;
        const className = [...element.classList].find(value => value.startsWith('icon-'));
        const name = element.dataset.icon || (className ? className.slice(5) : '');
        if (!name) return;
        element.dataset.iconRendered = 'true';
        element.innerHTML = getIcon(name);
    });
}

function observeDynamicIcons() {
    if (iconObserver || !document.body) return;
    iconObserver = new MutationObserver(mutations => {
        mutations.forEach(mutation => mutation.addedNodes.forEach(node => {
            if (node.nodeType === Node.ELEMENT_NODE) hydrateIconPlaceholders(node);
        }));
    });
    iconObserver.observe(document.body, { childList: true, subtree: true });
}

function initApp(currentPage) {
    loadIcons();
    applyStoredUISettings();
    initTheme();
    renderSidebar(currentPage);
    renderHeader();
    hydrateIconPlaceholders(document);
    observeDynamicIcons();
    initGlobalAccessibility();

    const requestedByQuery = new URLSearchParams(window.location.search).get('tv') === '1';
    const tvMode = requestedByQuery || storage.get('synergia-tv') === 'true';
    const tvApplied = setTVMode(tvMode, { initial: true });
    if (tvMode && !tvApplied) return;

    startClock('tv-clock');
    const tvLastUpdate = document.getElementById('tv-last-update');
    if (tvLastUpdate && window.SYNERGIA_DATA?.meta?.lastUpdate) {
        tvLastUpdate.textContent = formatDateTime(window.SYNERGIA_DATA.meta.lastUpdate);
        tvLastUpdate.setAttribute('datetime', window.SYNERGIA_DATA.meta.lastUpdate);
    }
}

function applyStoredUISettings() {
    const settings = storage.json('synergia-settings', {});
    const densityAliases = { Compact: 'compact', Normal: 'normal', Comfortable: 'comfortable' };
    const fontAliases = { Pequena: 'small', Normal: 'normal', Grande: 'large' };
    const density = densityAliases[settings.density] || settings.density || 'normal';
    const fontSize = fontAliases[settings.fontSize] || settings.fontSize || 'normal';
    document.documentElement.dataset.density = ['compact', 'normal', 'comfortable'].includes(density) ? density : 'normal';
    document.documentElement.dataset.fontSize = ['small', 'normal', 'large'].includes(fontSize) ? fontSize : 'normal';

    if (settings.tvInterval != null && storage.get('synergia-tv-interval') == null) {
        storage.set('synergia-tv-interval', String(settings.tvInterval));
    }
}

function initTheme() {
    const preference = storage.get('synergia-theme');
    const prefersDark = window.matchMedia?.('(prefers-color-scheme: dark)').matches;
    applyTheme(preference === 'light' || preference === 'dark' ? preference : (prefersDark ? 'dark' : 'light'));

    const media = window.matchMedia?.('(prefers-color-scheme: dark)');
    if (media && !media.__synergiaBound) {
        media.addEventListener?.('change', event => {
            const stored = storage.get('synergia-theme');
            if (!stored || stored === 'auto') applyTheme(event.matches ? 'dark' : 'light');
        });
        media.__synergiaBound = true;
    }
}

function applyTheme(theme) {
    const selected = theme === 'dark' ? 'dark' : 'light';
    document.documentElement.dataset.theme = selected;
    document.documentElement.style.colorScheme = selected;

    document.querySelectorAll('.sidebar-logo img').forEach(logo => {
        logo.src = selected === 'dark'
            ? 'assets/logos/logo-negativa-horizontal.png'
            : 'assets/logos/logo-horizontal.png';
    });

    const button = document.getElementById('theme-toggle-btn');
    if (button) {
        const nextLabel = selected === 'dark' ? 'Ativar modo claro' : 'Ativar modo escuro';
        button.innerHTML = getIcon(selected === 'dark' ? 'sun' : 'moon');
        button.setAttribute('aria-label', nextLabel);
        button.title = nextLabel;
    }
}

function setTheme(theme) {
    if (theme === 'auto') {
        storage.set('synergia-theme', 'auto');
        applyTheme(window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
        return;
    }
    const selected = theme === 'dark' ? 'dark' : 'light';
    storage.set('synergia-theme', selected);
    applyTheme(selected);
}

function toggleTheme() {
    setTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark');
}

function getTVInterval() {
    const raw = Number(storage.get('synergia-tv-interval'));
    if (!Number.isFinite(raw) || raw <= 0) return 15000;
    const milliseconds = raw <= 120 ? raw * 1000 : raw;
    return Math.min(120000, Math.max(5000, milliseconds));
}

function setTVMode(enabled, options = {}) {
    const panelsContainer = document.getElementById('tv-panels');
    if (enabled && !panelsContainer) {
        storage.set('synergia-tv', 'true');
        const fileName = window.location.pathname.split('/').pop() || 'index.html';
        if (fileName !== 'index.html') {
            const destination = new URL('index.html', window.location.href);
            destination.searchParams.set('tv', '1');
            window.location.assign(destination.href);
        } else {
            storage.set('synergia-tv', 'false');
            document.documentElement.dataset.tv = 'false';
        }
        return false;
    }

    const active = Boolean(enabled);
    document.documentElement.dataset.tv = active ? 'true' : 'false';
    storage.set('synergia-tv', active ? 'true' : 'false');
    updateTVAccessibility(active);

    if (active) {
        currentPanelIndex = Math.max(0, [...panelsContainer.querySelectorAll('.tv-panel')].findIndex(panel => panel.classList.contains('active')));
        showTVPanel(currentPanelIndex);
        startTVCarousel('tv-panels', getTVInterval());
        setupTVInteraction();
    } else {
        stopTVCarousel();
        removeTVInteraction();
        if (!options.initial) document.getElementById('main-content')?.focus({ preventScroll: true });
    }
    return true;
}

function updateTVAccessibility(enabled) {
    const header = document.querySelector('.tv-header');
    const normalContent = document.querySelectorAll('[data-tv-hide]');
    const sidebar = document.getElementById('sidebar');
    const appHeader = document.getElementById('header');

    header?.setAttribute('aria-hidden', enabled ? 'false' : 'true');
    [sidebar, appHeader].forEach(element => element?.setAttribute('aria-hidden', enabled ? 'true' : 'false'));
    normalContent.forEach(element => {
        element.setAttribute('aria-hidden', enabled ? 'true' : 'false');
        element.inert = enabled;
    });
}

function showTVPanel(index) {
    const panels = [...document.querySelectorAll('#tv-panels .tv-panel')];
    if (!panels.length) return;
    currentPanelIndex = ((index % panels.length) + panels.length) % panels.length;
    panels.forEach((panel, panelIndex) => {
        const isActive = panelIndex === currentPanelIndex;
        panel.classList.toggle('active', isActive);
        panel.setAttribute('aria-hidden', isActive ? 'false' : 'true');
        panel.inert = !isActive;
    });
}

function startTVCarousel(containerId = 'tv-panels', intervalMs = getTVInterval()) {
    stopTVCarousel();
    const container = document.getElementById(containerId);
    const panels = container ? container.querySelectorAll('.tv-panel') : [];
    if (!panels.length) return;
    showTVPanel(currentPanelIndex);
    if (panels.length <= 1 || window.matchMedia?.('(prefers-reduced-motion: reduce)').matches || document.hidden) return;
    tvCarouselInterval = window.setInterval(() => showTVPanel(currentPanelIndex + 1), intervalMs);
}

function stopTVCarousel() {
    if (tvCarouselInterval) window.clearInterval(tvCarouselInterval);
    tvCarouselInterval = null;
}

function handleTVInteraction() {
    if (document.documentElement.dataset.tv !== 'true') return;
    stopTVCarousel();
    if (tvResumeTimeout) window.clearTimeout(tvResumeTimeout);
    tvResumeTimeout = window.setTimeout(() => startTVCarousel('tv-panels', getTVInterval()), 30000);
}

function setupTVInteraction() {
    removeTVInteraction();
    tvInteractionController = new AbortController();
    const options = { signal: tvInteractionController.signal, passive: true };
    window.addEventListener('pointerdown', handleTVInteraction, options);
    window.addEventListener('wheel', handleTVInteraction, options);
    window.addEventListener('keydown', handleTVInteraction, { signal: tvInteractionController.signal });
    document.addEventListener('visibilitychange', handleTVVisibility, { signal: tvInteractionController.signal });
}

function handleTVVisibility() {
    if (document.hidden) stopTVCarousel();
    else if (document.documentElement.dataset.tv === 'true') startTVCarousel('tv-panels', getTVInterval());
}

function removeTVInteraction() {
    tvInteractionController?.abort();
    tvInteractionController = null;
    if (tvResumeTimeout) window.clearTimeout(tvResumeTimeout);
    tvResumeTimeout = null;
}

function renderSidebar(currentPage) {
    const sidebar = document.getElementById('sidebar');
    if (!sidebar) return;
    const logo = document.documentElement.dataset.theme === 'dark'
        ? 'assets/logos/logo-negativa-horizontal.png'
        : 'assets/logos/logo-horizontal.png';

    const groups = NAV_ITEMS.map(group => `
        <div class="sidebar-group">
            <div class="sidebar-group-label">${escapeHTML(group.group)}</div>
            ${group.items.map(item => `
                <a href="${item.href}" class="sidebar-item${item.id === currentPage ? ' active' : ''}"${item.id === currentPage ? ' aria-current="page"' : ''} title="${escapeHTML(item.label)}">
                    ${getIcon(item.icon)}<span>${escapeHTML(item.label)}</span>
                </a>`).join('')}
        </div>`).join('');

    sidebar.innerHTML = `
        <div class="sidebar-logo"><img src="${logo}" alt="SYNERGIA"></div>
        <nav class="sidebar-nav" aria-label="Navegação principal">${groups}</nav>`;

    if (!document.querySelector('.sidebar-overlay')) {
        const overlay = document.createElement('div');
        overlay.className = 'sidebar-overlay';
        overlay.setAttribute('aria-hidden', 'true');
        overlay.addEventListener('click', closeSidebar);
        sidebar.insertAdjacentElement('afterend', overlay);
    }
}

function renderHeader() {
    const header = document.getElementById('header');
    if (!header) return;
    const dark = document.documentElement.dataset.theme === 'dark';
    const alertCount = window.SYNERGIA_DATA?.alerts?.length || 0;
    header.innerHTML = `
        <button type="button" class="btn btn-icon hamburger" id="sidebar-toggle" onclick="toggleSidebar()" aria-label="Abrir menu" aria-controls="sidebar" aria-expanded="false">${getIcon('menu')}</button>
        <div class="header-search" role="search">
            ${getIcon('search')}
            <label class="visually-hidden" for="global-search">Buscar lote, Workorder ou serial</label>
            <input id="global-search" type="search" class="form-input" placeholder="Buscar lote, Workorder ou serial" autocomplete="off">
        </div>
        <div class="header-actions">
            <button type="button" class="btn btn-icon" id="theme-toggle-btn" onclick="toggleTheme()" aria-label="${dark ? 'Ativar modo claro' : 'Ativar modo escuro'}">${getIcon(dark ? 'sun' : 'moon')}</button>
            <button type="button" class="btn btn-icon" onclick="setTVMode(true)" aria-label="Ativar Modo TV" title="Ativar Modo TV">${getIcon('tv')}</button>
            <button type="button" class="btn btn-icon notification-button" aria-label="${alertCount} notificações" title="Notificações">
                ${getIcon('bell')}${alertCount ? '<span class="notification-dot" aria-hidden="true"></span>' : ''}
            </button>
            <div class="user-profile" aria-label="Usuário de demonstração, perfil administrador">
                <div class="avatar" aria-hidden="true">DE</div>
                <div class="user-info"><div class="user-name">Demonstração</div><div class="user-role">Administrador</div></div>
                ${getIcon('chevron-down')}
            </div>
        </div>`;

    const search = header.querySelector('#global-search');
    const query = new URLSearchParams(window.location.search).get('q');
    if (query) search.value = query;
    search.addEventListener('keydown', event => {
        if (event.key !== 'Enter') return;
        const value = search.value.trim();
        if (!value) return;
        window.location.href = `consulta.html?q=${encodeURIComponent(value)}`;
    });
}

function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    const overlay = document.querySelector('.sidebar-overlay');
    const button = document.getElementById('sidebar-toggle');
    if (!sidebar) return;
    const open = !sidebar.classList.contains('open');
    sidebar.classList.toggle('open', open);
    overlay?.classList.toggle('active', open);
    overlay?.setAttribute('aria-hidden', open ? 'false' : 'true');
    button?.setAttribute('aria-expanded', open ? 'true' : 'false');
    button?.setAttribute('aria-label', open ? 'Fechar menu' : 'Abrir menu');
}

function closeSidebar() {
    document.getElementById('sidebar')?.classList.remove('open');
    const overlay = document.querySelector('.sidebar-overlay');
    overlay?.classList.remove('active');
    overlay?.setAttribute('aria-hidden', 'true');
    const button = document.getElementById('sidebar-toggle');
    button?.setAttribute('aria-expanded', 'false');
    button?.setAttribute('aria-label', 'Abrir menu');
}

function showModal(modalId) {
    const modal = document.getElementById(modalId);
    if (!modal) return;
    lastFocusedElement = document.activeElement;
    modal.classList.add('active');
    modal.setAttribute('aria-hidden', 'false');
    document.body.classList.add('modal-open');
    document.querySelector('.app')?.setAttribute('inert', '');
    trapFocus(modal);
    const focusable = getFocusableElements(modal);
    (focusable[0] || modal.querySelector('.modal') || modal).focus({ preventScroll: true });
}

function hideModal(modalId) {
    const modal = document.getElementById(modalId);
    if (!modal) return;
    modal.classList.remove('active');
    modal.setAttribute('aria-hidden', 'true');
    releaseFocus();
    if (!document.querySelector('.modal-overlay.active')) {
        document.body.classList.remove('modal-open');
        document.querySelector('.app')?.removeAttribute('inert');
    }
    if (lastFocusedElement?.isConnected) lastFocusedElement.focus({ preventScroll: true });
}

function confirmAction(title, message, onConfirm) {
    const titleElement = document.getElementById('modal-confirm-title');
    const bodyElement = document.getElementById('modal-confirm-body');
    const confirmButton = document.getElementById('modal-confirm-action');
    if (titleElement) titleElement.textContent = title;
    if (bodyElement) {
        bodyElement.replaceChildren();
        const paragraph = document.createElement('p');
        paragraph.textContent = message;
        bodyElement.appendChild(paragraph);
    }
    if (confirmButton) confirmButton.onclick = () => {
        onConfirm?.();
        hideModal('modal-confirm');
    };
    showModal('modal-confirm');
}

function getFocusableElements(element) {
    return [...element.querySelectorAll('a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])')]
        .filter(item => item.getClientRects().length > 0 && item.getAttribute('aria-hidden') !== 'true');
}

function trapFocus(element) {
    releaseFocus();
    activeFocusTrap = element;
    focusTrapHandler = event => {
        if (event.key !== 'Tab') return;
        const focusable = getFocusableElements(element);
        if (!focusable.length) { event.preventDefault(); return; }
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) { last.focus(); event.preventDefault(); }
        else if (!event.shiftKey && document.activeElement === last) { first.focus(); event.preventDefault(); }
    };
    element.addEventListener('keydown', focusTrapHandler);
}

function releaseFocus() {
    if (activeFocusTrap && focusTrapHandler) activeFocusTrap.removeEventListener('keydown', focusTrapHandler);
    activeFocusTrap = null;
    focusTrapHandler = null;
}

function initGlobalAccessibility() {
    if (globalHandlersReady) return;
    globalHandlersReady = true;
    document.getElementById('main-content')?.setAttribute('tabindex', '-1');
    document.querySelectorAll('.modal-overlay').forEach(modal => {
        modal.addEventListener('pointerdown', event => {
            if (event.target === modal) hideModal(modal.id);
        });
    });
    document.addEventListener('keydown', event => {
        if (event.key !== 'Escape') return;
        const activeModal = document.querySelector('.modal-overlay.active');
        if (activeModal) { hideModal(activeModal.id); return; }
        closeSidebar();
    });
}

function renderPagination(containerId, total, current, pageSize, onChange) {
    const container = document.getElementById(containerId);
    if (!container) return;
    const count = Math.max(0, Number(total) || 0);
    const size = Math.max(1, Number(pageSize) || 10);
    const totalPages = Math.max(1, Math.ceil(count / size));
    const page = Math.min(totalPages, Math.max(1, Number(current) || 1));
    const callback = typeof onChange === 'function' ? onChange : window[onChange];
    const start = count ? ((page - 1) * size) + 1 : 0;
    const end = Math.min(page * size, count);
    container.innerHTML = `<div class="table-info" aria-live="polite">${start}–${end} de ${count}</div><div class="pagination"><button type="button" class="btn btn-secondary btn-sm pagination-prev" ${page === 1 ? 'disabled' : ''}>Anterior</button><span class="pagination-current" aria-label="Página ${page} de ${totalPages}">${page} / ${totalPages}</span><button type="button" class="btn btn-secondary btn-sm pagination-next" ${page === totalPages ? 'disabled' : ''}>Próxima</button></div>`;
    container.querySelector('.pagination-prev')?.addEventListener('click', () => callback?.(page - 1));
    container.querySelector('.pagination-next')?.addEventListener('click', () => callback?.(page + 1));
}

function parseDate(value) {
    if (!value) return null;
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? null : date;
}

function formatDateTime(iso) {
    const date = parseDate(iso);
    if (!date) return 'Não informado';
    return new Intl.DateTimeFormat('pt-BR', { dateStyle: 'short', timeStyle: 'short' }).format(date);
}

function formatDate(iso) {
    if (/^\d{4}-\d{2}-\d{2}$/.test(String(iso))) {
        const [year, month, day] = String(iso).split('-');
        return `${day}/${month}/${year}`;
    }
    const date = parseDate(iso);
    return date ? new Intl.DateTimeFormat('pt-BR').format(date) : 'Não informado';
}

function formatTime(iso) {
    const date = parseDate(iso);
    return date ? new Intl.DateTimeFormat('pt-BR', { hour: '2-digit', minute: '2-digit' }).format(date) : 'Não informado';
}

function formatDuration(seconds) {
    if (!Number.isFinite(Number(seconds))) return 'Não informado';
    const total = Math.max(0, Number(seconds));
    const minutes = Math.floor(total / 60);
    return `${minutes} min ${Math.round(total % 60)} s`;
}

function formatNumber(value) {
    return Number.isFinite(Number(value)) ? new Intl.NumberFormat('pt-BR').format(Number(value)) : 'Não informado';
}

function showToast(message, type = 'info', durationMs = 3000) {
    const container = document.getElementById('toast-container');
    if (!container) return;
    const normalizedType = ['success', 'error', 'info', 'warning', 'attention'].includes(type) ? type : 'info';
    const toast = document.createElement('div');
    toast.className = `toast toast-${normalizedType}`;
    toast.setAttribute('role', normalizedType === 'error' ? 'alert' : 'status');
    toast.textContent = String(message);
    container.appendChild(toast);
    window.setTimeout(() => {
        toast.classList.add('toast-leaving');
        window.setTimeout(() => toast.remove(), 220);
    }, Math.max(1000, Number(durationMs) || 3000));
}

function announce(message, politeness = 'polite') {
    let region = document.getElementById('synergia-announcer');
    if (!region) {
        region = document.createElement('div');
        region.id = 'synergia-announcer';
        region.className = 'visually-hidden';
        document.body.appendChild(region);
    }
    region.setAttribute('aria-live', politeness);
    region.textContent = '';
    window.setTimeout(() => { region.textContent = String(message); }, 20);
}

function startClock(elementId) {
    const element = document.getElementById(elementId);
    if (!element) return;
    if (clockInterval) window.clearInterval(clockInterval);
    const update = () => {
        const now = new Date();
        element.textContent = new Intl.DateTimeFormat('pt-BR', { hour: '2-digit', minute: '2-digit', second: '2-digit' }).format(now);
        if (element.tagName === 'TIME') element.dateTime = now.toISOString();
    };
    update();
    clockInterval = window.setInterval(update, 1000);
}

const STATUS_LABELS = {
    success: 'Sucesso', concluida: 'Concluída', resolvida: 'Resolvida', gerado: 'Gerado',
    error: 'Erro', erro: 'Erro', falha: 'Falha', bloqueada: 'Bloqueada',
    warning: 'Alerta', alert: 'Alerta', divergencia: 'Divergência', escalada: 'Escalada',
    attention: 'Atenção', info: 'Informação', em_analise: 'Em análise',
    partial: 'Parcial', parcial: 'Parcial', unavailable: 'Indisponível', indisponivel: 'Indisponível',
    processing: 'Processando', processando: 'Processando', stale: 'Desatualizado',
    aberta: 'Aberta', nova: 'Nova', pendente: 'Pendente', neutro: 'Neutro'
};

function getBadgeHTML(status, label) {
    const normalized = normalizeText(status).replace(/\s+/g, '_');
    let variant = 'neutral';
    if (['success', 'concluida', 'resolvida', 'gerado'].includes(normalized)) variant = 'success';
    else if (['error', 'erro', 'falha', 'bloqueada'].includes(normalized)) variant = 'error';
    else if (['warning', 'alert', 'divergencia', 'escalada'].includes(normalized)) variant = 'alert';
    else if (normalized === 'attention') variant = 'attention';
    else if (['info', 'em_analise', 'aberta', 'nova'].includes(normalized)) variant = 'info';
    else if (['partial', 'parcial'].includes(normalized)) variant = 'partial';
    else if (['unavailable', 'indisponivel'].includes(normalized)) variant = 'unavailable';
    else if (['processing', 'processando'].includes(normalized)) variant = 'processing';
    else if (normalized === 'stale') variant = 'stale';
    const text = label ?? STATUS_LABELS[normalized] ?? String(status || 'Não informado');
    return `<span class="badge badge-${variant}">${escapeHTML(text)}</span>`;
}

function getImpactBadge(impact) {
    const normalized = normalizeText(impact);
    const mapping = { critico: 'error', critica: 'error', alto: 'alert', alta: 'alert', medio: 'attention', media: 'attention', baixo: 'info', baixa: 'info' };
    const label = normalized ? normalized.charAt(0).toLocaleUpperCase('pt-BR') + normalized.slice(1) : 'Não informado';
    return getBadgeHTML(mapping[normalized] || 'neutral', label);
}

function getStatusBadge(status) {
    const normalized = normalizeText(status).replace(/\s+/g, '_');
    return getBadgeHTML(normalized, STATUS_LABELS[normalized]);
}

function renderState(containerId, state, message) {
    const element = document.getElementById(containerId);
    if (!element) return;
    const wrapper = document.createElement('div');
    wrapper.className = `content-state content-state-${state}`;
    wrapper.setAttribute('role', state === 'error' ? 'alert' : 'status');
    wrapper.innerHTML = state === 'loading' ? `${getIcon('sync', 'spin')}<span></span>` : '<span></span>';
    wrapper.querySelector('span:last-child').textContent = message;
    element.replaceChildren(wrapper);
}

function showLoading(containerId) { renderState(containerId, 'loading', 'Carregando…'); }
function hideLoading() { /* o conteúdo é substituído pela função de renderização da tela */ }
function showEmpty(containerId, message = 'Nenhum resultado encontrado.') { renderState(containerId, 'empty', message); }
function showError(containerId, message = 'Não foi possível carregar os dados.') { renderState(containerId, 'error', message); }

function debounce(callback, wait = 250) {
    let timeout;
    return (...args) => {
        window.clearTimeout(timeout);
        timeout = window.setTimeout(() => callback(...args), wait);
    };
}

window.SYNERGIA_UTILS = Object.freeze({
    escapeHTML,
    normalizeText,
    formatDateTime,
    formatDate,
    formatTime,
    formatDuration,
    formatNumber,
    debounce,
    matchesQuery(record, query, fields = []) {
        const search = normalizeText(query);
        return !search || fields.some(field => normalizeText(record?.[field]).includes(search));
    },
    paginate(items, page = 1, pageSize = 10) {
        const size = Math.max(1, Number(pageSize) || 10);
        const current = Math.max(1, Number(page) || 1);
        return items.slice((current - 1) * size, current * size);
    }
});
