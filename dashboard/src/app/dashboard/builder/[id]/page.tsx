"use client";

import { Suspense, use, useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import dynamic from "next/dynamic";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowLeft, Check, Code2, Eye, PencilLine, Play } from "lucide-react";
import { Node, Edge, useNodesState, useEdgesState, addEdge, Connection, MarkerType } from "reactflow";
import { apiFetch } from "@/lib/api";
import { Button, Segmented, Skeleton, ToastProvider, cn } from "@/components/ui";
import ElementsSidebar from "./components/ElementsSidebar";
import PropertiesPanel from "./components/PropertiesPanel";
import ExportModal from "./components/ExportModal";
import DesignPanel from "./components/DesignPanel";
import KnowledgePanel from "./components/KnowledgePanel";
import BehaviourPanel from "./components/BehaviourPanel";
import LeadsPanel from "./components/LeadsPanel";
import WidgetPreview from "./components/WidgetPreview";
import TestChat from "./components/TestChat";
import {
    BEHAVIOUR_DEFAULTS, VISUAL_DEFAULTS, assetUrl, fontStylesheet, normalizeBehaviour, normalizeVisual,
    type Behaviour, type Visual,
} from "./components/design";

// React Flow needs the browser.
const FlowBuilder = dynamic(() => import("./components/FlowBuilder"), { ssr: false });

const TABS = [
    { id: "design", label: "Design" },
    { id: "knowledge", label: "Knowledge" },
    { id: "behaviour", label: "Behaviour" },
    { id: "flow", label: "Flow" },
    { id: "leads", label: "Leads" },
] as const;
type Tab = (typeof TABS)[number]["id"];
type SaveState = "saved" | "dirty" | "saving" | "error";

/** Everything that gets saved, as one comparable string. */
const snapshotOf = (s: { botName: string; instructions: string; knowledge: string; aiProvider: string; aiModel: string; aiApiKey: string;
                         visual: Visual; behaviour: Behaviour; nodes: unknown[]; edges: unknown[] }) => JSON.stringify(s);

/** Older configs used camelCase keys; drop them on save so the widget never reads a stale copy. */
const LEGACY_KEYS = new Set(["botLogo", ...Object.keys(VISUAL_DEFAULTS).map((k) => k.replace(/_([a-z])/g, (_, c) => c.toUpperCase()))]);

function Builder({ params }: { params: Promise<{ id: string }> }) {
    const { id } = use(params);
    const router = useRouter();
    const searchParams = useSearchParams();

    const [tab, setTab] = useState<Tab>("design");
    const [loading, setLoading] = useState(true);
    const [loadError, setLoadError] = useState(false);

    const [botName, setBotName] = useState("");
    const [visual, setVisual] = useState<Visual>(VISUAL_DEFAULTS);
    const rawVisual = useRef<Record<string, unknown>>({});
    const [behaviour, setBehaviourState] = useState<Behaviour>(BEHAVIOUR_DEFAULTS);
    const savedBehaviour = useRef("");
    const [instructions, setInstructions] = useState("");
    const [knowledge, setKnowledge] = useState("");
    const [aiProvider, setAiProvider] = useState("google");
    const [aiModel, setAiModel] = useState("gemini-3-flash-preview");
    const [aiApiKey, setAiApiKey] = useState("");
    const [hasSavedKey, setHasSavedKey] = useState(false);
    const [callbacks, setCallbacks] = useState(false);

    const [flowNodes, setFlowNodes, onNodesChange] = useNodesState<any>([]);
    const [flowEdges, setFlowEdges, onEdgesChange] = useEdgesState<any>([]);
    const [selectedNode, setSelectedNode] = useState<Node | null>(null);

    const [saveState, setSaveState] = useState<SaveState>("saved");
    const lastSaved = useRef("");
    const privateLoaded = useRef(false); // false: the public view, without instructions, knowledge or reply rules
    const [device, setDevice] = useState<"desktop" | "mobile">("desktop");
    const [chatOpen, setChatOpen] = useState<"open" | "closed">("open");
    const [mobilePreview, setMobilePreview] = useState(false);
    const [showExport, setShowExport] = useState(false);

    const setDesign = useCallback((patch: Partial<Visual>) => setVisual((v) => ({ ...v, ...patch })), []);
    const setBehaviour = useCallback((patch: Partial<Behaviour>) => setBehaviourState((b) => ({ ...b, ...patch })), []);

    // ── Load ────────────────────────────────────────────────────────
    const load = useCallback(async () => {
        setLoadError(false);
        try {
            const res = await apiFetch(`/api/bots/${id}/config`);
            if (!res.ok) throw new Error();
            const data = await res.json();
            privateLoaded.current = "system_prompt" in data;
            const v = normalizeVisual(data.visual_config);
            const b = normalizeBehaviour(data.behaviour);
            const nodes = data.flow_data?.nodes?.length ? data.flow_data.nodes
                : [{ id: "start-1", type: "start", position: { x: 250, y: 50 }, data: { label: "Start" } }];
            const edges = data.flow_data?.nodes?.length ? (data.flow_data.edges || []) : [];
            rawVisual.current = data.visual_config || {};
            setBotName(data.bot_name || "");
            setVisual(v);
            setBehaviourState(b);
            savedBehaviour.current = JSON.stringify(b);
            setInstructions(data.system_prompt || "");
            setKnowledge(data.knowledge_base || "");
            setAiProvider(data.ai_provider || "google");
            setAiModel(data.ai_model || "gemini-3-flash-preview");
            setAiApiKey("");
            setHasSavedKey(!!data.has_ai_api_key);
            setCallbacks(!!data.callbacks_enabled);
            setFlowNodes(nodes);
            setFlowEdges(edges);
            lastSaved.current = snapshotOf({
                botName: data.bot_name || "", instructions: data.system_prompt || "", knowledge: data.knowledge_base || "",
                aiProvider: data.ai_provider || "google", aiModel: data.ai_model || "gemini-3-flash-preview", aiApiKey: "",
                visual: v, behaviour: b, nodes, edges,
            });
            setSaveState("saved");
        } catch {
            setLoadError(true);
        } finally {
            setLoading(false);
        }
    }, [id, setFlowNodes, setFlowEdges]);
    useEffect(() => { load(); }, [load]);
    // On a phone, preview the chat as it looks on a phone.
    useEffect(() => { if (window.innerWidth < 768) setDevice("mobile"); }, []);

    // Back from payment: open the install dialog.
    useEffect(() => {
        if (searchParams.get("payment") === "success") {
            setShowExport(true);
            router.replace(`/dashboard/builder/${id}`);
        }
    }, [searchParams, id, router]);

    // ── Save (automatic, a second after the last change) ────────────
    const snapshot = useMemo(() => snapshotOf({
        botName, instructions, knowledge, aiProvider, aiModel, aiApiKey, visual, behaviour, nodes: flowNodes, edges: flowEdges,
    }), [botName, instructions, knowledge, aiProvider, aiModel, aiApiKey, visual, behaviour, flowNodes, flowEdges]);
    const latest = useRef(snapshot);
    latest.current = snapshot;

    const persist = useCallback(async () => {
        if (snapshot === lastSaved.current) return;
        setSaveState("saving");
        const ids = new Set(flowNodes.map((n: Node) => n.id));
        const visualConfig: Record<string, unknown> = Object.fromEntries(Object.entries(rawVisual.current).filter(([k]) => !LEGACY_KEYS.has(k)));
        const behaviourJson = JSON.stringify(behaviour);
        const body: Record<string, unknown> = {
            bot_name: botName.trim() || "Assistant",
            system_prompt: instructions,
            knowledge_base: knowledge,
            ai_provider: aiProvider,
            ai_model: aiModel,
            ai_api_key: aiApiKey,
            visual_config: { ...visualConfig, ...visual },
            // Dangling links stop the flow in the widget, so drop links to deleted blocks.
            flow_data: { nodes: flowNodes, edges: flowEdges.filter((e: Edge) => ids.has(e.source) && ids.has(e.target)) },
        };
        // Reply rules start applying only once someone changes them.
        if (behaviourJson !== savedBehaviour.current) body.behaviour = behaviour;
        // Never save blanks over what this page wasn't sent.
        if (!privateLoaded.current) {
            for (const key of ["system_prompt", "knowledge_base", "ai_provider", "ai_model", "ai_api_key", "behaviour"]) delete body[key];
        }
        try {
            const res = await apiFetch(`/api/bots/${id.trim()}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
            if (!res.ok) throw new Error();
            lastSaved.current = snapshot;
            savedBehaviour.current = behaviourJson;
            if (aiApiKey) setHasSavedKey(true);
            setSaveState(latest.current === snapshot ? "saved" : "dirty"); // edited while saving: the next save follows
        } catch {
            setSaveState("error");
        }
    }, [snapshot, id, botName, instructions, knowledge, aiProvider, aiModel, aiApiKey, visual, behaviour, flowNodes, flowEdges]);

    useEffect(() => {
        if (loading || loadError) return;
        if (snapshot === lastSaved.current) {
            setSaveState((s) => (s === "saving" ? s : "saved"));
            return;
        }
        setSaveState((s) => (s === "error" ? s : "dirty"));
        const t = setTimeout(persist, 1000);
        return () => clearTimeout(t);
    }, [snapshot, persist, loading, loadError]);

    // Ctrl/⌘+S saves now; leaving with unsaved changes asks first.
    useEffect(() => {
        const onKey = (e: KeyboardEvent) => {
            if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "s") { e.preventDefault(); persist(); }
        };
        const onLeave = (e: BeforeUnloadEvent) => {
            if (saveState === "dirty" || saveState === "saving" || saveState === "error") { e.preventDefault(); e.returnValue = ""; }
        };
        window.addEventListener("keydown", onKey);
        window.addEventListener("beforeunload", onLeave);
        return () => { window.removeEventListener("keydown", onKey); window.removeEventListener("beforeunload", onLeave); };
    }, [persist, saveState]);

    const refreshKnowledge = useCallback(async () => {
        const res = await apiFetch(`/api/bots/${id}/config`);
        if (!res.ok) return knowledge;
        const text: string = (await res.json()).knowledge_base || "";
        setKnowledge(text);
        return text;
    }, [id, knowledge]);

    // ── Flow handlers ───────────────────────────────────────────────
    const onConnect = useCallback((c: Connection) => setFlowEdges((eds) => addEdge({
        ...c, type: "animated", style: { stroke: "#550a64", strokeWidth: 2 }, markerEnd: { type: MarkerType.ArrowClosed, color: "#550a64" },
    }, eds)), [setFlowEdges]);
    const onFlowSave = useCallback((nodes: Node[], edges: Edge[]) => { setFlowNodes(nodes); setFlowEdges(edges); }, [setFlowNodes, setFlowEdges]);
    const onNodeUpdate = useCallback((nodeId: string, data: any) => {
        setFlowNodes((nodes) => nodes.map((n) => (n.id === nodeId ? { ...n, data: { ...n.data, ...data } } : n)));
    }, [setFlowNodes]);
    const onNodeDelete = useCallback((nodeId: string) => {
        setFlowNodes((nodes) => nodes.filter((n) => n.id !== nodeId));
        setFlowEdges((edges) => edges.filter((e) => e.source !== nodeId && e.target !== nodeId));
        setSelectedNode(null);
    }, [setFlowNodes, setFlowEdges]);

    const font = fontStylesheet(visual.font_family);

    return (
        <div className="h-screen flex flex-col bg-paper text-ink">
            {font && <link rel="stylesheet" href={font} />}

            {/* Top bar */}
            <header className="h-14 shrink-0 bg-white border-b border-line flex items-center gap-2 sm:gap-3 px-2 sm:px-4">
                <Link href="/dashboard" aria-label="Back to assistants" className="p-2 rounded-md text-stone-500 hover:text-ink hover:bg-stone-100">
                    <ArrowLeft size={18} />
                </Link>
                <div className="flex items-center gap-2.5 min-w-0">
                    <span className="h-7 w-7 shrink-0 rounded-full border border-line bg-stone-50 overflow-hidden flex items-center justify-center text-[12px] font-semibold text-stone-500">
                        {visual.logo_url ? <img src={assetUrl(visual.logo_url)} alt="" className="h-full w-full object-cover object-top" /> : (botName || "A").slice(0, 1).toUpperCase()}
                    </span>
                    <span className="text-sm font-semibold truncate max-w-[9rem] sm:max-w-[14rem]">{loading ? "Loading…" : botName || "Untitled assistant"}</span>
                </div>

                <nav aria-label="Builder sections" className="hidden md:flex items-stretch self-stretch mx-auto">
                    {TABS.map((t) => (
                        <button key={t.id} type="button" onClick={() => setTab(t.id)} aria-current={tab === t.id ? "page" : undefined}
                                className={cn("relative px-3.5 text-[13px] transition-colors", tab === t.id ? "text-ink font-medium" : "text-stone-500 hover:text-ink")}>
                            {t.label}
                            {tab === t.id && <span className="absolute inset-x-3 bottom-0 h-0.5 rounded-full bg-plum" />}
                        </button>
                    ))}
                </nav>

                <div className="ml-auto md:ml-0 flex items-center gap-2">
                    <SaveStatus state={saveState} onRetry={persist} />
                    <Link href={`/demo/${id}`} target="_blank"
                          className="hidden sm:inline-flex items-center gap-1.5 h-8 px-3 rounded-md border border-line-strong bg-white text-[13px] font-medium text-ink hover:bg-stone-50">
                        <Play size={13} /> Test
                    </Link>
                    <Button size="sm" variant="primary" onClick={() => setShowExport(true)}>
                        <Code2 size={14} /> <span className="hidden sm:inline">Add to website</span><span className="sm:hidden">Install</span>
                    </Button>
                </div>
            </header>

            {/* Tabs on small screens */}
            <nav aria-label="Builder sections" className="md:hidden flex overflow-x-auto bg-white border-b border-line px-2 [scrollbar-width:none]">
                {TABS.map((t) => (
                    <button key={t.id} type="button" onClick={() => setTab(t.id)} aria-current={tab === t.id ? "page" : undefined}
                            className={cn("relative shrink-0 h-11 px-3 text-[13px]", tab === t.id ? "text-ink font-medium" : "text-stone-500")}>
                        {t.label}
                        {tab === t.id && <span className="absolute inset-x-2 bottom-0 h-0.5 rounded-full bg-plum" />}
                    </button>
                ))}
            </nav>

            {loadError ? (
                <div className="flex-1 flex items-center justify-center p-6 text-center">
                    <div>
                        <p className="text-sm font-medium">Couldn&apos;t load this assistant</p>
                        <p className="text-[13px] text-stone-500 mt-1">It may have been deleted, or the connection dropped.</p>
                        <div className="mt-4 flex justify-center gap-2">
                            <Button size="sm" onClick={() => { setLoading(true); load(); }}>Try again</Button>
                            <Link href="/dashboard" className="inline-flex items-center h-8 px-3 rounded-md text-[13px] text-stone-600 hover:text-ink">Back to assistants</Link>
                        </div>
                    </div>
                </div>
            ) : tab === "leads" ? (
                <div className="flex-1 overflow-y-auto"><LeadsPanel botId={id} botName={botName} /></div>
            ) : tab === "flow" ? (
                <div className="flex-1 min-h-0 flex">
                    <aside className="hidden md:block w-72 shrink-0 bg-white border-r border-line overflow-y-auto p-4">
                        <ElementsSidebar />
                    </aside>
                    <main className="flex-1 min-w-0 p-3">
                        <FlowBuilder botId={id} nodes={flowNodes} edges={flowEdges} onNodesChange={onNodesChange} onEdgesChange={onEdgesChange}
                                     onConnect={onConnect} onSave={onFlowSave} onNodeSelect={setSelectedNode} />
                    </main>
                    <aside className="hidden lg:block w-80 shrink-0 bg-white border-l border-line overflow-y-auto p-4">
                        {selectedNode ? (
                            <PropertiesPanel node={selectedNode} onUpdate={onNodeUpdate} onDelete={onNodeDelete} onClose={() => setSelectedNode(null)} />
                        ) : (
                            <div className="pt-2">
                                <p className="text-sm font-medium">Block settings</p>
                                <p className="text-[13px] text-stone-500 mt-1 leading-relaxed">Select a block on the canvas to edit what it says or asks. Flows run before the AI takes over.</p>
                            </div>
                        )}
                    </aside>
                </div>
            ) : (
                <div className="flex-1 min-h-0 flex">
                    <aside className={cn("w-full lg:w-[440px] xl:w-[480px] shrink-0 bg-white border-r border-line overflow-y-auto", mobilePreview && "hidden lg:block")}>
                        <div className="px-5 sm:px-6 py-5 pb-24 lg:pb-8">
                            {loading ? (
                                <div className="space-y-4">{[0, 1, 2, 3, 4, 5].map((i) => <Skeleton key={i} className="h-10" />)}</div>
                            ) : tab === "design" ? (
                                <DesignPanel botId={id} visual={visual} set={setDesign} botName={botName} setBotName={setBotName} />
                            ) : tab === "knowledge" ? (
                                <KnowledgePanel botId={id} provider={aiProvider} setProvider={setAiProvider} model={aiModel} setModel={setAiModel}
                                                apiKey={aiApiKey} setApiKey={setAiApiKey} hasSavedKey={hasSavedKey}
                                                knowledge={knowledge} setKnowledge={setKnowledge} refreshKnowledge={refreshKnowledge} saved={saveState === "saved"} />
                            ) : (
                                <BehaviourPanel instructions={instructions} setInstructions={setInstructions} behaviour={behaviour} setBehaviour={setBehaviour}
                                                rateAnswers={visual.answer_feedback} setRateAnswers={(on) => setDesign({ answer_feedback: on })} />
                            )}
                        </div>
                    </aside>

                    <main className={cn("flex-1 min-w-0 flex-col bg-[#f3f2ef]", mobilePreview ? "flex" : "hidden lg:flex")}>
                        {tab !== "design" ? (
                            loading ? <div className="p-8 h-full"><Skeleton className="h-full w-full rounded-xl" /></div>
                                : <TestChat botId={id} saving={saveState !== "saved"} />
                        ) : (
                            <>
                                <div className="h-12 shrink-0 flex items-center justify-between gap-3 px-4 border-b border-line bg-white/70">
                                    <Segmented label="Device" value={device} onChange={setDevice}
                                               options={[{ value: "desktop", label: "Desktop" }, { value: "mobile", label: "Phone" }]} />
                                    <span className="hidden xl:inline text-[12px] text-stone-500">Preview updates as you edit</span>
                                    <Segmented label="Chat window" value={chatOpen} onChange={setChatOpen}
                                               options={[{ value: "open", label: "Chat open" }, { value: "closed", label: "Launcher" }]} />
                                </div>
                                <div className="flex-1 min-h-0 p-5 sm:p-8">
                                    {loading ? <Skeleton className="h-full w-full rounded-xl" /> : (
                                        <WidgetPreview visual={visual} botName={botName} device={device} open={chatOpen === "open"} callbacks={callbacks} />
                                    )}
                                </div>
                            </>
                        )}
                    </main>

                    <button type="button" onClick={() => setMobilePreview((p) => !p)}
                            className="lg:hidden fixed bottom-4 right-4 z-30 inline-flex items-center gap-1.5 h-10 px-4 rounded-full bg-ink text-white text-[13px] font-medium shadow-lg">
                        {mobilePreview ? <><PencilLine size={14} /> Edit</> : <><Eye size={14} /> {tab === "design" ? "Preview" : "Test"}</>}
                    </button>
                </div>
            )}

            {showExport && (
                <div className="fixed inset-0 z-[90]">
                    <ExportModal botId={id} botName={botName || undefined} onClose={() => setShowExport(false)} />
                </div>
            )}
        </div>
    );
}

function SaveStatus({ state, onRetry }: { state: SaveState; onRetry: () => void }) {
    if (state === "error") {
        return (
            <button type="button" onClick={onRetry} className="text-[12px] text-signal hover:underline underline-offset-2 px-1 whitespace-nowrap">
                Couldn&apos;t save · Retry
            </button>
        );
    }
    return (
        <span aria-live="polite" className="hidden sm:inline-flex items-center gap-1 text-[12px] text-stone-500 px-1 whitespace-nowrap">
            {state === "saved" ? <><Check size={13} className="text-emerald-600" /> Saved</> : state === "saving" ? "Saving…" : "Unsaved changes"}
        </span>
    );
}

export default function BuilderPage(props: { params: Promise<{ id: string }> }) {
    return (
        <Suspense fallback={<div className="h-screen bg-paper" />}>
            <ToastProvider>
                <Builder {...props} />
            </ToastProvider>
        </Suspense>
    );
}
