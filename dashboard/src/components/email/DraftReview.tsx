"use client";

import { useCallback, useEffect, useId, useRef, useState } from "react";
import Link from "next/link";
import { Monitor, Plus, RefreshCw, Smartphone, Trash2, X } from "lucide-react";
import { Button, Dialog, Input, Notice, Textarea, cn, useToast } from "@/components/ui";
import { apiJson } from "@/lib/api";
import { type DraftAnswer, type DraftDetail } from "@/lib/email";
import { formatWhen } from "@/lib/voice/api";

type Form = { to: string; subject: string; recap: string; answers: DraftAnswer[]; next_step: string; file_ids: string[] };

const POINTS = 6;
const formOf = (d: DraftDetail): Form => ({ to: d.to, subject: d.subject, recap: d.recap.join("\n"), answers: d.answers, next_step: d.next_step, file_ids: d.file_ids });
const asSaved = (f: Form) => ({ ...f, recap: f.recap.split("\n").map((p) => p.trim()).filter(Boolean).slice(0, POINTS) });

/** One after-call email: what it says, as the customer will see it. Changes are saved as they're made. */
export function DraftReview({ id, onClose, onDone }: { id: string; onClose: () => void; onDone: () => void }) {
    const toast = useToast();
    const titleId = useId();
    const panel = useRef<HTMLDivElement>(null);
    const [draft, setDraft] = useState<DraftDetail | null>(null);
    const [form, setForm] = useState<Form | null>(null);
    const [gone, setGone] = useState<string | null>(null);
    const [problem, setProblem] = useState<string | null>(null);
    const [width, setWidth] = useState<"desktop" | "phone">("desktop");
    const [busy, setBusy] = useState<"send" | "discard" | "again" | null>(null);
    const [asking, setAsking] = useState<"discard" | "again" | null>(null);
    const made = useRef(0);    // changes made so far, and how many of them are saved
    const kept = useRef(0);
    const saving = useRef<Promise<unknown> | null>(null);

    const load = useCallback(async () => {
        try {
            const d = await apiJson<DraftDetail>(`/api/email/drafts/${id}`);
            setDraft(d);
            setForm(formOf(d));
            kept.current = made.current;
        } catch (e) {
            setGone((e as Error).message);
        }
    }, [id]);

    useEffect(() => { void load(); panel.current?.focus(); }, [load]);

    // The AI is still writing it: look again every few seconds.
    useEffect(() => {
        if (draft?.state !== "writing") return;
        const t = setInterval(() => { void load(); }, 3000);
        return () => clearInterval(t);
    }, [draft?.state, load]);

    /** One save at a time, in order. True when every change so far is saved. */
    const save = useCallback(async (f: Form) => {
        await saving.current;
        const upTo = made.current;
        if (upTo === kept.current) return true;
        const run = apiJson<DraftDetail>(`/api/email/drafts/${id}`, { method: "PUT", json: asSaved(f) }).then((d) => {
            setDraft(d);
            setProblem(null);
            kept.current = upTo;
        }).catch((e) => setProblem((e as Error).message));
        saving.current = run;
        await run;
        return kept.current === made.current;
    }, [id]);

    // Saved a moment after typing stops; the preview that comes back is the email as it stands.
    useEffect(() => {
        if (!form || made.current === kept.current) return;
        const t = setTimeout(() => { void save(form); }, 500);
        return () => clearTimeout(t);
    }, [form, save]);

    const close = useCallback(async () => {
        if (form) await save(form);
        onClose();
    }, [form, save, onClose]);

    useEffect(() => {
        const onKey = (e: KeyboardEvent) => { if (e.key === "Escape" && !asking) void close(); };
        document.addEventListener("keydown", onKey);
        return () => document.removeEventListener("keydown", onKey);
    }, [asking, close]);

    const change = (patch: Partial<Form>) => {
        if (!form) return;
        made.current += 1;
        setForm({ ...form, ...patch });
    };
    const setAnswer = (i: number, patch: Partial<DraftAnswer>) => form && change({ answers: form.answers.map((a, n) => (n === i ? { ...a, ...patch } : a)) });

    const act = async (kind: "send" | "discard" | "again") => {
        if (!form) return;
        setAsking(null);
        setBusy(kind);
        try {
            if (!await save(form) && kind === "send") {  // what's on the screen is what goes
                toast("Fix what's marked before sending");
                return;
            }
            if (kind === "again") {
                await apiJson(`/api/email/drafts/${id}/rewrite`, { method: "POST" });
                await load();
                return;
            }
            await apiJson(`/api/email/drafts/${id}/${kind === "send" ? "send" : "discard"}`, { method: "POST" });
            toast(kind === "send" ? `On its way to ${form.to}` : "Discarded");
            onDone();
        } catch (e) {
            toast((e as Error).message);
        } finally {
            setBusy(null);
        }
    };

    const writing = draft?.state === "writing";
    const who = draft?.name || draft?.to || "";
    return (
        <div ref={panel} tabIndex={-1} role="dialog" aria-modal="true" aria-labelledby={titleId} className="fixed inset-0 z-50 flex flex-col bg-paper outline-none">
            <header className="flex items-center gap-4 px-4 sm:px-6 py-3 border-b border-line bg-white">
                <div className="min-w-0 flex-1">
                    <h2 id={titleId} className="text-[15px] font-semibold truncate">{who ? `Email to ${who}` : "Email"}</h2>
                    {draft && (
                        <p className="text-[13px] text-stone-500 truncate">
                            {draft.bot_name} · {draft.direction === "inbound" ? "Incoming call" : "Outgoing call"}
                            {draft.created_at ? ` · ${formatWhen(draft.created_at)}` : ""}
                        </p>
                    )}
                </div>
                {draft && <Link href={`/dashboard/voice/calls?call=${draft.call_id}`} className="text-[13px] text-plum hover:underline whitespace-nowrap">Open the call</Link>}
                <button type="button" onClick={close} aria-label="Close" className="p-1 rounded text-stone-400 hover:text-ink focus-visible:outline-2 focus-visible:outline-plum">
                    <X size={18} />
                </button>
            </header>

            {gone ? <p className="p-6 text-sm text-stone-600">{gone}</p> : (
                <div className="flex-1 min-h-0 overflow-y-auto lg:overflow-hidden lg:grid lg:grid-cols-[minmax(0,34rem)_minmax(0,1fr)]">
                    <section aria-label="What the email says" className="lg:overflow-y-auto bg-white lg:border-r border-line p-4 sm:p-6 space-y-4">
                        {!draft || !form ? <p className="text-sm text-stone-500">Loading…</p> : writing ? (
                            <p className="text-sm text-stone-600" role="status">The AI is writing this email from the call. It takes a few seconds.</p>
                        ) : (
                            <>
                                {draft.note && <Notice title="Read this one before it goes" className="mb-0">{draft.note}</Notice>}
                                {draft.fixed && <p className="text-[13px] text-stone-600">The AI&apos;s check changed something: {draft.fixed}</p>}
                                <label className="block">
                                    <span className="text-xs text-stone-500">To</span>
                                    <Input className="mt-1" type="email" maxLength={200} value={form.to} onChange={(e) => change({ to: e.target.value })} />
                                </label>
                                <label className="block">
                                    <span className="text-xs text-stone-500">Subject</span>
                                    <Input className="mt-1" maxLength={200} placeholder={draft.shown_subject} value={form.subject} onChange={(e) => change({ subject: e.target.value })} />
                                </label>
                                <label className="block">
                                    <span className="text-xs text-stone-500">What you talked about, one point on each line</span>
                                    <Textarea className="mt-1" rows={4} value={form.recap} onChange={(e) => change({ recap: e.target.value })} />
                                </label>
                                <fieldset>
                                    <legend className="text-xs text-stone-500">Their questions</legend>
                                    <ul className="mt-1 space-y-2">
                                        {form.answers.map((a, i) => (
                                            <li key={i} className="rounded-md border border-line p-2.5 space-y-1.5">
                                                <div className="flex items-center gap-2">
                                                    <Input aria-label={`Question ${i + 1}`} maxLength={200} value={a.q} onChange={(e) => setAnswer(i, { q: e.target.value })} />
                                                    <button type="button" aria-label={`Remove question ${i + 1}`} onClick={() => change({ answers: form.answers.filter((_, n) => n !== i) })}
                                                            className="p-1.5 rounded text-stone-500 hover:text-ink focus-visible:outline-2 focus-visible:outline-plum">
                                                        <Trash2 size={13} />
                                                    </button>
                                                </div>
                                                <Textarea aria-label={`Answer ${i + 1}`} rows={2} maxLength={800} value={a.a} onChange={(e) => setAnswer(i, { a: e.target.value })} />
                                            </li>
                                        ))}
                                    </ul>
                                    {form.answers.length < 10 && (
                                        <Button size="sm" className="mt-2" onClick={() => change({ answers: [...form.answers, { q: "", a: "" }] })}><Plus size={13} aria-hidden /> Add a question</Button>
                                    )}
                                </fieldset>
                                {draft.unanswered.length > 0 && (
                                    <p className="text-[13px] text-stone-600">
                                        The knowledge doesn&apos;t answer {draft.unanswered.map((q) => `"${q}"`).join(", ")}. Answer these on <Link href="/dashboard/questions" className="text-plum hover:underline">Questions</Link> and the
                                        assistant will know next time. If you know the answer, write it above.
                                    </p>
                                )}
                                <label className="block">
                                    <span className="text-xs text-stone-500">Next step</span>
                                    <Textarea className="mt-1" rows={2} maxLength={800} value={form.next_step} onChange={(e) => change({ next_step: e.target.value })} />
                                </label>
                                {draft.files_available.length > 0 && (
                                    <fieldset>
                                        <legend className="text-xs text-stone-500 mb-1">Files</legend>
                                        <ul className="space-y-1">
                                            {draft.files_available.map((f) => (
                                                <li key={f.id}>
                                                    <label className="flex items-center gap-2 text-[13px]">
                                                        <input type="checkbox" className="accent-plum" checked={form.file_ids.includes(f.id)}
                                                               onChange={() => change({ file_ids: form.file_ids.includes(f.id) ? form.file_ids.filter((x) => x !== f.id) : [...form.file_ids, f.id].slice(0, 6) })} />
                                                        {f.name}<span className="text-stone-500">{f.size}</span>
                                                    </label>
                                                </li>
                                            ))}
                                        </ul>
                                    </fieldset>
                                )}
                                {problem && <p className="text-[13px] text-signal" role="alert">{problem}</p>}
                            </>
                        )}
                    </section>

                    <section aria-label="Preview" className="lg:overflow-y-auto p-4 sm:p-6">
                        <div className="flex flex-wrap items-center gap-3 mb-3">
                            <div className="min-w-0 flex-1 text-[13px]">
                                {draft && <p className="truncate"><span className="text-stone-500">From </span>{draft.from}</p>}
                                {draft?.reply_to && <p className="truncate"><span className="text-stone-500">Replies to </span>{draft.reply_to}</p>}
                            </div>
                            <div role="group" aria-label="Preview width" className="inline-flex rounded-md border border-line p-0.5 bg-white">
                                <Width label="As on a computer" on={width === "desktop"} onClick={() => setWidth("desktop")}><Monitor size={14} /></Width>
                                <Width label="As on a phone" on={width === "phone"} onClick={() => setWidth("phone")}><Smartphone size={14} /></Width>
                            </div>
                        </div>
                        {draft && <p className="text-[13px] mb-2"><span className="text-stone-500">Subject </span><span className="font-medium">{draft.shown_subject}</span></p>}
                        <div className={cn("mx-auto transition-[max-width]", width === "phone" ? "max-w-[390px]" : "max-w-none")}>
                            <iframe title="Email preview" sandbox="" srcDoc={draft?.html ?? ""} className="w-full h-[70vh] min-h-[480px] rounded-md border border-line bg-white" />
                        </div>
                    </section>
                </div>
            )}

            {!gone && (
                <footer className="flex flex-wrap items-center gap-2 px-4 sm:px-6 py-3 border-t border-line bg-white">
                    <Button variant="ghost" onClick={() => setAsking("discard")} disabled={!draft || busy !== null}>Discard</Button>
                    <Button variant="ghost" onClick={() => setAsking("again")} disabled={!draft || writing || busy !== null}><RefreshCw size={13} aria-hidden /> Write again</Button>
                    <span className="flex-1" />
                    <Button onClick={close}>Close</Button>
                    <Button variant="primary" onClick={() => act("send")} disabled={!draft || writing || busy !== null}>{busy === "send" ? "Sending…" : "Approve and send"}</Button>
                </footer>
            )}

            <Dialog open={asking === "discard"} onClose={() => setAsking(null)} title="Discard this email?" description={`It won't be sent to ${form?.to ?? "them"}.`}
                    footer={<>
                        <Button variant="ghost" onClick={() => setAsking(null)}>Keep it</Button>
                        <Button variant="danger" onClick={() => act("discard")}>Discard</Button>
                    </>}>
                <p className="text-[13px] text-stone-600">It stays in History, marked as discarded.</p>
            </Dialog>
            <Dialog open={asking === "again"} onClose={() => setAsking(null)} title="Write this email again?" description="The AI writes it again from the call."
                    footer={<>
                        <Button variant="ghost" onClick={() => setAsking(null)}>Keep this one</Button>
                        <Button variant="primary" onClick={() => act("again")}>Write again</Button>
                    </>}>
                <p className="text-[13px] text-stone-600">Your changes to this email are replaced.</p>
            </Dialog>
        </div>
    );
}

function Width({ label, on, onClick, children }: { label: string; on: boolean; onClick: () => void; children: React.ReactNode }) {
    return (
        <button type="button" aria-label={label} title={label} aria-pressed={on} onClick={onClick}
                className={cn("h-7 w-8 inline-flex items-center justify-center rounded focus-visible:outline-2 focus-visible:outline-plum",
                    on ? "bg-plum-tint text-plum" : "text-stone-500 hover:text-ink")}>
            {children}
        </button>
    );
}
