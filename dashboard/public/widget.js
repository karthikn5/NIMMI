(function () {
    const script = document.currentScript;
    const botId = script.getAttribute('data-bot-id');
    const API_BASE = script.getAttribute('data-api-url') || "http://localhost:8000";

    if (!botId) {
        console.error("Nimmi AI: data-bot-id is missing.");
        return;
    }

    // Styles - Load 100+ premium fonts in batches
    const fontBatches = [
        "https://fonts.googleapis.com/css2?family=Inter:wght@400;700&family=Roboto:wght@400;700&family=Open+Sans:wght@400;700&family=Montserrat:wght@400;700&family=Poppins:wght@400;700&family=Lato:wght@400;700&family=Oswald:wght@400;700&family=Raleway:wght@400;700&family=Nunito:wght@400;700&family=Ubuntu:wght@400;700&family=Playfair+Display:wght@400;700&family=Lora:wght@400;700&family=Merriweather:wght@400;700&family=PT+Sans:wght@400;700&family=PT+Serif:wght@400;700&family=Noto+Sans:wght@400;700&family=Noto+Serif:wght@400;700&family=Work+Sans:wght@400;700&family=Fira+Sans:wght@400;700&family=Quicksand:wght@400;700&family=Josefin+Sans:wght@400;700&display=swap",
        "https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Space+Grotesk:wght@400;700&family=Caveat:wght@400;700&family=Lexend:wght@400;700&family=Kanit:wght@400;700&family=Outfit:wght@400;700&family=Syne:wght@400;700&family=Darker+Grotesque:wght@400;700&family=DM+Sans:wght@400;700&family=Manrope:wght@400;700&family=Sora:wght@400;700&family=Urbanist:wght@400;700&family=Figtree:wght@400;700&family=Archivo:wght@400;700&family=Schibsted+Grotesk:wght@400;700&family=Hanken+Grotesk:wght@400;700&family=Bricolage+Grotesque:wght@400;700&family=Young+Serif&family=Instrument+Serif&family=Playpen+Sans&family=Cabin:wght@400;700&display=swap",
        "https://fonts.googleapis.com/css2?family=Arvo:wght@400;700&family=Exo+2:wght@400;700&family=Muli:wght@400;700&family=Titillium+Web:wght@400;700&family=Dosis:wght@400;700&family=Oxygen:wght@400;700&family=Hind:wght@400;700&family=Libre+Baskerville:wght@400;700&family=Anton&family=Karla:wght@400;700&family=Bitter:wght@400;700&family=Varela+Round&family=Crimson+Text:wght@400;700&family=Barlow:wght@400;700&family=Asap:wght@400;700&family=Fjalla+One&family=Pacifico&family=Questrial&family=Assistant:wght@400;700&family=Signika:wght@400;700&display=swap",
        "https://fonts.googleapis.com/css2?family=Alegreya:wght@400;700&family=Alegreya+Sans:wght@400;700&family=Righteous&family=Patua+One&family=Comfortaa:wght@400;700&family=Lobster&family=Dancing+Script:wght@400;700&family=Kaushan+Script&family=Satisfy&family=Great+Vibes&family=Sacramento&family=Yellowtail&family=Cookie&family=Tangerine&family=Special+Elite&family=Luckiest+Guy&family=Bangers&family=Press+Start+2P&family=VT323&display=swap",
        "https://fonts.googleapis.com/css2?family=Nanum+Gothic:wght@400;700&family=Cairo:wght@400;700&family=Mukta:wght@400;700&family=Heebo:wght@400;700&family=Prompt:wght@400;700&family=Spectral:wght@400;700&family=Cardo:wght@400;700&family=Crimson+Pro:wght@400;700&family=Eczar:wght@400;700&family=Domine:wght@400;700&family=Old+Standard+TT:wght@400;700&family=Cormorant:wght@400;700&family=Prata&family=Marcellus&family=Josefin+Slab:wght@400;700&family=BioRhyme:wght@400;700&family=Chivo:wght@400;700&family=Overpass:wght@400;700&family=Public+Sans:wght@400;700&family=Fraunces:wght@400;700&family=Besley:wght@400;700&family=Casta&family=Delius&family=Neucha&display=swap"
    ];

    fontBatches.forEach(url => {
        const link = document.createElement('link');
        link.rel = 'stylesheet';
        link.href = url;
        document.head.appendChild(link);
    });

    const style = document.createElement('style');
    style.innerHTML = `
        #nimmi-widget-container {
            position: fixed;
            bottom: 20px;
            z-index: 9999;
            font-family: inherit;
        }
        #nimmi-bubble {
            width: 60px;
            height: 60px;
            border-radius: 50%;
            background: #3b82f6;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            transition: transform 0.2s;
        }
        #nimmi-bubble:hover { transform: scale(1.1); }
        #nimmi-chat-window {
            position: absolute;
            bottom: 80px;
            width: 380px;
            height: 600px;
            background: #ffffff;
            border-radius: 24px;
            box-shadow: 0 20px 50px rgba(0,0,0,0.15);
            display: none;
            flex-direction: column;
            overflow: hidden;
            border: 1px solid rgba(0,0,0,0.1);
        }
        #nimmi-chat-bg {
            position: absolute;
            inset: 0;
            z-index: 0;
            pointer-events: none;
            background-size: cover;
            background-position: center;
        }
        #nimmi-chat-messages {
            flex: 1;
            padding: 24px;
            overflow-y: auto;
            display: flex;
            flex-direction: column;
            gap: 16px;
            z-index: 10;
            position: relative;
        }
        #nimmi-chat-input-area {
            padding: 16px;
            background: #ffffff;
            border-top: 1px solid rgba(0,0,0,0.05);
            display: flex;
            gap: 8px;
            align-items: center;
            position: relative;
            z-index: 10;
            box-shadow: 0 -2px 10px rgba(0,0,0,0.05);
        }
        #nimmi-chat-input {
            flex: 1;
            border: 1px solid rgba(0,0,0,0.1);
            border-radius: 12px;
            height: 48px;
            padding: 0 16px;
            outline: none;
            font-size: 14px;
            transition: border-color 0.2s;
        }
        #nimmi-chat-input:focus {
            border-color: #3b82f6;
        }
        #nimmi-chat-send {
            width: 48px;
            height: 48px;
            border: none;
            border-radius: 12px;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
            transition: transform 0.2s, opacity 0.2s;
        }
        #nimmi-chat-send:hover { opacity: 0.9; transform: scale(1.05); }
        #nimmi-chat-send:active { transform: scale(0.95); }
    `;
    document.head.appendChild(style);

    // Initialize when DOM is ready
    const init = () => {
        // Container
        const container = document.createElement('div');
        container.id = "nimmi-widget-container";
        document.body.appendChild(container);

        loadConfig(container);
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    function loadConfig(container) {
        // Fetch Config
        fetch(`${API_BASE}/api/bots/${botId}/config`)
            .then(res => res.json())
            .then(config => {
                const { visual_config, bot_name } = config;
                const {
                    position = 'right',
                    color = '#3b82f6',
                    font_family = 'sans-serif',
                    text_color = '#ffffff',
                    input_bg_color = '#ffffff',
                    input_text_color = '#000000',
                    user_bubble_bg = '#3b82f6',
                    user_bubble_text = '#ffffff',
                    assistant_bubble_bg = '#e5e7eb',
                    assistant_bubble_text = '#000000',
                    chat_bg_color = '#f9fafb',
                    header_height = 80,
                    border_radius = 24,
                    launcher_shape = 'circle',
                    show_tail = true,
                    show_launcher_bg = true,
                    logo_size = 32,
                    right_padding = 20,
                    bottom_padding = 20,
                    background_image = '',
                    background_opacity = 1

                } = visual_config;

                const { nodes = [], edges = [] } = config.flow_data || {};
                let currentNodeId = null;
                let flowActive = nodes.length > 0;
                const variables = {};

                // Session ID management
                let visitorSessionId = localStorage.getItem('nimmi_session_id');
                if (!visitorSessionId) {
                    visitorSessionId = 'v' + Math.random().toString(36).substring(2, 10);
                    localStorage.setItem('nimmi_session_id', visitorSessionId);
                }

                container.style.right = position === 'right' ? `${right_padding}px` : 'auto';
                container.style.left = position === 'left' ? `${right_padding}px` : 'auto';
                container.style.bottom = `${bottom_padding}px`;
                container.style.fontFamily = font_family;

                const msg = `
                <div id="nimmi-chat-window">
                    <div id="nimmi-chat-header" style="position: relative; z-index: 10;">
                        <div style="display: flex; align-items: center; gap: 12px;">
                            <div id="nimmi-header-logo" style="width: 40px; height: 40px; background: rgba(255,255,255,0.2); border-radius: 12px; display: flex; align-items: center; justify-content: center; overflow: hidden; flex-shrink: 0;">
                                ${visual_config.logo_url ? `<img src="${visual_config.logo_url}" style="width: 100%; height: 100%; object-fit: cover;">` : `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="10" rx="2"></rect><circle cx="12" cy="5" r="2"></circle><path d="M12 7v4"></path><line x1="8" y1="16" x2="8" y2="16"></line><line x1="16" y1="16" x2="16" y2="16"></line></svg>`}
                            </div>
                            <span>${bot_name}</span>
                        </div>
                        <span id="nimmi-close" style="cursor:pointer; font-size: 24px; opacity: 0.7;">×</span>
                    </div>
                    <div id="nimmi-chat-messages">
                        ${background_image ? `<div id="nimmi-chat-bg" style="background-image: url('${background_image}'); opacity: ${background_opacity};"></div>` : ''}
                    </div>
                    <div id="nimmi-chat-input-area">
                        <input type="text" id="nimmi-chat-input" placeholder="Type a message...">
                        <button id="nimmi-chat-send">
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg>
                        </button>
                    </div>
                </div>
                <div id="nimmi-bubble-container" style="position:relative">
                    <div id="nimmi-bubble">
                        ${visual_config.logo_url ?
                        `<img src="${visual_config.logo_url}" style="width: ${logo_size}px; height: ${logo_size}px; object-fit: contain;">` :
                        `<svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>`
                    }
                    </div>
                </div>
            `;
                container.innerHTML = msg;

                const bubble = document.getElementById('nimmi-bubble');
                const window = document.getElementById('nimmi-chat-window');
                const close = document.getElementById('nimmi-close');
                const input = document.getElementById('nimmi-chat-input');
                const send = document.getElementById('nimmi-chat-send');
                const messages = document.getElementById('nimmi-chat-messages');

                messages.style.background = chat_bg_color;
                bubble.style.background = (show_launcher_bg && launcher_shape !== 'none') ? color : 'transparent';
                bubble.style.boxShadow = (show_launcher_bg && launcher_shape !== 'none') ? '0 4px 12px rgba(0,0,0,0.15)' : 'none';
                const header = document.getElementById('nimmi-chat-header');
                header.style.background = color;
                header.style.color = text_color;
                header.style.height = `${header_height}px`;
                header.style.display = 'flex';
                header.style.alignItems = 'center';
                header.style.boxShadow = '0 2px 10px rgba(0,0,0,0.1)';

                window.style.borderRadius = `${border_radius * 1.5}px`;

                send.style.background = color;
                send.style.color = text_color;

                // Launcher Shape Styles
                bubble.style.width = '60px'; // Reset
                if (launcher_shape === 'square') bubble.style.borderRadius = '0';
                else if (launcher_shape === 'rounded') bubble.style.borderRadius = '12px';
                else if (launcher_shape === 'oval') {
                    bubble.style.borderRadius = '40px';
                    bubble.style.width = '80px';
                } else {
                    bubble.style.borderRadius = '50%';
                }

                const existingTail = document.getElementById('nimmi-bubble-tail');
                if (existingTail) existingTail.remove();

                if (show_tail && launcher_shape !== 'none') {
                    const tail = document.createElement('div');
                    tail.id = 'nimmi-bubble-tail';
                    tail.style.position = 'absolute';
                    tail.style.width = '0';
                    tail.style.height = '0';
                    tail.style.borderLeft = '10px solid transparent';
                    tail.style.borderRight = '10px solid transparent';
                    tail.style.borderTop = `12px solid ${(show_launcher_bg && launcher_shape !== 'none') ? color : 'transparent'}`;
                    tail.style.bottom = '-8px';
                    tail.style.right = launcher_shape === 'oval' ? '20px' : '10px';
                    tail.style.transform = 'rotate(-15deg)';
                    document.getElementById('nimmi-bubble-container').appendChild(tail);
                }

                const inputElement = document.getElementById('nimmi-chat-input');
                inputElement.style.background = input_bg_color;
                inputElement.style.color = input_text_color;

                bubble.onclick = () => window.style.display = window.style.display === 'flex' ? 'none' : 'flex';
                close.onclick = () => window.style.display = 'none';

                // Alignment Fix: Ensure window stays on screen
                window.style.right = visual_config.position === 'right' ? '0' : 'auto';
                window.style.left = visual_config.position === 'left' ? '0' : 'auto';

                const addMessage = (content, role, isHtml = false) => {
                    const div = document.createElement('div');
                    div.style.marginBottom = '10px';
                    div.style.textAlign = role === 'user' ? 'right' : 'left';
                    div.style.position = 'relative';
                    div.style.zIndex = '10';
                    const bg = role === 'user' ? user_bubble_bg : assistant_bubble_bg;
                    const txt = role === 'user' ? user_bubble_text : assistant_bubble_text;

                    const inner = document.createElement('div');
                    inner.style.display = 'inline-block';
                    inner.style.padding = '12px 16px';
                    inner.style.fontSize = '14px';
                    inner.style.lineHeight = '1.5';
                    inner.style.borderRadius = `${border_radius}px`;
                    if (role === 'user') inner.style.borderTopRightRadius = '0';
                    else inner.style.borderTopLeftRadius = '0';
                    inner.style.background = bg;
                    inner.style.color = txt;
                    inner.style.maxWidth = '85%';
                    inner.style.wordBreak = 'break-word';

                    if (isHtml) inner.innerHTML = content;
                    else inner.innerText = content;

                    div.appendChild(inner);
                    messages.appendChild(div);
                    messages.scrollTop = messages.scrollHeight;
                    return div;
                };

                const addOptions = (options, onSelect) => {
                    const div = document.createElement('div');
                    div.style.marginBottom = '10px';
                    div.style.display = 'flex';
                    div.style.flexWrap = 'wrap';
                    div.style.gap = '5px';
                    div.style.position = 'relative';
                    div.style.zIndex = '10';

                    options.forEach(opt => {
                        const btn = document.createElement('button');
                        btn.innerText = opt;
                        btn.style.padding = '6px 12px';
                        btn.style.borderRadius = '20px';
                        btn.style.border = `1px solid ${color}`;
                        btn.style.background = 'transparent';
                        btn.style.color = color;
                        btn.style.cursor = 'pointer';
                        btn.style.fontSize = '12px';
                        btn.style.fontFamily = font_family;
                        btn.onclick = () => {
                            div.remove();
                            addMessage(opt, 'user');
                            onSelect(opt);
                        };
                        div.appendChild(btn);
                    });
                    messages.appendChild(div);
                    messages.scrollTop = messages.scrollHeight;
                };

                const addRating = (onSelect) => {
                    const div = document.createElement('div');
                    div.style.marginBottom = '10px';
                    div.style.display = 'flex';
                    div.style.gap = '8px';
                    div.style.position = 'relative';
                    div.style.zIndex = '10';

                    for (let i = 1; i <= 5; i++) {
                        const btn = document.createElement('button');
                        btn.innerText = i;
                        btn.style.width = '36px';
                        btn.style.height = '36px';
                        btn.style.borderRadius = '50%';
                        btn.style.border = `1px solid ${color}`;
                        btn.style.background = 'transparent';
                        btn.style.color = color;
                        btn.style.cursor = 'pointer';
                        btn.onclick = () => {
                            div.remove();
                            addMessage(String(i), 'user');
                            onSelect(i);
                        };
                        div.appendChild(btn);
                    }
                    messages.appendChild(div);
                    messages.scrollTop = messages.scrollHeight;
                };

                const addFileLink = (onSelect) => {
                    const div = document.createElement('div');
                    div.style.marginBottom = '10px';
                    div.style.position = 'relative';
                    div.style.zIndex = '10';

                    const input = document.createElement('input');
                    input.type = 'file';
                    input.style.display = 'none';
                    input.onchange = (e) => {
                        const file = e.target.files[0];
                        if (file) {
                            addMessage(`Uploaded: ${file.name}`, 'user');
                            onSelect(file.name);
                        }
                    };

                    const btn = document.createElement('button');
                    btn.innerText = "Upload File";
                    btn.style.padding = '8px 16px';
                    btn.style.borderRadius = '12px';
                    btn.style.background = color;
                    btn.style.color = text_color;
                    btn.style.border = 'none';
                    btn.style.cursor = 'pointer';
                    btn.onclick = () => input.click();

                    div.appendChild(input);
                    div.appendChild(btn);
                    messages.appendChild(div);
                    messages.scrollTop = messages.scrollHeight;
                };

                const getNextNode = (nodeId, sourceHandle = null) => {
                    const edge = edges.find(e =>
                        e.source === nodeId && (!sourceHandle || e.sourceHandle === sourceHandle)
                    );
                    return edge ? nodes.find(n => n.id === edge.target) : null;
                };

                const setVariable = (node, value) => {
                    const name = node.data.variableName || node.data.label || node.id;
                    variables[name] = value;
                    console.log(`Nimmi AI: Set variable "${name}" to "${value}"`);

                    fetch(`${API_BASE}/api/chat/variables`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            bot_id: botId,
                            visitor_session_id: visitorSessionId,
                            variable_name: name,
                            variable_value: String(value)
                        })
                    }).catch(e => console.error("Nimmi AI: Capture failed", e));
                };

                const evaluateCondition = (node) => {
                    const { variable, operator, value } = node.data;
                    const actualValue = variables[variable] || "";
                    console.log(`Nimmi AI: Evaluating condition "${variable}" ${operator} "${value}" (Actual: "${actualValue}")`);

                    switch (operator) {
                        case 'equals': return String(actualValue) === String(value);
                        case 'contains': return String(actualValue).includes(String(value));
                        case 'greater_than': return Number(actualValue) > Number(value);
                        case 'less_than': return Number(actualValue) < Number(value);
                        default: return false;
                    }
                };

                const processNode = (node) => {
                    if (!node) return;
                    currentNodeId = node.id;

                    switch (node.type) {
                        case 'start':
                            processNode(getNextNode(node.id));
                            break;
                        case 'message':
                            addMessage(node.data.message || "...", 'assistant');
                            setTimeout(() => processNode(getNextNode(node.id)), 600);
                            break;
                        case 'image':
                            addMessage(`<img src="${node.data.imageUrl}" style="width:100%; border-radius:12px;">`, 'assistant', true);
                            setTimeout(() => processNode(getNextNode(node.id)), 600);
                            break;
                        case 'video':
                            addMessage(`<video src="${node.data.videoUrl}" controls style="width:100%; border-radius:12px;"></video>`, 'assistant', true);
                            setTimeout(() => processNode(getNextNode(node.id)), 600);
                            break;
                        case 'multipleChoice':
                            addMessage(node.data.message || "Please choose an option:", 'assistant');
                            addOptions(node.data.options || [], (choice) => {
                                setVariable(node, choice);
                                processNode(getNextNode(node.id));
                            });
                            break;
                        case 'rating':
                            addMessage(node.data.message || "Rate your experience:", 'assistant');
                            addRating((val) => {
                                setVariable(node, val);
                                processNode(getNextNode(node.id));
                            });
                            break;
                        case 'fileUpload':
                            addMessage(node.data.message || "Please upload a file:", 'assistant');
                            addFileLink((fileName) => {
                                setVariable(node, fileName);
                                processNode(getNextNode(node.id));
                            });
                            break;
                        case 'textInput':
                        case 'emailInput':
                        case 'numberInput':
                        case 'phoneInput':
                        case 'datePicker':
                            addMessage(node.data.message || node.data.label || "Please provide input:", 'assistant');
                            input.placeholder = node.data.placeholder || (node.type === 'numberInput' ? "Enter a number..." : "Type here...");
                            input.type = node.type === 'numberInput' ? 'number' : 'text';
                            break;
                        case 'delay':
                            const ms = (node.data.delayTime || 2) * 1000;
                            setTimeout(() => processNode(getNextNode(node.id)), ms);
                            break;
                        case 'variable':
                            setVariable({ ...node, data: { ...node.data, label: node.data.variableName } }, node.data.variableValue);
                            processNode(getNextNode(node.id));
                            break;
                        case 'condition':
                            const result = evaluateCondition(node);
                            processNode(getNextNode(node.id, result ? 'true' : 'false'));
                            break;
                        case 'aiPrompt':
                            addMessage("...", 'assistant'); // Typing indicator placeholder
                            fetch(`${API_BASE}/api/chat/ai-prompt`, {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({
                                    bot_id: botId,
                                    prompt: node.data.systemPrompt,
                                    visitor_session_id: visitorSessionId
                                })
                            }).then(res => res.json())
                                .then(data => {
                                    messages.lastChild.remove(); // Remove thinking indicator
                                    addMessage(data.answer, 'assistant');
                                    setVariable(node, data.answer);
                                    processNode(getNextNode(node.id));
                                });
                            break;
                        case 'httpRequest':
                            fetch(`${API_BASE}/api/chat/proxy-http`, {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({
                                    url: node.data.url,
                                    method: node.data.method,
                                    body: {} // Simplify for now
                                })
                            }).then(res => res.json())
                                .then(data => {
                                    setVariable(node, JSON.stringify(data.data));
                                    processNode(getNextNode(node.id));
                                });
                            break;
                        case 'webhook':
                            fetch(`${API_BASE}/api/chat/proxy-http`, {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({
                                    url: node.data.url,
                                    method: 'POST',
                                    body: variables // Send all captured variables
                                })
                            }).then(() => {
                                processNode(getNextNode(node.id));
                            });
                            break;
                        case 'slack':
                            // Format variables for Slack
                            let slackText = `*New Lead captured!* \n\n`;
                            for (const [key, val] of Object.entries(variables)) {
                                if (key !== 'bot_id' && key !== 'session_id') {
                                    slackText += `*${key}*: ${val}\n`;
                                }
                            }

                            fetch(`${API_BASE}/api/chat/proxy-http`, {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({
                                    url: node.data.url,
                                    method: 'POST',
                                    body: {
                                        text: slackText,
                                        channel: node.data.channel || undefined
                                    }
                                })
                            }).then(() => {
                                processNode(getNextNode(node.id));
                            });
                            break;
                        case 'googleSheets':
                            fetch(`${API_BASE}/api/integrations/google-sheets`, {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({
                                    bot_id: botId,
                                    spreadsheet_id: node.data.spreadsheetId,
                                    sheet_name: node.data.sheetName,
                                    data: variables
                                })
                            }).then(() => {
                                processNode(getNextNode(node.id));
                            });
                            break;
                        case 'end':
                            addMessage(node.data.message || "Thank you!", 'assistant');
                            flowActive = false;
                            input.disabled = true;
                            send.disabled = true;
                            break;
                        default:
                            processNode(getNextNode(node.id));
                    }
                };

                if (flowActive) {
                    const startNode = nodes.find(n => n.type === 'start') || nodes[0];
                    processNode(startNode);
                }

                const sendMessage = () => {
                    const text = input.value.trim();
                    if (!text) return;
                    addMessage(text, 'user');
                    input.value = '';

                    fetch(`${API_BASE}/api/chat/message`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            bot_id: botId,
                            message: text,
                            visitor_session_id: visitorSessionId,
                            history: []
                        })
                    })
                        .then(res => res.json())
                        .then(data => {
                            addMessage(data.answer, 'assistant');
                        });
                };

                const handleUserInput = () => {
                    const text = input.value.trim();
                    if (!text) return;

                    if (flowActive) {
                        const currentNode = nodes.find(n => n.id === currentNodeId);
                        if (currentNode && ['textInput', 'emailInput', 'numberInput', 'phoneInput', 'datePicker'].includes(currentNode.type)) {
                            addMessage(text, 'user');
                            setVariable(currentNode, text);
                            input.value = '';
                            input.placeholder = "Type a message...";
                            processNode(getNextNode(currentNode.id));
                        } else {
                            // If flow is active but we're not at an input node, fallback to chat or ignore?
                            // For now, let's allow fallback chat if flow gets stuck
                            sendMessage();
                        }
                    } else {
                        sendMessage();
                    }
                };

                send.onclick = handleUserInput;
                input.onkeypress = (e) => { if (e.key === 'Enter') handleUserInput(); };
            });
    }
})();
