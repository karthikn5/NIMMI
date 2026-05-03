(async function() {
    // Prevent multiple initializations
    if (window.__NIMMI_WIDGET_LOADED__) return;
    window.__NIMMI_WIDGET_LOADED__ = true;

    // Configuration
    const script = document.currentScript || (function() {
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

    // Process visual config
    const color = visual.color || '#9d55ac';
    const position = visual.position || 'right';
    const showLauncherBg = (visual.show_launcher_bg !== undefined ? visual.show_launcher_bg : visual.showLauncherBg) !== false;
    const launcherShape = visual.launcher_shape || visual.launcherShape || 'circle';
    const showTail = (visual.show_tail !== undefined ? visual.show_tail : visual.showTail) !== false;
    const logoSize = visual.logo_size || visual.logoSize || 32;
    
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
    const positionCSS = position === 'left' ? 'left: 24px;' : 'right: 24px;';
    const windowPositionCSS = position === 'left' ? 'left: 24px;' : 'right: 24px;';
    
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
    const tailCSS = showTail ? `
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
            bottom: 24px;
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
        #nimmi-launcher img {
            width: ${logoSize}px;
            height: ${logoSize}px;
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
            bottom: 100px;
            ${windowPositionCSS}
            width: 400px;
            height: 600px;
            background: white;
            border-radius: 24px;
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
    
    if (logoUrl) {
        launcher.innerHTML = `<img src="${logoUrl}" alt="Chat" onerror="this.outerHTML='<svg class=\\'fallback\\' viewBox=\\'0 0 24 24\\'><path d=\\'M12 2C6.477 2 2 6.477 2 12c0 1.821.487 3.53 1.338 5L2.5 21.5l4.5-.838A9.955 9.955 0 0012 22c5.523 0 10-4.477 10-10S17.523 2 12 2zm0 18c-1.476 0-2.886-.313-4.156-.872l-2.618.487.487-2.618A7.955 7.955 0 014 12c0-4.411 3.589-8 8-8s8 3.589 8 8-3.589 8-8 8z\\'/></svg>'" />`;
    } else {
        launcher.innerHTML = `<svg class="fallback" viewBox="0 0 24 24"><path d="M12 2C6.477 2 2 6.477 2 12c0 1.821.487 3.53 1.338 5L2.5 21.5l4.5-.838A9.955 9.955 0 0012 22c5.523 0 10-4.477 10-10S17.523 2 12 2zm0 18c-1.476 0-2.886-.313-4.156-.872l-2.618.487.487-2.618A7.955 7.955 0 014 12c0-4.411 3.589-8 8-8s8 3.589 8 8-3.589 8-8 8z"/></svg>`;
    }
    shadow.appendChild(launcher);

    // Chat Window
    const chatWindow = document.createElement('div');
    chatWindow.id = 'nimmi-chat-window';
    
    // We use an iframe to host the chat UI to prevent style pollution
    const iframe = document.createElement('iframe');
    const dashboardBase = typeof window !== "undefined" && window.location.hostname.includes("nimmiai.in")
        ? "https://nimmiai.in"
        : "http://localhost:3000";
        
    iframe.src = `${dashboardBase}/widget/${botId}?t=` + Date.now();
    chatWindow.appendChild(iframe);
    shadow.appendChild(chatWindow);

    // Toggle Logic
    let isOpen = false;
    launcher.onclick = () => {
        isOpen = !isOpen;
        if (isOpen) {
            chatWindow.style.display = 'flex';
            setTimeout(() => chatWindow.classList.add('open'), 10);
        } else {
            chatWindow.classList.remove('open');
            setTimeout(() => {
                if (!isOpen) chatWindow.style.display = 'none';
            }, 300);
        }
    };

    // Listen for messages from iframe (e.g. close request)
    window.addEventListener('message', (event) => {
        if (event.data === 'close-nimmi-widget') {
            launcher.click();
        }
    });
})();
