"use client";

import { useEffect, useId, useRef, useState } from "react";
import Link from "next/link";
import { ArrowDown, ArrowUp, Monitor, Plus, RotateCcw, Send, Smartphone, Trash2, X } from "lucide-react";
import { Button, Dialog, Input, Select, Switch, Textarea, cn, useToast } from "@/components/ui";
import { apiJson } from "@/lib/api";
import {
    ACTION_LABEL, BLOCK_LABEL,
    type AssistantEmails, type Block, type ButtonAction, type Design, type EmailKind, type Language, type Preview,
} from "@/lib/email";

type FileRow = { id: string; name: string; bot_id?: string | null };
type Welcome = AssistantEmails["settings"]["welcome"];

/** The blocks each kind of email can have (backend mail/designs.py). */
const ADDABLE: Record<EmailKind, Block["type"][]> = {
    welcome: ["text", "heading", "ai_note", "files", "button", "details", "signature", "divider", "image"],
    after_call: ["text", "heading", "call_summary", "files", "button", "signature", "divider", "image"],
    meeting: ["text", "heading", "meeting", "button", "signature", "divider", "image"],
    callback_booked: ["text", "heading", "button", "signature", "divider", "image"],
    voicemail: ["text", "heading", "button", "signature", "divider", "image"],
    missed_chat: ["text", "heading", "button", "signature", "divider", "image"],
    chat_copy: ["text", "heading", "transcript", "signature", "divider"],
    during_call: ["text", "heading", "ai_note", "files", "signature", "divider"],
};

const ABOUT: Partial<Record<Block["type"], string>> = {
    call_summary: "What you talked about, the answers to their questions and the next step, written by the AI from the call.",
    meeting: "When the meeting is, and where or how to join.",
    details: "What they told your assistant: their name, what they want, their budget...",
    transcript: "Their chat, message by message.",
    signature: "Signed with the name the email comes from (Email > Settings).",
    divider: "A thin line between parts of the email.",
};

function blank(type: Block["type"]): Block {
    switch (type) {
        case "text": return { type, text: "" };
        case "heading": return { type, text: "" };
        case "ai_note": return { type, guidance: "" };
        case "button": return { type, label: "", action: "link", url: "" };
        case "image": return { type, url: "", alt: "" };
        default: return { type } as Block;
    }
}

export function DesignEditor({ open, onClose, botId, botName, kind, label, placeholders, languages, growth, setup, onSetup }: {
    open: boolean; onClose: () => void; botId: string; botName: string; kind: EmailKind; label: string;
    placeholders: string[]; languages: Language[]; growth: boolean;
    setup: AssistantEmails; onSetup: (s: AssistantEmails) => void;
}) {
    const toast = useToast();
    const titleId = useId();
    const panel = useRef<HTMLDivElement>(null);
    const [language, setLanguage] = useState<Language>("en");
    const [design, setDesign] = useState<Design | null>(null);
    const [base, setBase] = useState("");
    const [welcome, setWelcome] = useState<Welcome>(setup.settings.welcome);
    const [preview, setPreview] = useState<Preview | null>(null);
    const [width, setWidth] = useState<"desktop" | "phone">("desktop");
    const [busy, setBusy] = useState<"save" | "test" | "reset" | null>(null);
    const [files, setFiles] = useState<FileRow[]>([]);
    const [leaving, setLeaving] = useState(false);
    const texts = useRef<Record<number, HTMLTextAreaElement | null>>({});
    const saved = setup.kinds.find((k) => k.kind === kind)?.saved ?? [];

    const dirty = !!design && (JSON.stringify({ s: design.subject, b: design.blocks }) !== base ||
        (kind === "welcome" && JSON.stringify(welcome) !== JSON.stringify(setup.settings.welcome)));

    useEffect(() => {
        if (!open) return;
        setDesign(null);
        apiJson<Design>(`/api/email/designs/${botId}/${kind}?language=${language}`)
            .then((d) => { setDesign(d); setBase(JSON.stringify({ s: d.subject, b: d.blocks })); })
            .catch((e) => toast((e as Error).message));
    }, [open, botId, kind, language, toast]);

    useEffect(() => { if (open) { setWelcome(setup.settings.welcome); panel.current?.focus(); } }, [open, setup.settings.welcome]);

    useEffect(() => {
        if (!open || kind !== "welcome") return;
        apiJson<FileRow[]>("/api/whatsapp/files").then((rows) => setFiles(rows.filter((f) => !f.bot_id || f.bot_id === botId)))
            .catch(() => setFiles([]));
    }, [open, kind, botId]);

    // The preview follows the edits, a moment after typing stops.
    useEffect(() => {
        if (!open || !design) return;
        const t = setTimeout(() => {
            apiJson<Preview>(`/api/email/designs/${botId}/${kind}/preview`, {
                method: "POST", json: { language, subject: design.subject, blocks: design.blocks },
            }).then(setPreview).catch(() => {});
        }, 400);
        return () => clearTimeout(t);
    }, [open, botId, kind, language, design]);

    useEffect(() => {
        if (!open) return;
        const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") leave(); };
        document.addEventListener("keydown", onKey);
        return () => document.removeEventListener("keydown", onKey);
    });

    if (!open) return null;

    const leave = () => (dirty ? setLeaving(true) : onClose());
    const setBlocks = (blocks: Block[]) => design && setDesign({ ...design, blocks });
    const update = (i: number, patch: Partial<Block>) => design && setBlocks(design.blocks.map((b, n) => (n === i ? ({ ...b, ...patch } as Block) : b)));
    const move = (i: number, by: -1 | 1) => {
        if (!design) return;
        const next = [...design.blocks];
        const [b] = next.splice(i, 1);
        next.splice(i + by, 0, b);
        setBlocks(next);
    };
    const insert = (i: number, name: string) => {
        const el = texts.current[i];
        const block = design?.blocks[i];
        if (!block || !("text" in block)) return;
        const token = `{{${name}}}`;
        const start = el?.selectionStart ?? block.text.length;
        const end = el?.selectionEnd ?? start;
        update(i, { text: block.text.slice(0, start) + token + block.text.slice(end) });
        requestAnimationFrame(() => { el?.focus(); el?.setSelectionRange(start + token.length, start + token.length); });
    };

    const save = async () => {
        if (!design) return;
        setBusy("save");
        try {
            const next = await apiJson<Design>(`/api/email/designs/${botId}/${kind}`, {
                method: "PUT", json: { language, subject: design.subject, blocks: design.blocks },
            });
            setDesign(next);
            setBase(JSON.stringify({ s: next.subject, b: next.blocks }));
            if (kind === "welcome" && JSON.stringify(welcome) !== JSON.stringify(setup.settings.welcome)) {
                onSetup(await apiJson<AssistantEmails>(`/api/email/setup/${botId}`, { method: "PUT", json: { settings: { welcome } } }));
            } else {
                onSetup({ ...setup, kinds: setup.kinds.map((k) => (k.kind === kind ? { ...k, saved: [...new Set([...k.saved, language])] } : k)) });
            }
            toast("Saved");
        } catch (e) {
            toast((e as Error).message);
        } finally {
            setBusy(null);
        }
    };

    const reset = async () => {
        setBusy("reset");
        try {
            const next = await apiJson<Design>(`/api/email/designs/${botId}/${kind}?language=${language}`, { method: "DELETE" });
            setDesign(next);
            setBase(JSON.stringify({ s: next.subject, b: next.blocks }));
            onSetup({ ...setup, kinds: setup.kinds.map((k) => (k.kind === kind ? { ...k, saved: k.saved.filter((l) => l !== language) } : k)) });
            toast("Back to the ready-made design");
        } catch (e) {
            toast((e as Error).message);
        } finally {
            setBusy(null);
        }
    };

    const test = async () => {
        if (!design) return;
        setBusy("test");
        try {
            const r = await apiJson<{ to: string }>(`/api/email/designs/${botId}/${kind}/test`, {
                method: "POST", json: { language, subject: design.subject, blocks: design.blocks },
            });
            toast(`Test sent to ${r.to}, with sample details`);
        } catch (e) {
            toast((e as Error).message);
        } finally {
            setBusy(null);
        }
    };

    return (
        <div ref={panel} tabIndex={-1} role="dialog" aria-modal="true" aria-labelledby={titleId}
             className="fixed inset-0 z-50 flex flex-col bg-paper outline-none">
            <header className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 sm:px-6 py-3 border-b border-line bg-white">
                <div className="min-w-0 flex-1">
                    <h2 id={titleId} className="text-[15px] font-semibold truncate">{label}</h2>
                    <p className="text-[13px] text-stone-500 truncate">{botName}</p>
                </div>
                {languages.length > 1 && (
                    <div role="group" aria-label="Language" className="inline-flex rounded-md border border-line p-0.5 bg-paper">
                        {languages.map((l) => (
                            <button key={l} type="button" aria-pressed={language === l} onClick={() => setLanguage(l)}
                                    className={cn("h-7 px-3 rounded text-[13px] focus-visible:outline-2 focus-visible:outline-plum",
                                        language === l ? "bg-white shadow-[0_1px_2px_rgba(28,23,25,0.08)] text-ink font-medium" : "text-stone-500 hover:text-ink")}>
                                {setup.languages[l]}{saved.includes(l) && <span className="text-plum" aria-label=", saved"> ·</span>}
                            </button>
                        ))}
                    </div>
                )}
                <Button size="sm" variant="ghost" onClick={reset} disabled={!design?.saved || busy !== null}>
                    <RotateCcw size={13} aria-hidden /> Ready-made design
                </Button>
                <button type="button" onClick={leave} aria-label="Close"
                        className="p-1 rounded text-stone-400 hover:text-ink focus-visible:outline-2 focus-visible:outline-plum">
                    <X size={18} />
                </button>
            </header>

            <div className="flex-1 min-h-0 overflow-y-auto lg:overflow-hidden lg:grid lg:grid-cols-[minmax(0,34rem)_minmax(0,1fr)]">
                <section aria-label="Edit the email" className="lg:overflow-y-auto bg-white lg:border-r border-line p-4 sm:p-6 space-y-4">
                    {!design ? <p className="text-sm text-stone-500">Loading…</p> : (
                        <>
                            <label className="block">
                                <span className="text-xs text-stone-500">Subject</span>
                                <Input className="mt-1" maxLength={200} value={design.subject} onChange={(e) => setDesign({ ...design, subject: e.target.value })} />
                            </label>
                            <ol className="space-y-3" aria-label="Blocks, top to bottom">
                                {design.blocks.map((b, i) => (
                                    <li key={i} className="rounded-md border border-line bg-paper/60">
                                        <div className="flex items-center gap-1 px-3 py-2 border-b border-line">
                                            <span className="text-xs font-medium text-stone-600 flex-1">{BLOCK_LABEL[b.type]}</span>
                                            <IconButton label={`Move ${BLOCK_LABEL[b.type]} up`} disabled={i === 0} onClick={() => move(i, -1)}><ArrowUp size={13} /></IconButton>
                                            <IconButton label={`Move ${BLOCK_LABEL[b.type]} down`} disabled={i === design.blocks.length - 1} onClick={() => move(i, 1)}><ArrowDown size={13} /></IconButton>
                                            <IconButton label={`Remove ${BLOCK_LABEL[b.type]}`} onClick={() => setBlocks(design.blocks.filter((_, n) => n !== i))}><Trash2 size={13} /></IconButton>
                                        </div>
                                        <div className="p-3">
                                            <BlockEditor block={b} index={i} update={update} insert={insert} texts={texts} placeholders={placeholders}
                                                         kind={kind} growth={growth} welcome={welcome} setWelcome={setWelcome} files={files} />
                                        </div>
                                    </li>
                                ))}
                            </ol>
                            <AddBlock kinds={ADDABLE[kind]} onAdd={(t) => setBlocks([...design.blocks, blank(t)])} />
                        </>
                    )}
                </section>

                <section aria-label="Preview" className="lg:overflow-y-auto p-4 sm:p-6">
                    <div className="flex flex-wrap items-center gap-3 mb-3">
                        <div className="min-w-0 flex-1 text-[13px]">
                            {preview && <p className="truncate"><span className="text-stone-500">From </span>{preview.from}</p>}
                            {preview?.reply_to && <p className="truncate"><span className="text-stone-500">Replies to </span>{preview.reply_to}</p>}
                        </div>
                        <div role="group" aria-label="Preview width" className="inline-flex rounded-md border border-line p-0.5 bg-white">
                            <IconToggle label="As on a computer" on={width === "desktop"} onClick={() => setWidth("desktop")}><Monitor size={14} /></IconToggle>
                            <IconToggle label="As on a phone" on={width === "phone"} onClick={() => setWidth("phone")}><Smartphone size={14} /></IconToggle>
                        </div>
                    </div>
                    {preview && <p className="text-[13px] mb-2"><span className="text-stone-500">Subject </span><span className="font-medium">{preview.subject}</span></p>}
                    {preview?.too_big && <p className="text-[13px] text-amber-700 mb-2">This email is long: Gmail may cut it short. Remove an image or some text.</p>}
                    <div className={cn("mx-auto transition-[max-width]", width === "phone" ? "max-w-[390px]" : "max-w-none")}>
                        <iframe title="Email preview, with sample details" sandbox="" srcDoc={preview?.html ?? ""}
                                className="w-full h-[70vh] min-h-[480px] rounded-md border border-line bg-white" />
                    </div>
                    <p className="text-xs text-stone-500 mt-2">With sample details. Real emails use each person&apos;s own.</p>
                </section>
            </div>

            <footer className="flex flex-wrap items-center justify-end gap-2 px-4 sm:px-6 py-3 border-t border-line bg-white">
                <Button variant="ghost" onClick={test} disabled={!design || busy !== null}>
                    <Send size={13} aria-hidden /> {busy === "test" ? "Sending…" : "Send me a test"}
                </Button>
                <Button onClick={leave}>Close</Button>
                <Button variant="primary" onClick={save} disabled={!dirty || busy !== null}>{busy === "save" ? "Saving…" : "Save"}</Button>
            </footer>

            <Dialog open={leaving} onClose={() => setLeaving(false)} title="Leave without saving?"
                    description="Your changes to this email haven't been saved."
                    footer={<>
                        <Button variant="ghost" onClick={() => setLeaving(false)}>Keep editing</Button>
                        <Button variant="danger" onClick={() => { setLeaving(false); onClose(); }}>Discard changes</Button>
                    </>}>
                <p className="text-[13px] text-stone-600">Saved emails go out as they were before.</p>
            </Dialog>
        </div>
    );
}

function BlockEditor({ block: b, index: i, update, insert, texts, placeholders, kind, growth, welcome, setWelcome, files }: {
    block: Block; index: number; update: (i: number, p: Partial<Block>) => void; insert: (i: number, name: string) => void;
    texts: React.MutableRefObject<Record<number, HTMLTextAreaElement | null>>; placeholders: string[]; kind: EmailKind;
    growth: boolean; welcome: Welcome; setWelcome: (w: Welcome) => void; files: FileRow[];
}) {
    if (b.type === "text") {
        return (
            <>
                <Textarea ref={(el) => { texts.current[i] = el; }} aria-label="Text" rows={5} maxLength={5000} className="leading-relaxed"
                          value={b.text} onChange={(e) => update(i, { text: e.target.value })} />
                <div className="flex flex-wrap items-center gap-1.5 mt-2">
                    <span className="text-xs text-stone-500 mr-1">Insert</span>
                    {placeholders.map((p) => (
                        <button key={p} type="button" onClick={() => insert(i, p)}
                                className="h-6 px-2 rounded bg-plum-tint text-plum text-xs hover:bg-plum hover:text-white focus-visible:outline-2 focus-visible:outline-plum">
                            {p}
                        </button>
                    ))}
                </div>
                <p className="text-xs text-stone-500 mt-2">A fallback after a bar is used when it&apos;s not known: {"{{first_name|there}}"}.</p>
            </>
        );
    }
    if (b.type === "heading") {
        return <Input aria-label="Heading" maxLength={200} value={b.text} onChange={(e) => update(i, { text: e.target.value })} />;
    }
    if (b.type === "ai_note") {
        return (
            <div className="space-y-2">
                <p className="text-[13px] text-stone-600">
                    A sentence or two the AI writes for each person from their {kind === "during_call" ? "call" : "chat"}, using only your
                    knowledge: no prices or numbers it can&apos;t find there. Counts as one AI reply.
                </p>
                {kind === "welcome" && (
                    <div className="flex items-center justify-between gap-3">
                        <span className="text-[13px]">The AI writes it</span>
                        <Switch checked={welcome.ai_note && growth} disabled={!growth} onChange={(v) => setWelcome({ ...welcome, ai_note: v })} label="The AI writes a note" />
                    </div>
                )}
                <label className="block">
                    <span className="text-xs text-stone-500">What it should talk about (optional)</span>
                    <Input className="mt-1" maxLength={500} placeholder="e.g. Mention our free site visits on weekends"
                           value={b.guidance ?? ""} onChange={(e) => update(i, { guidance: e.target.value })} />
                </label>
                {!growth && <p className="text-xs text-amber-700">The AI&apos;s note comes with Growth or Pro: on your plan this block is left out.</p>}
            </div>
        );
    }
    if (b.type === "files") {
        if (kind !== "welcome") return <p className="text-[13px] text-stone-600">The files sent with this email, with a download link each.</p>;
        const toggle = (id: string) => setWelcome({ ...welcome, files: welcome.files.includes(id) ? welcome.files.filter((x) => x !== id) : [...welcome.files, id] });
        return (
            <div className="space-y-3">
                <div className="flex items-center justify-between gap-3">
                    <span className="text-[13px]">Add the files that fit their chat (the AI picks)</span>
                    <Switch checked={welcome.ai_files && growth} disabled={!growth} onChange={(v) => setWelcome({ ...welcome, ai_files: v })} label="The AI picks files" />
                </div>
                <label className="flex items-center justify-between gap-3 text-[13px]">
                    <span>At most</span>
                    <Select className="w-24" value={welcome.max_files} disabled={!growth}
                            onChange={(e) => setWelcome({ ...welcome, max_files: Number(e.target.value) })}>
                        {[1, 2, 3, 4].map((n) => <option key={n} value={n}>{n} {n === 1 ? "file" : "files"}</option>)}
                    </Select>
                </label>
                {files.length > 0 ? (
                    <fieldset>
                        <legend className="text-xs text-stone-500 mb-1">Always send</legend>
                        <ul className="space-y-1">
                            {files.map((f) => (
                                <li key={f.id}>
                                    <label className="flex items-center gap-2 text-[13px]">
                                        <input type="checkbox" className="accent-plum" checked={welcome.files.includes(f.id)} disabled={!growth} onChange={() => toggle(f.id)} />
                                        {f.name}
                                    </label>
                                </li>
                            ))}
                        </ul>
                    </fieldset>
                ) : (
                    <p className="text-[13px] text-stone-600">
                        No files yet. Add your brochure or price list in <Link href="/dashboard/whatsapp/files" className="text-plum hover:underline">Files</Link>,
                        with when to send each.
                    </p>
                )}
                {!growth && <p className="text-xs text-amber-700">Files come with Growth or Pro: on your plan this block is left out.</p>}
            </div>
        );
    }
    if (b.type === "button") {
        const actions = (Object.keys(ACTION_LABEL) as ButtonAction[]).filter((a) => kind === "meeting" || !["join", "change", "cancel"].includes(a));
        return (
            <div className="grid sm:grid-cols-2 gap-2">
                <label className="block">
                    <span className="text-xs text-stone-500">Label</span>
                    <Input className="mt-1" maxLength={60} value={b.label} onChange={(e) => update(i, { label: e.target.value })} />
                </label>
                <label className="block">
                    <span className="text-xs text-stone-500">Opens</span>
                    <Select className="mt-1" value={b.action} onChange={(e) => update(i, { action: e.target.value as ButtonAction })}>
                        {actions.map((a) => <option key={a} value={a}>{ACTION_LABEL[a]}</option>)}
                    </Select>
                </label>
                {b.action === "link" ? (
                    <label className="block sm:col-span-2">
                        <span className="text-xs text-stone-500">Address</span>
                        <Input className="mt-1" type="url" maxLength={500} placeholder="https://" value={b.url ?? ""} onChange={(e) => update(i, { url: e.target.value })} />
                    </label>
                ) : (
                    <p className="sm:col-span-2 text-xs text-stone-500">
                        {b.action === "whatsapp" ? "Your WhatsApp number, when one is connected to this assistant. Otherwise the button is left out."
                            : b.action === "book" || b.action === "call" ? "Left out of emails for now: the page it opens isn't ready yet."
                                : "Filled in for each meeting."}
                    </p>
                )}
            </div>
        );
    }
    if (b.type === "image") {
        return (
            <div className="space-y-2">
                <label className="block">
                    <span className="text-xs text-stone-500">Image address (PNG or JPEG)</span>
                    <Input className="mt-1" type="url" maxLength={500} placeholder="https://" value={b.url} onChange={(e) => update(i, { url: e.target.value })} />
                </label>
                <label className="block">
                    <span className="text-xs text-stone-500">Describe it, for people who can&apos;t see images</span>
                    <Input className="mt-1" maxLength={200} value={b.alt ?? ""} onChange={(e) => update(i, { alt: e.target.value })} />
                </label>
            </div>
        );
    }
    return <p className="text-[13px] text-stone-600">{ABOUT[b.type] ?? ""}</p>;
}

function AddBlock({ kinds, onAdd }: { kinds: Block["type"][]; onAdd: (t: Block["type"]) => void }) {
    const [value, setValue] = useState("");
    return (
        <div className="flex items-center gap-2">
            <Select aria-label="Block to add" className="w-56" value={value} onChange={(e) => setValue(e.target.value)}>
                <option value="">Add a block…</option>
                {kinds.map((k) => <option key={k} value={k}>{BLOCK_LABEL[k]}</option>)}
            </Select>
            <Button size="sm" onClick={() => { if (value) { onAdd(value as Block["type"]); setValue(""); } }} disabled={!value}>
                <Plus size={13} aria-hidden /> Add
            </Button>
        </div>
    );
}

function IconButton({ label, onClick, disabled, children }: { label: string; onClick: () => void; disabled?: boolean; children: React.ReactNode }) {
    return (
        <button type="button" aria-label={label} title={label} onClick={onClick} disabled={disabled}
                className="p-1.5 rounded text-stone-500 hover:text-ink hover:bg-white disabled:opacity-30 disabled:hover:bg-transparent focus-visible:outline-2 focus-visible:outline-plum">
            {children}
        </button>
    );
}

function IconToggle({ label, on, onClick, children }: { label: string; on: boolean; onClick: () => void; children: React.ReactNode }) {
    return (
        <button type="button" aria-label={label} title={label} aria-pressed={on} onClick={onClick}
                className={cn("h-7 w-8 inline-flex items-center justify-center rounded focus-visible:outline-2 focus-visible:outline-plum",
                    on ? "bg-plum-tint text-plum" : "text-stone-500 hover:text-ink")}>
            {children}
        </button>
    );
}
