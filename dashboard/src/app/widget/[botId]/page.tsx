"use client";

import { use, useCallback, useEffect, useRef, useState, Suspense } from "react";
import { authHeaders } from "@/lib/api";
import { Send, User, Bot, X, Clock, Paperclip, Phone } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { io, type Socket } from "socket.io-client";
import { motion, AnimatePresence } from "framer-motion";
import { Flow, evaluate, questionFor, validate, variableName, type FlowNode, type InputType } from "./flow";

interface Message {
    id: string;
    text: string;
    sender: "user" | "bot";
    timestamp: Date;
    media?: { type: "image" | "video"; url: string };
}

/** What the visitor is being asked right now by the flow. */
type Pending =
    | { kind: "input"; node: FlowNode; type: InputType }
    | { kind: "choices"; node: FlowNode; options: string[] }
    | { kind: "rating"; node: FlowNode; scale: number }
    | { kind: "file"; node: FlowNode }
    | { kind: "callback"; node: FlowNode; phone: string };

const CALL_YES = "Yes, call me";
const CALL_NO = "No, thanks";

/** A stable id for this visitor and assistant, so each visitor gets their own conversation. */
function visitorId(botId: string) {
    const key = `nimmi_visitor_${botId}`;
    try {
        let id = localStorage.getItem(key);
        if (!id) {
            id = `${botId.slice(0, 8)}-${crypto.randomUUID()}`;
            localStorage.setItem(key, id);
        }
        return id;
    } catch {
        return `${botId.slice(0, 8)}-${Math.random().toString(36).slice(2)}`;
    }
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const uid = () => `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;

function WidgetContent({ params }: { params: Promise<{ botId: string }> }) {
    const { botId } = use(params);
    const searchParams = useSearchParams();
    const isDemo = searchParams.get("is_demo") === "true";
    const [aiMessages, setAiMessages] = useState<Message[]>([]);
    const [humanMessages, setHumanMessages] = useState<Message[]>([]);
    const [input, setInput] = useState("");
    const [loading, setLoading] = useState(false);
    const [mode, setMode] = useState<"ai" | "human">("ai");
    const [botConfig, setBotConfig] = useState<any>(null);
    const [pending, setPending] = useState<Pending | null>(null);
    const [callback, setCallback] = useState<{ open: boolean; phone: string; consent: boolean; state: "idle" | "sending" | "done" | "error"; error: string }>(
        { open: false, phone: "", consent: false, state: "idle", error: "" });
    const socketRef = useRef<Socket | null>(null);
    const messagesEndRef = useRef<HTMLDivElement>(null);
    const fileRef = useRef<HTMLInputElement>(null);
    const flowRef = useRef<Flow | null>(null);
    const varsRef = useRef<Record<string, string>>({});
    const flowStarted = useRef(false);

    const apiBase = typeof window !== "undefined" && (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1")
        ? "http://localhost:8000"
        : "https://api.nimmiai.in";
    const aiSession = "widget-session-ai-" + visitorId(botId);
    const humanSession = "widget-session-human-" + visitorId(botId);
    const demoHeaders = isDemo ? authHeaders() : {};

    const messages = mode === "ai" ? aiMessages : humanMessages;

    const say = useCallback((text: string, media?: Message["media"]) => {
        setAiMessages((prev) => [...prev, { id: uid(), text, sender: "bot", timestamp: new Date(), media }]);
    }, []);
    const echo = (text: string) => setAiMessages((prev) => [...prev, { id: uid(), text, sender: "user", timestamp: new Date() }]);

    const addHumanMessageSafely = (newMsg: Message) => {
        setHumanMessages((prev) => (prev.some((m) => m.id === newMsg.id) ? prev : [...prev, newMsg]));
    };

    // ── Human handoff ──────────────────────────────────────────────
    const goHuman = useCallback(async (note?: string) => {
        setMode("human");
        setPending(null);
        try {
            const res = await fetch(`${apiBase}/api/chat/handoff`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ bot_id: botId, visitor_session_id: humanSession }),
            });
            // Give the agent what the flow already collected.
            await Promise.all(Object.entries(varsRef.current).map(([k, v]) => fetch(`${apiBase}/api/chat/variables`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ bot_id: botId, visitor_session_id: humanSession, variable_name: k, variable_value: v }),
            }).catch(() => {})));
            if (res.ok) {
                const body = await res.json().catch(() => ({}));
                setHumanMessages((prev) => prev.length ? prev : [{
                    id: uid(), sender: "bot", timestamp: new Date(),
                    text: body.away ? body.message : (note || "We've let our team know. Someone will join this chat shortly."),
                }]);
            }
            socketRef.current?.emit("join", { room: humanSession });
        } catch (err) {
            console.error("Handoff request failed:", err);
        }
    }, [apiBase, botId, humanSession]);

    const handleModeToggle = (newMode: "ai" | "human") => {
        if (newMode === mode) return;
        if (newMode === "human") goHuman();
        else setMode("ai");
    };

    // ── Flow runner ────────────────────────────────────────────────
    const saveVar = useCallback((name: string, value: string) => {
        varsRef.current[name] = value;
        fetch(`${apiBase}/api/chat/variables`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ bot_id: botId, visitor_session_id: aiSession, variable_name: name, variable_value: value }),
        }).catch(() => {});
    }, [apiBase, botId, aiSession]);

    const proxy = (url: string, method: string, body: Record<string, unknown>) => fetch(`${apiBase}/api/chat/proxy-http`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url, method, body }),
    }).then((r) => r.json()).catch(() => ({}));

    const run = useCallback(async (node: FlowNode | null): Promise<void> => {
        const flow = flowRef.current;
        if (!node || !flow) { setPending(null); return; } // flow finished: free chat with the assistant
        const d = node.data || {};
        switch (node.type) {
            case "message":
                await sleep(500);
                if (d.message) say(String(d.message));
                return run(flow.next(node.id));
            case "image":
            case "video": {
                const url = node.type === "image" ? d.imageUrl : d.videoUrl;
                if (url) { await sleep(400); say("", { type: node.type, url }); }
                return run(flow.next(node.id));
            }
            case "multipleChoice":
                await sleep(400);
                say(questionFor(node));
                setPending({ kind: "choices", node, options: (d.options || []).filter(Boolean) });
                return;
            case "rating":
                await sleep(400);
                say(questionFor(node));
                setPending({ kind: "rating", node, scale: Number(d.scale) || 5 });
                return;
            case "fileUpload":
                await sleep(400);
                say(questionFor(node));
                setPending({ kind: "file", node });
                return;
            case "textInput":
            case "emailInput":
            case "numberInput":
            case "phoneInput":
            case "datePicker":
                await sleep(400);
                say(questionFor(node));
                setPending({ kind: "input", node, type: node.type as InputType });
                return;
            case "delay":
                await sleep(Math.min(Number(d.delay ?? d.delayTime ?? 2), 60) * 1000);
                return run(flow.next(node.id));
            case "variable":
                if (d.variableName) saveVar(String(d.variableName), String(d.variableValue ?? ""));
                return run(flow.next(node.id));
            case "condition":
                return run(flow.next(node.id, evaluate(node, varsRef.current) ? "true" : "false"));
            case "aiPrompt": {
                setLoading(true);
                try {
                    const res = await fetch(`${apiBase}/api/chat/ai-prompt`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json", ...demoHeaders },
                        body: JSON.stringify({ bot_id: botId, prompt: d.prompt || d.systemPrompt || "", visitor_session_id: aiSession,
                                               context: Object.entries(varsRef.current).map(([k, v]) => `${k}: ${v}`).join("\n") }),
                    });
                    const { answer } = await res.json();
                    if (answer) { say(answer); saveVar(variableName(node), answer); }
                } catch { /* keep going without the AI step */ }
                setLoading(false);
                return run(flow.next(node.id));
            }
            case "httpRequest": {
                const res = await proxy(d.url, d.method || "POST", varsRef.current);
                if (res?.data !== undefined) saveVar(variableName(node), typeof res.data === "string" ? res.data : JSON.stringify(res.data));
                return run(flow.next(node.id));
            }
            case "webhook":
                await proxy(d.url, "POST", varsRef.current);
                return run(flow.next(node.id));
            case "slack": {
                const lines = Object.entries(varsRef.current).map(([k, v]) => `*${k}*: ${v}`).join("\n");
                await proxy(d.url, "POST", { text: `*New lead from ${botConfig?.bot_name ?? "your assistant"}*\n\n${lines}`, channel: d.channel || undefined });
                return run(flow.next(node.id));
            }
            case "googleSheets":
                await fetch(`${apiBase}/api/integrations/google-sheets`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ bot_id: botId, spreadsheet_id: d.spreadsheetId, sheet_name: d.sheetName || "Sheet1", data: varsRef.current }),
                }).catch(() => {});
                return run(flow.next(node.id));
            case "handover":
                await sleep(400);
                say(d.message || "Connecting you to a person now.");
                await sleep(800);
                return goHuman(d.message);
            case "end":
                await sleep(400);
                say(d.message || "Thank you!");
                setPending(null);
                return;
            default: // start and anything unknown: just move on
                return run(flow.next(node.id));
        }
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [apiBase, botId, aiSession, botConfig, goHuman, say, saveVar]);

    /** The visitor answered the current flow question. */
    const answer = async (value: string) => {
        const p = pending;
        const flow = flowRef.current;
        if (!p || !flow) return;
        echo(value);

        if (p.kind === "input") {
            const problem = validate(p.type, value);
            if (problem) { say(problem); return; }
            setPending(null);
            saveVar(variableName(p.node), value.trim());
            // A phone number is the moment to offer a call, if the business takes callbacks.
            if (p.type === "phoneInput" && botConfig?.callbacks_enabled && p.node.data?.offerCallback !== false) {
                await sleep(400);
                say(`Would you like us to call you on ${value.trim()} now? The call may be recorded.`);
                setPending({ kind: "callback", node: p.node, phone: value.trim() });
                return;
            }
            return run(flow.next(p.node.id));
        }
        if (p.kind === "callback") {
            setPending(null);
            if (value === CALL_YES) {
                try {
                    const res = await fetch(`${apiBase}/api/voice/callbacks/request`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ bot_id: botId, phone: p.phone, consent: true, name: varsRef.current.name, session_id: aiSession }),
                    });
                    const body = await res.json().catch(() => ({}));
                    say(res.ok ? "Done. We'll call you shortly." : (body.detail || "We couldn't schedule the call, but our team has your number."));
                } catch {
                    say("We couldn't schedule the call, but our team has your number.");
                }
            }
            return run(flow.next(p.node.id));
        }
        setPending(null);
        saveVar(variableName(p.node), value);
        return run(flow.next(p.node.id, value));
    };

    // ── Setup: socket for human chat, config, flow ─────────────────
    useEffect(() => {
        const socket = io(apiBase, { transports: ["websocket"], upgrade: false });
        socketRef.current = socket;
        socket.on("connect", () => socket.emit("join", { room: humanSession }));
        socket.on("agent_joined", () => {
            addHumanMessageSafely({ id: `system-agent-joined-${Date.now()}`, text: "A person from our team has joined the chat.", sender: "bot", timestamp: new Date() });
        });
        socket.on("message", (data: any) => {
            if (data.sender === "agent") addHumanMessageSafely({ id: uid(), text: data.message, sender: "bot", timestamp: new Date() });
        });
        return () => { socket.disconnect(); };
    }, [apiBase, humanSession]);

    useEffect(() => {
        const storageKey = `nimmi_chat_history_${botId}`;
        try {
            const saved = localStorage.getItem(storageKey);
            if (saved) {
                const { messages: savedMessages, timestamp, mode: savedMode } = JSON.parse(saved);
                if (Date.now() - timestamp < 24 * 60 * 60 * 1000 && savedMode === "human") {
                    const unique = (savedMessages || []).filter((m: any, i: number, all: any[]) => i === all.findIndex((x: any) => x.id === m.id));
                    setHumanMessages(unique.map((m: any) => ({ ...m, timestamp: new Date(m.timestamp) })));
                    setMode("human");
                } else {
                    localStorage.removeItem(storageKey);
                }
            }
        } catch { /* storage unavailable */ }

        (async () => {
            try {
                const res = await fetch(`${apiBase}/api/bots/${botId}/config`);
                if (res.ok) setBotConfig(await res.json());
            } catch (err) {
                console.error("Failed to load bot config:", err);
            }
        })();
    }, [botId, apiBase]);

    // Start the flow once, after the config (and so callbacks_enabled) is known.
    useEffect(() => {
        if (!botConfig || flowStarted.current) return;
        flowStarted.current = true;
        const { nodes = [], edges = [] } = botConfig.flow_data || {};
        const flow = new Flow(nodes, edges);
        flowRef.current = flow;
        if (flow.hasSteps) run(flow.start());
        else say(`Hi! I'm ${botConfig.bot_name || "your assistant"}. How can I help you today?`);
    }, [botConfig, run, say]);

    useEffect(() => {
        if (mode === "human" && humanMessages.length > 0) {
            try {
                localStorage.setItem(`nimmi_chat_history_${botId}`, JSON.stringify({ messages: humanMessages, timestamp: Date.now(), mode: "human" }));
            } catch { /* storage unavailable */ }
        }
    }, [humanMessages, mode, botId]);

    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [messages, pending]);

    // ── Free chat ──────────────────────────────────────────────────
    const handleSend = async () => {
        const text = input.trim();
        if (!text || loading) return;
        setInput("");

        if (mode === "human") {
            setHumanMessages((prev) => [...prev, { id: uid(), text, sender: "user", timestamp: new Date() }]);
            // Always through the socket, so the message is stored and the team is notified.
            if (socketRef.current?.connected) socketRef.current.emit("message", { room: humanSession, message: text, sender: "visitor" });
            return;
        }

        // Typing answers the flow's question; a typed option counts as choosing it.
        if (pending?.kind === "input") return answer(text);
        if (pending?.kind === "choices" || pending?.kind === "callback") {
            const options = pending.kind === "choices" ? pending.options : [CALL_YES, CALL_NO];
            const match = options.find((o) => o.toLowerCase() === text.toLowerCase());
            if (match) return answer(match);
        }

        const userMsg: Message = { id: uid(), text, sender: "user", timestamp: new Date() };
        const history = [...aiMessages, userMsg].filter((m) => m.text).map((m) => ({ role: m.sender === "user" ? "user" : "assistant", content: m.text }));
        const botMsgId = uid();
        setAiMessages((prev) => [...prev, userMsg, { id: botMsgId, text: "", sender: "bot", timestamp: new Date() }]);
        setLoading(true);

        try {
            const res = await fetch(`${apiBase}/api/chat/message/stream`, {
                method: "POST",
                // Demo mode only counts when the bot owner is signed in on this dashboard.
                headers: { "Content-Type": "application/json", ...demoHeaders },
                body: JSON.stringify({ bot_id: botId, message: text, visitor_session_id: aiSession, history, is_demo: isDemo }),
            });
            if (!res.ok || !res.body) throw new Error("Failed to get response");
            const reader = res.body.getReader();
            const decoder = new TextDecoder();
            let buffer = "";
            let reply = "";
            for (;;) {
                const { done, value } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split("\n");
                buffer = lines.pop() ?? ""; // keep a partial line for the next chunk
                for (const line of lines) {
                    if (!line.startsWith("data: ")) continue;
                    const data = line.slice(6);
                    if (data.trim() === "[DONE]") continue;
                    reply += data;
                    setAiMessages((prev) => prev.map((m) => (m.id === botMsgId ? { ...m, text: reply } : m)));
                }
            }
        } catch (err) {
            console.error("Chat error:", err);
            setAiMessages((prev) => prev.map((m) => (m.id === botMsgId ? { ...m, text: "Sorry, something went wrong. Please try again." } : m)));
        } finally {
            setLoading(false);
        }
    };

    const visual = botConfig?.visual_config || {};
    const primaryColor = visual.color || "#9d55ac";
    const textColor = visual.text_color || visual.textColor || "#ffffff";
    const fontFamily = visual.font_family || visual.fontFamily || "Inter, sans-serif";
    const borderRadius = visual.border_radius ? `${visual.border_radius}px` : (visual.borderRadius ? `${visual.borderRadius}px` : "24px");
    const chatBg = visual.chat_bg_color || visual.chatBgColor || "#f8fafc";
    const background = visual.background_image || visual.backgroundImage;
    const googleFontName = fontFamily.replace(/'/g, "").split(",")[0].replace(/ /g, "+");
    const fontUrl = `https://fonts.googleapis.com/css2?family=${googleFontName}:wght@400;700&display=swap`;

    const placeholder = mode === "ai" && pending?.kind === "input"
        ? (pending.node.data?.placeholder || "Type your answer…")
        : "Type a message...";
    const chip = "px-3 py-1.5 rounded-full text-xs border transition-colors hover:opacity-80";

    return (
        <div className="flex flex-col h-screen overflow-hidden relative" style={{ fontFamily, backgroundColor: chatBg }}>
            {background && (
                <div
                    className="absolute inset-0 z-0 pointer-events-none"
                    style={{
                        backgroundImage: `url(${background.includes("/static/uploads/") ? `${apiBase}/static/uploads/${background.split("/").pop()}` : background})`,
                        backgroundSize: "cover",
                        backgroundPosition: "center",
                        opacity: visual.background_opacity ?? visual.backgroundOpacity ?? 1,
                    }}
                />
            )}

            <header className="p-4 font-bold flex items-center justify-between shrink-0 shadow-lg relative z-20 border-b border-white/10"
                    style={{
                        backgroundColor: primaryColor,
                        color: textColor,
                        minHeight: (visual.header_height || visual.headerHeight) ? `${visual.header_height || visual.headerHeight}px` : undefined,
                        borderTopLeftRadius: borderRadius,
                        borderTopRightRadius: borderRadius,
                    }}>
                <div className="flex items-center gap-3 min-w-0">
                    <img
                        src={visual.logo_url || visual.botLogo || "/favicon.png"}
                        alt=""
                        className="w-10 h-10 rounded-full border-2 border-white/50 object-cover shrink-0"
                    />
                    <div className="flex flex-col min-w-0">
                        <span className="font-bold text-sm tracking-tight truncate">{botConfig?.bot_name || "Assistant"}</span>
                        <span className="text-[10px] opacity-70 font-medium">{mode === "human" ? "Chatting with our team" : "Usually replies instantly"}</span>
                    </div>
                </div>

                <div className="flex items-center gap-2 ml-auto">
                    <div role="radiogroup" aria-label="Chat with" className="flex bg-black/20 p-0.5 rounded-full border border-white/10">
                        {(["ai", "human"] as const).map((m) => (
                            <button
                                key={m}
                                role="radio"
                                aria-checked={mode === m}
                                onClick={() => handleModeToggle(m)}
                                className={`px-3 py-1 rounded-full text-[10px] font-semibold transition-colors ${mode === m ? "bg-white text-black" : "opacity-70 hover:opacity-100"}`}
                            >
                                {m === "ai" ? "Assistant" : "Person"}
                            </button>
                        ))}
                    </div>
                    <button onClick={() => window.parent.postMessage("close-nimmi-widget", "*")} aria-label="Close chat"
                            className="p-2 hover:bg-white/10 rounded-full opacity-70 hover:opacity-100 transition-opacity">
                        <X size={18} />
                    </button>
                </div>
            </header>

            <main className="flex-1 overflow-y-auto p-5 space-y-3 custom-scrollbar relative z-10">
                <AnimatePresence initial={false}>
                    {messages.map((msg) => (
                        <motion.div
                            key={msg.id}
                            initial={{ opacity: 0, y: 8 }}
                            animate={{ opacity: 1, y: 0 }}
                            className={`flex ${msg.sender === "user" ? "justify-end" : "justify-start"} items-start gap-2`}
                        >
                            {msg.sender === "bot" && (
                                <div className="w-7 h-7 rounded-full flex items-center justify-center text-white shrink-0 mt-1"
                                     style={{ backgroundColor: mode === "human" ? "#16a34a" : primaryColor }}>
                                    {mode === "human" ? <User size={14} /> : <Bot size={14} />}
                                </div>
                            )}
                            {msg.media ? (
                                msg.media.type === "image"
                                    ? <img src={msg.media.url} alt="" className="max-w-[80%] rounded-xl" />
                                    : <video src={msg.media.url} controls className="max-w-[80%] rounded-xl" />
                            ) : (
                                <div
                                    className="px-4 py-3 text-[13px] leading-relaxed max-w-[85%] whitespace-pre-wrap shadow-sm"
                                    style={{
                                        borderRadius,
                                        backgroundColor: msg.sender === "user" ? (visual.user_bubble_bg || visual.userBubbleBg || primaryColor) : (visual.assistant_bubble_bg || visual.assistantBubbleBg || "#E5E7EB"),
                                        color: msg.sender === "user" ? (visual.user_bubble_text || visual.userBubbleText || "#ffffff") : (visual.assistant_bubble_text || visual.assistantBubbleText || "#1F2937"),
                                        borderTopRightRadius: msg.sender === "user" ? 0 : undefined,
                                        borderTopLeftRadius: msg.sender === "bot" ? 0 : undefined,
                                    }}
                                >
                                    {msg.text || (loading ? <span className="flex gap-1 py-1 animate-pulse"><span className="w-1 h-1 bg-slate-400 rounded-full" /><span className="w-1 h-1 bg-slate-400 rounded-full" /><span className="w-1 h-1 bg-slate-400 rounded-full" /></span> : "")}
                                </div>
                            )}
                        </motion.div>
                    ))}
                </AnimatePresence>

                {mode === "ai" && pending && pending.kind !== "input" && (
                    <div className="flex flex-wrap gap-2 pl-9">
                        {pending.kind === "choices" && pending.options.map((o) => (
                            <button key={o} onClick={() => answer(o)} className={chip} style={{ borderColor: primaryColor, color: primaryColor }}>{o}</button>
                        ))}
                        {pending.kind === "rating" && Array.from({ length: pending.scale }, (_, i) => String(i + 1)).map((n) => (
                            <button key={n} onClick={() => answer(n)} className={`${chip} w-9 px-0`} style={{ borderColor: primaryColor, color: primaryColor }}>{n}</button>
                        ))}
                        {pending.kind === "callback" && (
                            <>
                                <button onClick={() => answer(CALL_YES)} className={`${chip} inline-flex items-center gap-1.5`} style={{ backgroundColor: primaryColor, borderColor: primaryColor, color: textColor }}>
                                    <Phone size={12} /> {CALL_YES}
                                </button>
                                <button onClick={() => answer(CALL_NO)} className={chip} style={{ borderColor: primaryColor, color: primaryColor }}>{CALL_NO}</button>
                            </>
                        )}
                        {pending.kind === "file" && (
                            <>
                                <button onClick={() => fileRef.current?.click()} className={`${chip} inline-flex items-center gap-1.5`} style={{ borderColor: primaryColor, color: primaryColor }}>
                                    <Paperclip size={12} /> Choose a file
                                </button>
                                <input ref={fileRef} type="file" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (f) answer(f.name); }} />
                            </>
                        )}
                    </div>
                )}
                <div ref={messagesEndRef} />
            </main>

            <footer className="p-4 bg-zinc-900/80 border-t border-white/5 flex flex-col gap-2 backdrop-blur-md relative z-10">
                {mode === "human" && (
                    <div className="text-[10px] text-white/40 flex items-center gap-1 px-1">
                        <Clock size={10} />
                        <span>Chat history is kept for 24 hours</span>
                    </div>
                )}
                {botConfig?.callbacks_enabled && mode === "ai" && !pending && (
                    callback.state === "done" ? (
                        <p className="text-[11px] text-white/70 px-1">Thanks. We&apos;ll call you shortly.</p>
                    ) : !callback.open ? (
                        <button onClick={() => setCallback({ ...callback, open: true })} className="self-start text-[11px] text-white/70 hover:text-white underline underline-offset-2 px-1">
                            Prefer a call? Ask us to call you back
                        </button>
                    ) : (
                        <form
                            className="flex flex-col gap-2 p-3 rounded-xl bg-white/5 border border-white/10"
                            onSubmit={async (e) => {
                                e.preventDefault();
                                setCallback({ ...callback, state: "sending", error: "" });
                                try {
                                    const res = await fetch(`${apiBase}/api/voice/callbacks/request`, {
                                        method: "POST",
                                        headers: { "Content-Type": "application/json" },
                                        body: JSON.stringify({ bot_id: botId, phone: callback.phone, consent: callback.consent, session_id: aiSession }),
                                    });
                                    const body = await res.json().catch(() => ({}));
                                    if (!res.ok) throw new Error(body.detail || "Couldn't request a call");
                                    setCallback({ ...callback, state: "done" });
                                } catch (err) {
                                    setCallback({ ...callback, state: "error", error: (err as Error).message });
                                }
                            }}
                        >
                            <input
                                type="tel" inputMode="tel" required placeholder="Your phone number" value={callback.phone}
                                onChange={(e) => setCallback({ ...callback, phone: e.target.value })}
                                className="h-10 rounded-lg px-3 text-sm outline-none bg-white text-black"
                                aria-label="Your phone number"
                            />
                            <label className="flex items-start gap-2 text-[11px] text-white/80 leading-snug">
                                <input type="checkbox" required checked={callback.consent}
                                       onChange={(e) => setCallback({ ...callback, consent: e.target.checked })} className="mt-0.5" />
                                <span>I agree to receive a call from {botConfig?.bot_name || "this business"} about my enquiry. The call may be recorded.</span>
                            </label>
                            {callback.state === "error" && <p className="text-[11px] text-red-300">{callback.error}</p>}
                            <div className="flex gap-2">
                                <button type="submit" disabled={callback.state === "sending" || !callback.consent}
                                        className="flex-1 h-9 rounded-lg text-xs font-semibold disabled:opacity-50"
                                        style={{ backgroundColor: primaryColor, color: textColor }}>
                                    {callback.state === "sending" ? "Requesting…" : "Call me"}
                                </button>
                                <button type="button" onClick={() => setCallback({ ...callback, open: false })} className="h-9 px-3 rounded-lg text-xs text-white/70 hover:text-white">
                                    Cancel
                                </button>
                            </div>
                        </form>
                    )
                )}
                <form className="flex gap-2 w-full" onSubmit={(e) => { e.preventDefault(); handleSend(); }}>
                    <input
                        type={mode === "ai" && pending?.kind === "input" && pending.type === "datePicker" ? "date" : "text"}
                        inputMode={mode === "ai" && pending?.kind === "input" && pending.type === "phoneInput" ? "tel" : undefined}
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        placeholder={placeholder}
                        aria-label="Message"
                        className="flex-1 rounded-xl border border-white/5 h-12 px-4 text-sm outline-none"
                        style={{ backgroundColor: visual.input_bg_color || visual.inputBgColor || "#ffffff", color: visual.input_text_color || visual.inputTextColor || "#000000" }}
                    />
                    <button
                        type="submit"
                        disabled={!input.trim() || loading}
                        aria-label="Send"
                        className="w-12 h-12 shrink-0 rounded-xl flex items-center justify-center active:scale-95 transition-transform disabled:opacity-50"
                        style={{ backgroundColor: primaryColor, color: textColor }}
                    >
                        <Send size={18} />
                    </button>
                </form>
            </footer>

            <style dangerouslySetInnerHTML={{ __html: `
                @import url('${fontUrl}');
                .custom-scrollbar::-webkit-scrollbar { width: 4px; }
                .custom-scrollbar::-webkit-scrollbar-track { background: transparent; }
                .custom-scrollbar::-webkit-scrollbar-thumb { background: #e2e8f0; border-radius: 10px; }
            `}} />
        </div>
    );
}

export default function WidgetPage({ params }: { params: Promise<{ botId: string }> }) {
    return (
        <Suspense fallback={<div className="flex h-screen items-center justify-center bg-white"><div className="w-8 h-8 border-4 border-slate-200 border-t-[#9d55ac] rounded-full animate-spin" /></div>}>
            <WidgetContent params={params} />
        </Suspense>
    );
}
