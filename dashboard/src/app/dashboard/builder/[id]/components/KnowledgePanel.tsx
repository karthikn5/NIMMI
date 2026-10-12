"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ArrowRight, FileText, Globe, PlayCircle, RefreshCw, Trash2, Upload } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { Button, Dialog, Input, Select, Status, Textarea, cn, useToast } from "@/components/ui";
import { Field, Section } from "./controls";

/** Providers the chat backend can actually call (see backend/utils.py). */
const MODELS: Record<string, { label: string; models: { value: string; label: string }[] }> = {
    google: { label: "Google Gemini", models: [
        { value: "gemini-3-flash-preview", label: "Gemini 3 Flash (preview)" },
        { value: "gemini-2.0-flash", label: "Gemini 2.0 Flash" },
    ] },
    openai: { label: "OpenAI", models: [
        { value: "gpt-4o-mini", label: "GPT-4o mini" },
        { value: "gpt-4o", label: "GPT-4o" },
    ] },
};

type Props = {
    botId: string;
    provider: string; setProvider: (v: string) => void;
    model: string; setModel: (v: string) => void;
    apiKey: string; setApiKey: (v: string) => void; hasSavedKey: boolean;
    knowledge: string; setKnowledge: (v: string) => void;
    /** Re-read the written knowledge after a source adds to it; resolves to the new text. */
    refreshKnowledge: () => Promise<string>;
    /** Every change is saved, so the server has the text we see. */
    saved: boolean;
};

type Busy = "website" | "youtube" | "file" | "source" | null;
type Source = { name: string; kind: "website" | "youtube" | "file"; chars: number };
const SOURCE_ICON = { website: Globe, youtube: PlayCircle, file: FileText };
const sourceLabel = (s: Source) => (s.kind === "file" ? s.name.replace(/^file: /, "") : s.name.replace(/^https?:\/\/(www\.)?/, ""));

export default function KnowledgePanel(p: Props) {
    const toast = useToast();
    const fileInput = useRef<HTMLInputElement>(null);
    const [url, setUrl] = useState("");
    const [video, setVideo] = useState("");
    const [busy, setBusy] = useState<Busy>(null);
    const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null);
    const [indexed, setIndexed] = useState<number | null>(null);
    const [pages, setPages] = useState("1");
    const [sources, setSources] = useState<Source[] | null>(null);
    const [removing, setRemoving] = useState<Source | null>(null);
    const [reindexing, setReindexing] = useState(false);
    const searchedText = useRef(p.knowledge); // the written knowledge the search index was built from

    const loadStats = useCallback(async () => {
        try {
            const res = await apiFetch(`/api/bots/${p.botId}/knowledge/stats`);
            if (res.ok) setIndexed((await res.json()).vector_count ?? 0);
        } catch { /* stats are a nice-to-have */ }
    }, [p.botId]);
    const loadSources = useCallback(async () => {
        try {
            const res = await apiFetch(`/api/bots/${p.botId}/knowledge/sources`);
            if (res.ok) setSources((await res.json()).sources);
        } catch { /* the list is optional */ }
    }, [p.botId]);
    useEffect(() => { loadStats(); loadSources(); }, [loadStats, loadSources]);

    const run = async (kind: Exclude<Busy, null>, call: () => Promise<Response>, success: string | ((data: any) => string)) => {
        setBusy(kind);
        setResult(null);
        try {
            const res = await call();
            const data = await res.json().catch(() => ({}));
            if (!res.ok || (data.status && data.status !== "success")) throw new Error(data.error || data.detail || "That didn't work. Check the link and try again.");
            searchedText.current = await p.refreshKnowledge(); // a source indexes the text it leaves behind
            await Promise.all([loadStats(), loadSources()]);
            setResult({ ok: true, text: typeof success === "function" ? success(data) : success });
            return true;
        } catch (e) {
            setResult({ ok: false, text: (e as Error).message });
            return false;
        } finally {
            setBusy(null);
        }
    };

    const json = (path: string, body: object) => apiFetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const addWebsite = async () => {
        if (!/^https?:\/\/\S+\.\S+/.test(url.trim())) return setResult({ ok: false, text: "Enter a full web address, starting with https://" });
        if (await run("website", () => json("/api/knowledge/crawl", { bot_id: p.botId, url: url.trim(), pages: Number(pages) }),
                      (d) => (d.pages > 1 ? `Read ${d.pages} pages. The assistant can now answer from them.` : "Page added. The assistant can now answer from it."))) setUrl("");
    };
    const addVideo = async () => {
        if (!/youtu\.?be/.test(video)) return setResult({ ok: false, text: "Enter a YouTube video link." });
        if (await run("youtube", () => json("/api/knowledge/youtube", { bot_id: p.botId, url: video.trim() }), "Video transcript added.")) setVideo("");
    };
    const refreshSource = (s: Source) =>
        run("source", () => json("/api/knowledge/crawl", { bot_id: p.botId, url: s.name, pages: 1 }), `${sourceLabel(s)} refreshed.`);
    const removeSource = async (s: Source) => {
        setRemoving(null);
        await run("source", () => apiFetch(`/api/bots/${p.botId}/knowledge/sources?name=${encodeURIComponent(s.name)}`, { method: "DELETE" }),
                  `${sourceLabel(s)} removed.`);
    };
    const addFile = async (file: File | undefined) => {
        if (!file) return;
        if (!/\.(pdf|txt)$/i.test(file.name)) return toast("Upload a PDF or a .txt file.");
        const form = new FormData();
        form.append("file", file);
        await run("file", () => apiFetch(`/api/bots/${p.botId}/knowledge/upload`, { method: "POST", body: form }), `${file.name} added.`);
    };

    const editedSinceIndex = (indexed ?? 0) > 0 && p.knowledge !== searchedText.current;
    const reindex = async () => {
        setReindexing(true);
        setResult(null);
        try {
            const res = await apiFetch(`/api/bots/${p.botId}/knowledge/reindex`, { method: "POST" });
            if (!res.ok) throw new Error();
            searchedText.current = p.knowledge;
            await loadStats();
            setResult({ ok: true, text: "Search updated with your latest edits." });
        } catch {
            setResult({ ok: false, text: "Couldn't update the search. Try again in a moment." });
        } finally {
            setReindexing(false);
        }
    };

    const provider = MODELS[p.provider];
    const words = p.knowledge.trim() ? p.knowledge.trim().split(/\s+/).length : 0;

    return (
        <div>
            <Section title="What it knows" description="Your assistant answers only from what you add here. Add your website, documents and anything customers often ask."
                     action={indexed !== null ? (
                         <Status tone={indexed > 0 || words > 0 ? "good" : "neutral"}>
                             {indexed > 0 ? `${indexed.toLocaleString("en-IN")} passages searchable` : words > 0 ? "Using written knowledge" : "Nothing added yet"}
                         </Status>
                     ) : undefined}>
                <div className="rounded-md border border-line divide-y divide-line">
                    <SourceRow icon={Globe} title="Website" hint="Reads the page, and optionally the pages it links to on the same site.">
                        <div className="flex gap-2">
                            <Input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://yourbusiness.com" inputMode="url"
                                   onKeyDown={(e) => e.key === "Enter" && addWebsite()} aria-label="Website address" />
                            <Button onClick={addWebsite} disabled={!!busy || !url.trim()}>{busy === "website" ? "Reading…" : "Add"}</Button>
                        </div>
                        <Select value={pages} onChange={(e) => setPages(e.target.value)} aria-label="How much to read" className="mt-2 w-auto">
                            <option value="1">Just this page</option>
                            <option value="10">This page and up to 9 linked pages</option>
                            <option value="25">This page and up to 24 linked pages</option>
                        </Select>
                    </SourceRow>
                    <SourceRow icon={PlayCircle} title="YouTube video" hint="Uses the video's captions.">
                        <div className="flex gap-2">
                            <Input value={video} onChange={(e) => setVideo(e.target.value)} placeholder="https://youtube.com/watch?v=…"
                                   onKeyDown={(e) => e.key === "Enter" && addVideo()} aria-label="YouTube link" />
                            <Button onClick={addVideo} disabled={!!busy || !video.trim()}>{busy === "youtube" ? "Reading…" : "Add"}</Button>
                        </div>
                    </SourceRow>
                    <SourceRow icon={FileText} title="Document" hint="PDF or plain text, such as a brochure, price list or policy.">
                        <Button onClick={() => fileInput.current?.click()} disabled={!!busy}>
                            <Upload size={14} /> {busy === "file" ? "Reading…" : "Upload a file"}
                        </Button>
                        <input ref={fileInput} type="file" accept=".pdf,.txt" className="hidden" onChange={(e) => { addFile(e.target.files?.[0]); e.target.value = ""; }} />
                    </SourceRow>
                </div>
                {result && (
                    <p role="status" className={cn("text-[13px]", result.ok ? "text-emerald-700" : "text-signal")}>{result.text}</p>
                )}
                {!!sources?.length && (
                    <div>
                        <p className="text-[13px] font-medium text-stone-700 mb-1.5">Added sources <span className="text-stone-400 font-normal">· {sources.length}</span></p>
                        <ul className="rounded-md border border-line divide-y divide-line max-h-72 overflow-y-auto">
                            {sources.map((src) => {
                                const Icon = SOURCE_ICON[src.kind];
                                return (
                                    <li key={src.name} className="flex items-center gap-3 px-3 py-2">
                                        <Icon size={14} className="text-stone-400 shrink-0" aria-hidden />
                                        <span className="min-w-0 flex-1">
                                            <span className="block text-[13px] text-ink truncate" title={src.name}>{sourceLabel(src)}</span>
                                            <span className="block text-[11px] text-stone-500">{src.chars.toLocaleString("en-IN")} characters</span>
                                        </span>
                                        {src.kind === "website" && (
                                            <button type="button" onClick={() => refreshSource(src)} disabled={!!busy} title="Read this page again"
                                                    className="p-1.5 rounded text-stone-400 hover:text-ink hover:bg-stone-100 disabled:opacity-40" aria-label={`Refresh ${sourceLabel(src)}`}>
                                                <RefreshCw size={14} />
                                            </button>
                                        )}
                                        <button type="button" onClick={() => setRemoving(src)} disabled={!!busy}
                                                className="p-1.5 rounded text-stone-400 hover:text-signal hover:bg-red-50 disabled:opacity-40" aria-label={`Remove ${sourceLabel(src)}`}>
                                            <Trash2 size={14} />
                                        </button>
                                    </li>
                                );
                            })}
                        </ul>
                    </div>
                )}
                <Dialog open={!!removing} onClose={() => setRemoving(null)} title="Remove this source?"
                        description={removing ? `${sourceLabel(removing)} will be removed, and the assistant will stop answering from it.` : undefined}
                        footer={<>
                            <Button variant="ghost" onClick={() => setRemoving(null)}>Cancel</Button>
                            <Button variant="danger" onClick={() => removing && removeSource(removing)}>Remove</Button>
                        </>}>
                    <p className="text-[13px] text-stone-600">You can add it again at any time.</p>
                </Dialog>
            </Section>

            <Section title="Written knowledge" description="Facts in your own words: prices, timings, policies, answers to common questions. Text from your sources also appears here, so you can correct it."
                     action={<span className="text-[12px] text-stone-500 tabular-nums whitespace-nowrap">{words.toLocaleString("en-IN")} words</span>}>
                <Textarea rows={12} value={p.knowledge} onChange={(e) => p.setKnowledge(e.target.value)}
                          placeholder={"e.g.\nOpening hours: Monday to Saturday, 9 AM to 7 PM.\n2BHK flats start at ₹58 lakhs.\nWe offer home loans with SBI and HDFC."}
                          className="text-[13px]" aria-label="Written knowledge" />
                {editedSinceIndex && (
                    <div className="flex items-center justify-between gap-3 rounded-md border border-line-strong px-3 py-2.5">
                        <p className="text-[13px] text-stone-600">Update the search so the assistant finds your edits.</p>
                        <Button size="sm" onClick={reindex} disabled={reindexing || !p.saved}>
                            {reindexing ? "Updating…" : !p.saved ? "Saving…" : "Update search"}
                        </Button>
                    </div>
                )}
            </Section>

            <Section title="Questions it couldn't answer">
                <Link href="/dashboard/questions" className="flex items-center justify-between gap-3 rounded-md border border-line px-4 py-3 hover:bg-stone-50 transition-colors">
                    <span className="text-[13px] text-stone-600">See what customers asked that it didn&apos;t know, and answer each one once.</span>
                    <ArrowRight size={16} className="text-stone-400 shrink-0" />
                </Link>
            </Section>

            <Section title="AI model" description="Leave the key empty to use Nimmi's own. Add yours to bill usage to your account.">
                {!provider && (
                    <p className="text-[13px] text-amber-700">The current provider ({p.provider}) isn&apos;t supported for chat. Choose one below.</p>
                )}
                <div className="grid grid-cols-2 gap-3">
                    <Field label="Provider" htmlFor="provider">
                        <Select id="provider" value={provider ? p.provider : ""} onChange={(e) => {
                            p.setProvider(e.target.value);
                            p.setModel(MODELS[e.target.value].models[0].value);
                        }}>
                            {!provider && <option value="" disabled>Choose…</option>}
                            {Object.entries(MODELS).map(([value, m]) => <option key={value} value={value}>{m.label}</option>)}
                        </Select>
                    </Field>
                    <Field label="Model" htmlFor="model">
                        <Select id="model" value={p.model} onChange={(e) => p.setModel(e.target.value)} disabled={!provider}>
                            {provider && !provider.models.some((m) => m.value === p.model) && <option value={p.model}>{p.model}</option>}
                            {provider?.models.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
                        </Select>
                    </Field>
                </div>
                <Field label="Your API key (optional)" htmlFor="api-key" aside={p.hasSavedKey && !p.apiKey ? "A key is saved" : undefined}>
                    <Input id="api-key" type="password" autoComplete="off" value={p.apiKey} onChange={(e) => p.setApiKey(e.target.value)}
                           placeholder={p.hasSavedKey ? "Enter a new key to replace the saved one" : `${provider?.label ?? "Provider"} API key`} />
                </Field>
            </Section>
        </div>
    );
}

function SourceRow({ icon: Icon, title, hint, children }: { icon: typeof Globe; title: string; hint: string; children: React.ReactNode }) {
    return (
        <div className="p-4">
            <div className="flex items-start gap-3 mb-3">
                <Icon size={16} className="text-stone-500 mt-0.5 shrink-0" aria-hidden />
                <div>
                    <p className="text-[13px] font-medium text-ink">{title}</p>
                    <p className="text-[12px] text-stone-500">{hint}</p>
                </div>
            </div>
            <div className="pl-7">{children}</div>
        </div>
    );
}
