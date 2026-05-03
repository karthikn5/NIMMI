(function() {
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

    // Create Container
    const container = document.createElement('div');
    container.id = 'nimmi-widget-container';
    document.body.appendChild(container);

    // Create Shadow DOM
    const shadow = container.attachShadow({ mode: 'closed' });

    // Styles
    const style = document.createElement('style');
    style.textContent = `
        #nimmi-launcher {
            position: fixed;
            bottom: 24px;
            right: 24px;
            width: 60px;
            height: 60px;
            background: #9d55ac;
            border-radius: 50%;
            box-shadow: 0 4px 20px rgba(0,0,0,0.2);
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: transform 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275);
            z-index: 999999;
        }
        #nimmi-launcher:hover {
            transform: scale(1.1);
        }
        #nimmi-launcher svg {
            width: 28px;
            height: 28px;
            fill: white;
        }
        #nimmi-chat-window {
            position: fixed;
            bottom: 100px;
            right: 24px;
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
                right: 20px;
                bottom: 90px;
            }
        }
    `;
    shadow.appendChild(style);

    // Launcher
    const launcher = document.createElement('div');
    launcher.id = 'nimmi-launcher';
    launcher.innerHTML = `<svg viewBox="0 0 24 24"><path d="M12 2C6.477 2 2 6.477 2 12c0 1.821.487 3.53 1.338 5L2.5 21.5l4.5-.838A9.955 9.955 0 0012 22c5.523 0 10-4.477 10-10S17.523 2 12 2zm0 18c-1.476 0-2.886-.313-4.156-.872l-2.618.487.487-2.618A7.955 7.955 0 014 12c0-4.411 3.589-8 8-8s8 3.589 8 8-3.589 8-8 8z"/></svg>`;
    shadow.appendChild(launcher);

    // Chat Window
    const chatWindow = document.createElement('div');
    chatWindow.id = 'nimmi-chat-window';
    
    // We use an iframe to host the chat UI to prevent style pollution
    const iframe = document.createElement('iframe');
    // Using a hosted chat page or a specialized endpoint
    // For now, let's assume we have a /widget/bot_id endpoint or similar
    // Actually, let's just point to a specialized widget URL on the dashboard domain
    const dashboardBase = typeof window !== "undefined" && window.location.hostname.includes("nimmiai.in")
        ? "https://nimmiai.in"
        : "http://localhost:3000";
        
    iframe.src = `${dashboardBase}/widget/${botId}`;
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
