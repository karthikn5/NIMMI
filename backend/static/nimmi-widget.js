(async function() {
    // Prevent multiple initializations
    if (window.__NIMMI_WIDGET_LOADED__) return;
    window.__NIMMI_WIDGET_LOADED__ = true;

    // Configuration
    // currentScript is null when a page builder or tag manager inserts the tag; then find it by its bot id.
    const script = document.currentScript
        || document.querySelector('script[data-bot-id][src*="nimmi-widget"]')
        || (function() {
            const scripts = document.getElementsByTagName('script');
            return scripts[scripts.length - 1];
        })();

    const botId = script.getAttribute('data-bot-id');
    const apiBase = script.getAttribute('data-api-url') || 'https://api.nimmiai.in';

    if (!botId) {
        console.error('Nimmi Widget: data-bot-id is required');
        return;
    }

    // Fetch config
    let config = {};
    let visual = {};
    try {
        const res = await fetch(`${apiBase}/api/bots/${botId}/config`);
        if (res.ok) {
            config = await res.json();
            visual = config.visual_config || {};
        }
    } catch (e) {
        console.warn('Nimmi Widget: failed to fetch config, using defaults');
    }

    // Where the chat appears: every page, only some, or all but some; optionally not on phones.
    const here = (location.pathname.replace(/\/+$/, '') || '/').toLowerCase();
    const onPath = (pattern) => {
        let p = String(pattern || '').trim().toLowerCase();
        if (!p) return false;
        try { if (/^https?:\/\//.test(p)) p = new URL(p).pathname; } catch (e) {}
        if (!p.startsWith('/')) p = '/' + p;
        if (p.endsWith('*')) {
            const base = p.slice(0, -1).replace(/\/+$/, '');
            return here === (base || '/') || here.startsWith(base + '/');
        }
        return here === (p.replace(/\/+$/, '') || '/');
    };
    const pageRule = visual.page_rule || 'all';
    const listed = (Array.isArray(visual.page_paths) ? visual.page_paths : []).some(onPath);
    if ((pageRule === 'only' && !listed) || (pageRule === 'except' && listed)) return;
    if (visual.hide_on_mobile === true && window.innerWidth <= 480) return;

    // Process visual config
    const color = visual.color || '#9d55ac';
    const labelText = String(visual.launcher_label || '').trim().slice(0, 30);
    const labelColor = visual.text_color || '#ffffff';
    const position = visual.position || 'right';
    const showLauncherBg = (visual.show_launcher_bg !== undefined ? visual.show_launcher_bg : visual.showLauncherBg) !== false;
    const launcherShape = visual.launcher_shape || visual.launcherShape || 'circle';
    const showTail = (visual.show_tail !== undefined ? visual.show_tail : visual.showTail) !== false;
    const logoSize = visual.logo_size || visual.logoSize || 32;
    const rightPadding = visual.right_padding !== undefined ? visual.right_padding : (visual.rightPadding !== undefined ? visual.rightPadding : 20);
    const bottomPadding = visual.bottom_padding !== undefined ? visual.bottom_padding : (visual.bottomPadding !== undefined ? visual.bottomPadding : 20);
    const borderRadiusVal = visual.border_radius !== undefined ? visual.border_radius : (visual.borderRadius !== undefined ? visual.borderRadius : 24);
    const clamp = (v, lo, hi, d) => { const n = Number(v); return Number.isFinite(n) && n > 0 ? Math.min(Math.max(n, lo), hi) : d; };
    const windowWidth = clamp(visual.window_width, 320, 480, 400);
    const windowHeight = clamp(visual.window_height, 460, 760, 600);
    // A short message beside the launcher, and opening the chat by itself; both optional.
    const greeting = String(visual.launcher_greeting || '').trim();
    const greetingDelay = clamp(visual.greeting_delay, 0, 60, 3);
    const autoOpenDelay = clamp(visual.auto_open_delay, 1, 120, 0);
    const sideCSS = position === 'left' ? `left: ${rightPadding}px;` : `right: ${rightPadding}px;`;
    
    // Process logo URL logic
    let logoUrl = visual.logo_url || visual.botLogo;
    if (logoUrl && logoUrl.includes('/static/uploads/')) {
        const fileName = logoUrl.split('/').pop();
        logoUrl = `${apiBase}/static/uploads/${fileName}`;
    }

    // Create Container
    const container = document.createElement('div');
    container.id = 'nimmi-widget-container';
    document.body.appendChild(container);

    // Create Shadow DOM
    const shadow = container.attachShadow({ mode: 'closed' });

    // Launcher positioning
    const positionCSS = position === 'left' ? `left: ${rightPadding}px;` : `right: ${rightPadding}px;`;
    const windowPositionCSS = position === 'left' ? `left: ${rightPadding}px;` : `right: ${rightPadding}px;`;
    
    // Launcher shape CSS
    let borderRadius = '50%';
    let width = '60px';
    let height = '60px';
    if (launcherShape === 'square') borderRadius = '0';
    if (launcherShape === 'rounded') borderRadius = '12px';
    if (launcherShape === 'oval') {
        borderRadius = '40px';
        width = '80px';
    }
    
    const bgColor = (showLauncherBg && launcherShape !== 'none') ? color : 'transparent';
    const shadowCSS = (showLauncherBg && launcherShape !== 'none') ? 'box-shadow: 0 4px 20px rgba(0,0,0,0.2);' : '';

    // Tail CSS
    const tailCSS = showTail && !labelText ? `
        #nimmi-launcher::after {
            content: '';
            position: absolute;
            bottom: -6px;
            ${position === 'left' ? 'left: ' + (launcherShape === 'oval' ? '20px' : '10px') : 'right: ' + (launcherShape === 'oval' ? '20px' : '10px')};
            width: 0;
            height: 0;
            border-left: 10px solid transparent;
            border-right: 10px solid transparent;
            border-top: 12px solid ${showLauncherBg ? color : 'transparent'};
            transform: rotate(${position === 'left' ? '15deg' : '-15deg'});
            z-index: -1;
            filter: drop-shadow(0 2px 2px rgba(0,0,0,0.1));
        }
    ` : '';

    // Styles
    const style = document.createElement('style');
    style.textContent = `
        #nimmi-launcher {
            position: fixed;
            bottom: ${bottomPadding}px;
            ${positionCSS}
            width: ${width};
            height: ${height};
            background: ${bgColor};
            border-radius: ${borderRadius};
            ${shadowCSS}
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: transform 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275);
            z-index: 999999;
            box-sizing: border-box;
            border: ${(!showLauncherBg && !logoUrl) ? '1px solid rgba(0,0,0,0.1)' : 'none'};
        }
        #nimmi-launcher:hover {
            transform: scale(1.1);
        }
        #nimmi-launcher.labelled {
            width: auto;
            height: 52px;
            padding: 0 20px 0 14px;
            gap: 8px;
            border-radius: 999px;
            color: ${showLauncherBg ? labelColor : color};
            font: 600 15px/1 system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;
            white-space: nowrap;
        }
        #nimmi-launcher.labelled:hover { transform: translateY(-2px); }
        #nimmi-launcher.labelled img, #nimmi-launcher.labelled svg.fallback { width: 26px; height: 26px; max-width: none; max-height: none; }
        #nimmi-launcher img {
            max-width: 80%;
            max-height: 80%;
            width: ${Math.min(logoSize, 56)}px;
            height: ${Math.min(logoSize, 56)}px;
            object-fit: contain;
            pointer-events: none;
        }
        #nimmi-launcher svg.fallback {
            width: 28px;
            height: 28px;
            fill: ${showLauncherBg ? 'white' : color};
            stroke: ${showLauncherBg ? 'white' : color};
        }
        ${tailCSS}
        #nimmi-chat-window {
            position: fixed;
            bottom: ${bottomPadding + 76}px;
            ${windowPositionCSS}
            width: ${windowWidth}px;
            height: ${windowHeight}px;
            max-height: calc(100vh - ${bottomPadding + 96}px);
            background: white;
            border-radius: ${borderRadiusVal}px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.15);
            overflow: hidden;
            display: none;
            flex-direction: column;
            z-index: 999999;
            border: 1px solid rgba(0,0,0,0.05);
            transition: all 0.3s ease;
            transform: translateY(20px);
            opacity: 0;
        }
        #nimmi-chat-window.open {
            display: flex;
            transform: translateY(0);
            opacity: 1;
        }
        #nimmi-greeting {
            position: fixed;
            bottom: ${bottomPadding + 76}px;
            ${sideCSS}
            max-width: 260px;
            padding: 12px 36px 12px 14px;
            background: #fff;
            color: #1c1917;
            font: 14px/1.45 system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;
            border-radius: 14px;
            border: 1px solid rgba(0,0,0,0.06);
            box-shadow: 0 8px 28px rgba(0,0,0,0.14);
            z-index: 999998;
            cursor: pointer;
            display: none;
            opacity: 0;
            transform: translateY(8px);
            transition: opacity 0.25s ease, transform 0.25s ease;
        }
        #nimmi-greeting.show { opacity: 1; transform: none; }
        #nimmi-greeting button {
            position: absolute; top: 6px; right: 6px; width: 24px; height: 24px;
            border: 0; border-radius: 6px; background: transparent; color: #78716c;
            font-size: 18px; line-height: 1; cursor: pointer;
        }
        #nimmi-greeting button:hover { background: #f5f5f4; color: #1c1917; }
        iframe {
            width: 100%;
            height: 100%;
            border: none;
        }
        @media (max-width: 480px) {
            #nimmi-chat-window {
                width: calc(100% - 40px);
                height: calc(100% - 120px);
                left: ${position === 'left' ? '20px' : 'auto'};
                right: ${position === 'left' ? 'auto' : '20px'};
                bottom: 90px;
            }
        }
    `;
    shadow.appendChild(style);

    // Launcher
    const launcher = document.createElement('div');
    launcher.id = 'nimmi-launcher';
    
    // Built with DOM calls, never HTML strings: the logo URL comes from settings and this runs on the
    // customer's own website, so it must not be able to inject markup or script there.
    const chatIcon = () => {
        const ns = 'http://www.w3.org/2000/svg';
        const svg = document.createElementNS(ns, 'svg');
        svg.setAttribute('class', 'fallback');
        svg.setAttribute('viewBox', '0 0 24 24');
        const path = document.createElementNS(ns, 'path');
        path.setAttribute('d', 'M12 2C6.477 2 2 6.477 2 12c0 1.821.487 3.53 1.338 5L2.5 21.5l4.5-.838A9.955 9.955 0 0012 22c5.523 0 10-4.477 10-10S17.523 2 12 2zm0 18c-1.476 0-2.886-.313-4.156-.872l-2.618.487.487-2.618A7.955 7.955 0 014 12c0-4.411 3.589-8 8-8s8 3.589 8 8-3.589 8-8 8z');
        svg.appendChild(path);
        return svg;
    };
    const safeLogo = (() => {
        try {
            const u = new URL(String(logoUrl || ''), document.baseURI);
            return (u.protocol === 'https:' || u.protocol === 'http:') ? u.href : '';
        } catch (e) { return ''; }
    })();
    if (safeLogo) {
        const img = document.createElement('img');
        img.alt = 'Chat';
        img.src = safeLogo;
        img.addEventListener('error', () => img.replaceWith(chatIcon()), { once: true });
        launcher.appendChild(img);
    } else {
        launcher.appendChild(chatIcon());
    }
    if (labelText) {
        launcher.classList.add('labelled');
        const span = document.createElement('span');
        span.textContent = labelText;
        launcher.appendChild(span);
        launcher.setAttribute('aria-label', labelText);
    }
    shadow.appendChild(launcher);

    // Chat Window
    const chatWindow = document.createElement('div');
    chatWindow.id = 'nimmi-chat-window';
    
    // We use an iframe to host the chat UI to prevent style pollution
    const iframe = document.createElement('iframe');
    // The chat UI lives on the Nimmi dashboard. Don't infer it from the host page: on a
    // customer's site that would never be nimmiai.in.
    const dashboardBase = script.getAttribute('data-dashboard-url')
        || (apiBase.includes('nimmiai.in') ? 'https://nimmiai.in' : 'http://localhost:3000');
        
    const isDemo = script.getAttribute('data-is-demo') === 'true';
    iframe.src = `${dashboardBase}/widget/${botId}?t=` + Date.now() + (isDemo ? '&is_demo=true' : '');
    iframe.setAttribute('allow', 'microphone'); // the chat's mic button (the visitor still has to allow it)
    chatWindow.appendChild(iframe);
    shadow.appendChild(chatWindow);

    // Greeting bubble (text only, never HTML)
    const remember = (key) => { try { sessionStorage.setItem(`${key}_${botId}`, '1'); } catch (e) {} };
    const remembered = (key) => { try { return sessionStorage.getItem(`${key}_${botId}`) === '1'; } catch (e) { return false; } };
    const bubble = document.createElement('div');
    bubble.id = 'nimmi-greeting';
    bubble.setAttribute('role', 'status');
    const bubbleText = document.createElement('span');
    bubbleText.textContent = greeting;
    const bubbleClose = document.createElement('button');
    bubbleClose.type = 'button';
    bubbleClose.setAttribute('aria-label', 'Dismiss');
    bubbleClose.textContent = '×';
    bubble.append(bubbleText, bubbleClose);
    shadow.appendChild(bubble);
    const hideGreeting = () => {
        bubble.classList.remove('show');
        setTimeout(() => { bubble.style.display = 'none'; }, 250);
    };

    // Open and close
    let isOpen = false;
    const setOpen = (open) => {
        isOpen = open;
        if (open) {
            hideGreeting();
            chatWindow.style.display = 'flex';
            setTimeout(() => chatWindow.classList.add('open'), 10);
        } else {
            chatWindow.classList.remove('open');
            setTimeout(() => {
                if (!isOpen) chatWindow.style.display = 'none';
            }, 300);
        }
    };
    launcher.onclick = () => setOpen(!isOpen);
    bubble.onclick = () => setOpen(true);
    bubbleClose.onclick = (e) => { e.stopPropagation(); remember('nimmi_greeting_closed'); hideGreeting(); };

    if (greeting && !remembered('nimmi_greeting_closed')) {
        setTimeout(() => {
            if (isOpen) return;
            bubble.style.display = 'block';
            setTimeout(() => bubble.classList.add('show'), 10);
        }, greetingDelay * 1000);
    }
    // Opening by itself takes over a phone screen, so only on larger screens, once per visit.
    if (autoOpenDelay && window.innerWidth > 480 && !remembered('nimmi_auto_opened')) {
        setTimeout(() => {
            if (isOpen) return;
            remember('nimmi_auto_opened');
            setOpen(true);
        }, autoOpenDelay * 1000);
    }

    // Listen for messages from iframe (e.g. close request), and an "open" request from the host
    // page itself (e.g. an "Open the assistant" button); other frames can't open it.
    window.addEventListener('message', (event) => {
        if (event.data === 'close-nimmi-widget') setOpen(false);
        if (event.data === 'open-nimmi-widget' && event.source === window) setOpen(true);
    });
})();
