"use client";

import { use, useCallback, useEffect, useRef, useState, Suspense } from "react";
import { apiBase as apiBaseUrl, authHeaders } from "@/lib/api";
import { Send, User, Bot, X, Clock, Paperclip, Phone, ThumbsUp, ThumbsDown, Mic, Square, Loader2 } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { io, type Socket } from "socket.io-client";
import { motion, AnimatePresence } from "framer-motion";
import { Flow, evaluate, questionFor, validate, variableName, type FlowNode, type InputType } from "./flow";
import { isLight } from "@/lib/color";
import { RichText } from "./rich";
import { speechLang, useVoiceInput } from "./voice";

interface Message {
    id: string;
    text: string;
    sender: "user" | "bot";
    timestamp: Date;
    media?: { type: "image" | "video"; url: string };
    /** For AI answers: the question it answered, and the visitor's rating of it. */
    question?: string;
    rated?: "up" | "down";
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
    const inApp = searchParams.get("app") === "1"; // a phone app shows this page full screen: no close button
    const [aiMessages, setAiMessages] = useState<Message[]>([]);
    const [humanMessages, setHumanMessages] = useState<Message[]>([]);
    const [input, setInput] = useState("");
    const [loading, setLoading] = useState(false);
    const [mode, setMode] = useState<"ai" | "human">("ai");
    const [botConfig, setBotConfig] = useState<any>(null);
    const [pending, setPending] = useState<Pending | null>(null);
    const [flowDone, setFlowDone] = useState(false); // no flow, or it has finished: free chat
    const [askedOwnQuestion, setAskedOwnQuestion] = useState(false); // typed to the assistant, not an answer to the flow
    const [callback, setCallback] = useState<{ open: boolean; phone: string; consent: boolean; state: "idle" | "sending" | "done" | "error"; error: string }>(
        { open: false, phone: "", consent: false, state: "idle", error: "" });
    const socketRef = useRef<Socket | null>(null);
    const messagesEndRef = useRef<HTMLDivElement>(null);
    const fileRef = useRef<HTMLInputElement>(null);
    const flowRef = useRef<Flow | null>(null);
    const varsRef = useRef<Record<string, string>>({});
    const flowStarted = useRef(false);

    // Same address the rest of the dashboard uses (NEXT_PUBLIC_API_URL locally, api.nimmiai.in live).
    const apiBase = apiBaseUrl();
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

    // The team's replies arrive over the socket and are also fetched every few seconds (the socket can drop, or
    // be on another server process). Each has its saved id, so it shows once; replies from an earlier chat in
    // this session are marked seen when the chat starts, so they aren't shown as new.
    const seenReplies = useRef<Set<string>>(new Set());
    const repliesKnown = useRef(false);
    const takeReply = useCallback((id: string, text: string) => {
        if (seenReplies.current.has(id)) return;
        seenReplies.current.add(id);
        setHumanMessages((prev) => (prev.some((m) => m.id === id) ? prev : [...prev, { id, text, sender: "bot", timestamp: new Date() }]));
    }, []);

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
                (body.earlier || []).forEach((id: string) => seenReplies.current.add(id));
                repliesKnown.current = true;
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
        else {
            setMode("ai");
            // Back with the assistant by choice: next time the chat opens here too.
            try { localStorage.removeItem(`nimmi_chat_history_${botId}`); } catch { /* storage unavailable */ }
        }
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
        body: JSON.stringify({ bot_id: botId, url, method, body }),
    }).then((r) => r.json()).catch(() => ({}));

    const run = useCallback(async (node: FlowNode | null): Promise<void> => {
        const flow = flowRef.current;
        if (!node || !flow) {
            // The flow ran out of steps without an End block: close it politely and hand over to the assistant.
            setPending(null);
            if (flow) {
                await sleep(400);
                const first = String(varsRef.current.name || "").trim().split(" ")[0];
                say(`Thanks${first ? `, ${first}` : ""}! How can I help you today?`);
            }
            setFlowDone(true); // after the closing line, so suggested questions come below it
            return;
        }
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
                setFlowDone(true);
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
            if (data.sender === "agent") takeReply(data.id || uid(), data.message);
        });
        return () => { socket.disconnect(); };
    }, [apiBase, humanSession, takeReply]);

    // While talking to a person: check for the team's replies too, in case the socket missed one.
    useEffect(() => {
        if (mode !== "human") return;
        let stopped = false;
        const check = async () => {
            if (document.visibilityState !== "visible") return;
            try {
                const res = await fetch(`${apiBase}/api/chat/live/${botId}/${encodeURIComponent(humanSession)}`);
                if (!res.ok || stopped) return;
                const { messages: replies = [] } = await res.json();
                if (!repliesKnown.current) {  // reopened without a record of what was seen: these are old
                    replies.forEach((r: { id: string }) => seenReplies.current.add(r.id));
                    repliesKnown.current = true;
                    return;
                }
                replies.forEach((r: { id: string; text: string }) => takeReply(r.id, r.text));
            } catch { /* offline for a moment: the next check catches up */ }
        };
        check();
        const timer = setInterval(check, 4000);
        return () => { stopped = true; clearInterval(timer); };
    }, [mode, apiBase, botId, humanSession, takeReply]);

    useEffect(() => {
        const storageKey = `nimmi_chat_history_${botId}`;
        try {
            const saved = localStorage.getItem(storageKey);
            if (saved) {
                const { messages: savedMessages, timestamp, mode: savedMode, seen } = JSON.parse(saved);
                const unique = (savedMessages || []).filter((m: any, i: number, all: any[]) => i === all.findIndex((x: any) => x.id === m.id));
                // The chat opens with the assistant. It reopens with the team only to carry on a real conversation
                // (the visitor wrote, or the team replied), not because "Person" was once clicked.
                const talking = unique.some((m: any) => m.sender === "user") || unique.length > 1;
                if (Date.now() - timestamp < 24 * 60 * 60 * 1000 && savedMode === "human" && talking) {
                    setHumanMessages(unique.map((m: any) => ({ ...m, timestamp: new Date(m.timestamp) })));
                    if (Array.isArray(seen)) {
                        seen.forEach((id: string) => seenReplies.current.add(id));
                        repliesKnown.current = true;
                    }
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
        else {
            setFlowDone(true);
            say(String(botConfig.visual_config?.welcome_message || "").trim()
                || `Hi! I'm ${botConfig.bot_name || "your assistant"}. How can I help you today?`);
        }
    }, [botConfig, run, say]);

    useEffect(() => {
        if (mode === "human" && humanMessages.length > 0) {
            try {
                localStorage.setItem(`nimmi_chat_history_${botId}`, JSON.stringify({
                    messages: humanMessages, timestamp: Date.now(), mode: "human", seen: [...seenReplies.current] }));
            } catch { /* storage unavailable */ }
        }
    }, [humanMessages, mode, botId]);

    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [messages, pending]);

    // A visitor's rating of an answer; unhelpful ones reach the business's Questions page.
    const rate = (msg: Message, helpful: boolean) => {
        setAiMessages((prev) => prev.map((m) => (m.id === msg.id ? { ...m, rated: helpful ? "up" : "down" } : m)));
        fetch(`${apiBase}/api/chat/feedback`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ bot_id: botId, visitor_session_id: aiSession, question: msg.question, helpful }),
        }).catch(() => {});
    };

    // ── Free chat ──────────────────────────────────────────────────
    /** `suggested`: a suggested question was clicked. It goes to the assistant even while the flow waits for an
     *  answer, and the flow then asks its question again. */
    const handleSend = async (preset?: string, suggested = false) => {
        const text = (preset ?? input).trim();
        if (!text || loading) return;
        setInput("");
        const flowWaiting = suggested && pending?.kind === "input" ? pending : null;

        if (mode === "human") {
            setHumanMessages((prev) => [...prev, { id: uid(), text, sender: "user", timestamp: new Date() }]);
            // Always through the socket, so the message is stored and the team is notified. While it's
            // reconnecting, socket.io holds the message and sends it once connected (it used to be dropped).
            socketRef.current?.emit("message", { room: humanSession, message: text, sender: "visitor" });
            return;
        }

        // Typing answers the flow's question; a typed option counts as choosing it.
        if (pending?.kind === "input" && !flowWaiting) return answer(text);
        if (!suggested && (pending?.kind === "choices" || pending?.kind === "callback")) {
            const options = pending.kind === "choices" ? pending.options : [CALL_YES, CALL_NO];
            const match = options.find((o) => o.toLowerCase() === text.toLowerCase());
            if (match) return answer(match);
        }

        const userMsg: Message = { id: uid(), text, sender: "user", timestamp: new Date() };
        setAskedOwnQuestion(true);
        const history = [...aiMessages, userMsg].filter((m) => m.text).map((m) => ({ role: m.sender === "user" ? "user" : "assistant", content: m.text }));
        const botMsgId = uid();
        setAiMessages((prev) => [...prev, userMsg, { id: botMsgId, text: "", sender: "bot", timestamp: new Date(), question: text }]);
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
                    // Pieces are JSON strings, so line breaks inside the answer survive; older servers sent plain text.
                    let piece = data;
                    if (data.startsWith('"')) { try { piece = JSON.parse(data); } catch { /* keep as is */ } }
                    reply += piece;
                    setAiMessages((prev) => prev.map((m) => (m.id === botMsgId ? { ...m, text: reply } : m)));
                }
            }
        } catch (err) {
            console.error("Chat error:", err);
            setAiMessages((prev) => prev.map((m) => (m.id === botMsgId ? { ...m, text: "Sorry, something went wrong. Please try again." } : m)));
        } finally {
            setLoading(false);
        }
        if (flowWaiting) {
            await sleep(400);
            say(questionFor(flowWaiting.node)); // back to the flow's question, which is still waiting for its answer
        }
    };

    // Mic: speak instead of typing. Words appear as they're heard and are sent when the visitor stops.
    const voice = useVoiceInput({
        lang: speechLang(botConfig?.language), apiBase, botId, headers: demoHeaders,
        onText: (text, final) => {
            if (!final) return setInput(text);
            setInput("");
            handleSend(text);
        },
        onError: (message) => {
            if (mode === "ai") say(message);
            else setHumanMessages((prev) => [...prev, { id: uid(), text: message, sender: "bot", timestamp: new Date() }]);
        },
    });

    const visual = botConfig?.visual_config || {};
    const primaryColor = visual.color || "#9d55ac";
    const textColor = visual.text_color || visual.textColor || "#ffffff";
    const fontFamily = visual.font_family || visual.fontFamily || "Inter, sans-serif";
    const borderRadius = visual.border_radius ? `${visual.border_radius}px` : (visual.borderRadius ? `${visual.borderRadius}px` : "24px");
    const chatBg = visual.chat_bg_color || visual.chatBgColor || "#f8fafc";
    const chatLight = isLight(chatBg);
    const background = visual.background_image || visual.backgroundImage;
    const googleFontName = fontFamily.replace(/'/g, "").split(",")[0].replace(/ /g, "+");
    const fontUrl = `https://fonts.googleapis.com/css2?family=${googleFontName}:wght@400;700&display=swap`;

    const placeholder = mode === "ai" && pending?.kind === "input"
        ? (pending.node.data?.placeholder || "Type your answer…")
        : (visual.input_placeholder || "Type a message...");
    // Suggested questions: from the first message until the visitor asks their own question (answers to the flow's
    // questions don't count). Shown while the flow waits for a typed answer or is done; not beside the flow's own buttons.
    const starters: string[] = (Array.isArray(visual.starters) ? visual.starters : [])
        .map((q: unknown) => String(q).trim()).filter(Boolean).slice(0, 4);
    const showStarters = mode === "ai" && starters.length > 0 && !askedOwnQuestion && aiMessages.length > 0
        && ((flowDone && !pending) || pending?.kind === "input");
    // Footer: dark glass by default; a chosen colour gets text that reads on it.
    const footerBg: string = visual.footer_bg_color || "";
    const footerLight = !!footerBg && isLight(footerBg);
    const onFooter = (light: string, dark: string) => (footerLight ? light : dark);
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

            <header className="p-4 flex flex-col justify-center gap-3 shrink-0 shadow-lg relative z-20 border-b border-white/10"
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
                        className="w-10 h-10 rounded-full border-2 border-white/50 object-cover object-top shrink-0"
                    />
                    <div className="flex flex-col min-w-0 flex-1">
                        <span className="font-bold text-sm tracking-tight truncate">{botConfig?.bot_name || "Assistant"}</span>
                        <span className="text-[11px] opacity-75 font-medium truncate">
                            {mode === "human" && <span className="inline-block w-1.5 h-1.5 rounded-full bg-green-400 mr-1.5 align-middle" aria-hidden />}
                            {mode === "human" ? "Chatting with our team" : (visual.subtitle || "Usually replies instantly")}
                        </span>
                    </div>
                    {visual.show_human_toggle !== false && (
                        <div role="radiogroup" aria-label="Chat with" className="flex items-center p-0.5 rounded-full border border-current/30 bg-current/10 shrink-0">
                            {(["ai", "human"] as const).map((m) => (
                                <button key={m} type="button" role="radio" aria-checked={mode === m} onClick={() => handleModeToggle(m)}
                                        title={m === "ai" ? "Chat with the assistant" : "Talk to a person"}
                                        className={`inline-flex items-center gap-1 h-[22px] px-2 rounded-full text-[11px] font-semibold transition-colors ${mode === m ? "bg-white text-gray-900 shadow-sm" : "opacity-80 hover:opacity-100"}`}>
                                    {m === "ai" ? <Bot size={12} /> : <User size={12} />}
                                    <span className="hidden min-[360px]:inline">{m === "ai" ? "AI" : "Person"}</span>
                                </button>
                            ))}
                        </div>
                    )}
                    {!inApp && (
                        <button onClick={() => window.parent.postMessage("close-nimmi-widget", "*")} aria-label="Close chat"
                                className="p-2 -mr-1 hover:bg-white/10 rounded-full opacity-70 hover:opacity-100 transition-opacity shrink-0">
                            <X size={18} />
                        </button>
                    )}
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
                                <div className="flex flex-col gap-1 max-w-[85%] min-w-0">
                                <div
                                    className={`px-4 py-3 text-[13px] leading-relaxed shadow-sm ${msg.sender === "bot" ? "" : "whitespace-pre-wrap"}`}
                                    style={{
                                        borderRadius,
                                        backgroundColor: msg.sender === "user" ? (visual.user_bubble_bg || visual.userBubbleBg || primaryColor) : (visual.assistant_bubble_bg || visual.assistantBubbleBg || "#E5E7EB"),
                                        color: msg.sender === "user" ? (visual.user_bubble_text || visual.userBubbleText || "#ffffff") : (visual.assistant_bubble_text || visual.assistantBubbleText || "#1F2937"),
                                        borderTopRightRadius: msg.sender === "user" ? 0 : undefined,
                                        borderTopLeftRadius: msg.sender === "bot" ? 0 : undefined,
                                    }}
                                >
                                    {msg.text ? (msg.sender === "bot" ? <RichText text={msg.text} /> : msg.text) : (loading ? <span className="flex gap-1 py-1 animate-pulse"><span className="w-1 h-1 bg-slate-400 rounded-full" /><span className="w-1 h-1 bg-slate-400 rounded-full" /><span className="w-1 h-1 bg-slate-400 rounded-full" /></span> : "")}
                                </div>
                                {visual.answer_feedback && mode === "ai" && msg.question && msg.text && !(loading && msg.id === aiMessages[aiMessages.length - 1]?.id) && (
                                    <div className={`flex items-center gap-1 px-1 text-[11px] ${chatLight ? "text-stone-500" : "text-white/60"}`}>
                                        {msg.rated ? (
                                            <span>{msg.rated === "up" ? "Thanks for letting us know." : "Thanks. We'll use this to improve."}</span>
                                        ) : (
                                            <>
                                                <span className="mr-0.5">Helpful?</span>
                                                <button onClick={() => rate(msg, true)} aria-label="Helpful" className="p-1 rounded hover:bg-black/5"><ThumbsUp size={12} /></button>
                                                <button onClick={() => rate(msg, false)} aria-label="Not helpful" className="p-1 rounded hover:bg-black/5"><ThumbsDown size={12} /></button>
                                            </>
                                        )}
                                    </div>
                                )}
                                </div>
                            )}
                        </motion.div>
                    ))}
                </AnimatePresence>

                {showStarters && (
                    <div className="flex flex-wrap gap-2 pl-9">
                        {starters.map((q) => (
                            <button key={q} onClick={() => handleSend(q, true)} className={chip} style={{ borderColor: primaryColor, color: primaryColor }}>{q}</button>
                        ))}
                    </div>
                )}

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

            <footer className={`p-4 border-t flex flex-col gap-2 relative z-10 ${footerBg ? onFooter("border-black/5", "border-white/5") : "bg-zinc-900/80 border-white/5 backdrop-blur-md"}`}
                    style={footerBg ? { backgroundColor: footerBg } : undefined}>
                {mode === "human" && (
                    <div className={`text-[10px] flex items-center gap-1 px-1 ${onFooter("text-stone-400", "text-white/40")}`}>
                        <Clock size={10} />
                        <span>Chat history is kept for 24 hours</span>
                    </div>
                )}
                {botConfig?.callbacks_enabled && mode === "ai" && !pending && (
                    callback.state === "done" ? (
                        <p className={`text-[11px] px-1 ${onFooter("text-stone-600", "text-white/70")}`}>Thanks. We&apos;ll call you shortly.</p>
                    ) : !callback.open ? (
                        <button onClick={() => setCallback({ ...callback, open: true })} className={`self-start text-[11px] underline underline-offset-2 px-1 ${onFooter("text-stone-600 hover:text-stone-900", "text-white/70 hover:text-white")}`}>
                            Prefer a call? Ask us to call you back
                        </button>
                    ) : (
                        <form
                            className={`flex flex-col gap-2 p-3 rounded-xl border ${onFooter("bg-black/[0.03] border-black/10", "bg-white/5 border-white/10")}`}
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
                                className={`h-10 rounded-lg px-3 text-sm outline-none bg-white text-black ${onFooter("border border-black/10", "")}`}
                                aria-label="Your phone number"
                            />
                            <label className={`flex items-start gap-2 text-[11px] leading-snug ${onFooter("text-stone-700", "text-white/80")}`}>
                                <input type="checkbox" required checked={callback.consent}
                                       onChange={(e) => setCallback({ ...callback, consent: e.target.checked })} className="mt-0.5" />
                                <span>I agree to receive a call from {botConfig?.bot_name || "this business"} about my enquiry. The call may be recorded.</span>
                            </label>
                            {callback.state === "error" && <p className={`text-[11px] ${onFooter("text-red-600", "text-red-300")}`}>{callback.error}</p>}
                            <div className="flex gap-2">
                                <button type="submit" disabled={callback.state === "sending" || !callback.consent}
                                        className="flex-1 h-9 rounded-lg text-xs font-semibold disabled:opacity-50"
                                        style={{ backgroundColor: primaryColor, color: textColor }}>
                                    {callback.state === "sending" ? "Requesting…" : "Call me"}
                                </button>
                                <button type="button" onClick={() => setCallback({ ...callback, open: false })} className={`h-9 px-3 rounded-lg text-xs ${onFooter("text-stone-600 hover:text-stone-900", "text-white/70 hover:text-white")}`}>
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
                        className={`flex-1 rounded-xl border h-12 px-4 text-sm outline-none ${onFooter("border-black/10", "border-white/5")}`}
                        style={{ backgroundColor: visual.input_bg_color || visual.inputBgColor || "#ffffff", color: visual.input_text_color || visual.inputTextColor || "#000000" }}
                    />
                    {voice.supported && !input.trim() && !voice.listening ? (
                        <button
                            type="button"
                            onClick={voice.start}
                            disabled={loading || voice.busy}
                            aria-label="Speak your message"
                            title="Speak your message"
                            className="w-12 h-12 shrink-0 rounded-xl flex items-center justify-center active:scale-95 transition-transform disabled:opacity-50"
                            style={{ backgroundColor: primaryColor, color: textColor }}
                        >
                            {voice.busy ? <Loader2 size={18} className="animate-spin" /> : <Mic size={18} />}
                        </button>
                    ) : voice.listening ? (
                        <button
                            type="button"
                            onClick={voice.stop}
                            aria-label="Stop and send"
                            title="Stop and send"
                            className="w-12 h-12 shrink-0 rounded-xl flex items-center justify-center bg-red-500 text-white animate-pulse"
                        >
                            <Square size={16} fill="currentColor" />
                        </button>
                    ) : (
                        <button
                            type="submit"
                            disabled={!input.trim() || loading}
                            aria-label="Send"
                            className="w-12 h-12 shrink-0 rounded-xl flex items-center justify-center active:scale-95 transition-transform disabled:opacity-50"
                            style={{ backgroundColor: primaryColor, color: textColor }}
                        >
                            <Send size={18} />
                        </button>
                    )}
                </form>
                <p className={`text-center text-[10px] leading-none -mb-1 ${onFooter("text-stone-400", "text-white/40")}`}>
                    Powered by{" "}
                    <a href="https://nimmiai.in" target="_blank" rel="noopener noreferrer"
                       className={`font-semibold underline-offset-2 hover:underline ${onFooter("text-stone-500 hover:text-stone-800", "text-white/60 hover:text-white")}`}>
                        Nimmi
                    </a>
                </p>
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
