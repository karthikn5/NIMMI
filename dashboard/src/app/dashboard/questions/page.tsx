"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { MessageCircle, Phone, Plus, Globe } from "lucide-react";
import AppHeader from "@/components/AppHeader";
import {
    Button, Card, Dialog, EmptyState, Input, Segmented, Select, Skeleton, Textarea, ToastProvider, useToast,
} from "@/components/ui";
import { currentUserId } from "@/lib/api";
import { apiSave, useApi } from "@/lib/useApi";
import { formatWhen } from "@/lib/voice/api";

type Status = "open" | "answered" | "dismissed";
type Question = {
    id: string; bot_id: string; bot_name: string; question: string; answer: string; status: Status;
    count: number; channel: "chat" | "whatsapp" | "voice" | "manual" | null; last_asked_at: string | null;
};
type Data = { items: Question[]; counts: Record<Status, number> };

const CHANNEL = { chat: { label: "Website chat", icon: Globe }, whatsapp: { label: "WhatsApp", icon: MessageCircle },
                  voice: { label: "Phone call", icon: Phone }, manual: { label: "Added by you", icon: Plus } } as const;

export default function QuestionsPage() {
    return (
        <ToastProvider>
            <div className="min-h-screen bg-paper text-ink">
                <AppHeader />
                <Questions />
            </div>
        </ToastProvider>
    );
}

function Questions() {
    const router = useRouter();
    const toast = useToast();
    const [status, setStatus] = useState<Status>("open");
    const [botId, setBotId] = useState("");
    const [editing, setEditing] = useState<string | null>(null);
    const [adding, setAdding] = useState(false);
    const bots = useApi<{ id: string; name: string }[]>("/api/bots");
    const data = useApi<Data>(`/api/questions?status=${status}${botId ? `&bot_id=${botId}` : ""}`);

    useEffect(() => { if (!currentUserId()) router.push("/auth/login"); }, [router]);

    const act = async (q: Question, action: "dismiss" | "reopen" | "delete") => {
        const res = action === "delete"
            ? await apiSave(`/api/questions/${q.id}`, "DELETE")
            : await apiSave(`/api/questions/${q.id}/${action}`, "POST");
        if (!res.ok) return toast(res.message);
        toast(action === "dismiss" ? "Dismissed" : action === "reopen" ? "Moved back to To answer" : "Deleted");
        data.reload();
    };

    const counts = data.data?.counts ?? { open: 0, answered: 0, dismissed: 0 };

    return (
        <main className="max-w-4xl mx-auto px-4 sm:px-6 py-8 pb-24">
            <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
                <div>
                    <h1 className="text-2xl font-semibold tracking-tight">Questions</h1>
                    <p className="text-sm text-stone-500 mt-1 max-w-2xl">
                        What customers asked that your assistants couldn&apos;t answer, on chat, WhatsApp and calls.
                        Answer once and the assistant uses it from then on.
                    </p>
                </div>
                <Button variant="primary" className="self-start sm:self-auto" onClick={() => setAdding(true)}><Plus size={15} /> Add an answer</Button>
            </div>

            <div className="flex flex-col sm:flex-row sm:items-center gap-3 mt-6 mb-4">
                <Segmented label="Show" value={status} onChange={(v) => { setStatus(v); setEditing(null); }} options={[
                    { value: "open", label: `To answer ${counts.open}` },
                    { value: "answered", label: `Answered ${counts.answered}` },
                    { value: "dismissed", label: `Dismissed ${counts.dismissed}` },
                ]} />
                <Select aria-label="Assistant" className="sm:w-56 sm:ml-auto" value={botId} onChange={(e) => setBotId(e.target.value)}>
                    <option value="">All assistants</option>
                    {(bots.data ?? []).map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
                </Select>
            </div>

            <Card>
                {data.loading && !data.data ? (
                    <div className="p-5 space-y-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-14" />)}</div>
                ) : !data.data?.items.length ? (
                    status === "open"
                        ? <EmptyState title="Nothing to answer" body="When an assistant can't answer something, the question shows up here, grouped with others asking the same thing." />
                        : <EmptyState title={status === "answered" ? "No answers yet" : "Nothing dismissed"} body={status === "answered" ? "Answers you write here are used by the assistant straight away." : "Questions you dismiss are hidden and not tracked again."} />
                ) : (
                    <ul>
                        {data.data.items.map((q) => {
                            const ch = CHANNEL[q.channel ?? "chat"] ?? CHANNEL.chat;
                            const Icon = ch.icon;
                            return (
                                <li key={q.id} className="px-5 py-4 border-t border-line first:border-t-0">
                                    <div className="flex flex-col sm:flex-row sm:items-start gap-3">
                                        <div className="min-w-0 flex-1">
                                            <p className="text-sm font-medium">{q.question}</p>
                                            {q.status === "answered" && editing !== q.id && (
                                                <p className="text-[13px] text-stone-600 mt-1.5 pl-3 border-l-2 border-plum/30 whitespace-pre-wrap">{q.answer}</p>
                                            )}
                                            <p className="text-xs text-stone-500 mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1">
                                                {q.count > 0 && <span className="tabular-nums">Asked {q.count} {q.count === 1 ? "time" : "times"}</span>}
                                                <span className="inline-flex items-center gap-1"><Icon size={11} aria-hidden /> {ch.label}</span>
                                                <span>{q.bot_name}</span>
                                                {q.last_asked_at && <span>{formatWhen(q.last_asked_at)}</span>}
                                            </p>
                                        </div>
                                        {editing !== q.id && (
                                            <div className="flex gap-1.5 shrink-0">
                                                {q.status === "open" && <>
                                                    <Button size="sm" variant="primary" onClick={() => setEditing(q.id)}>Answer</Button>
                                                    <Button size="sm" variant="ghost" onClick={() => act(q, "dismiss")}>Dismiss</Button>
                                                </>}
                                                {q.status === "answered" && <>
                                                    <Button size="sm" onClick={() => setEditing(q.id)}>Edit</Button>
                                                    <Button size="sm" variant="ghost" onClick={() => act(q, "delete")}>Delete</Button>
                                                </>}
                                                {q.status === "dismissed" && <Button size="sm" onClick={() => act(q, "reopen")}>Restore</Button>}
                                            </div>
                                        )}
                                    </div>
                                    {editing === q.id && (
                                        <AnswerForm question={q} onCancel={() => setEditing(null)} onSaved={() => { setEditing(null); data.reload(); }} />
                                    )}
                                </li>
                            );
                        })}
                    </ul>
                )}
            </Card>

            <AddAnswer open={adding} bots={bots.data ?? []} defaultBot={botId} onClose={() => setAdding(false)}
                       onSaved={() => { setAdding(false); setStatus("answered"); data.reload(); }} />
        </main>
    );
}

function AnswerForm({ question, onCancel, onSaved }: { question: Question; onCancel: () => void; onSaved: () => void }) {
    const toast = useToast();
    const [wording, setWording] = useState(question.question);
    const [answer, setAnswer] = useState(question.answer);
    const [busy, setBusy] = useState(false);

    const save = async () => {
        setBusy(true);
        const res = await apiSave(`/api/questions/${question.id}/answer`, "POST", { answer, question: wording });
        setBusy(false);
        if (!res.ok) return toast(res.message);
        toast("Saved. The assistant uses this answer from now on.");
        onSaved();
    };

    return (
        <div className="mt-3 space-y-2">
            <Input aria-label="Question" value={wording} maxLength={1000} onChange={(e) => setWording(e.target.value)} />
            <Textarea aria-label="Answer" autoFocus rows={3} maxLength={2000} value={answer} onChange={(e) => setAnswer(e.target.value)}
                      placeholder="Write the answer as you'd want the assistant to say it. Include numbers, timings and links." />
            <div className="flex justify-end gap-2">
                <Button size="sm" variant="ghost" onClick={onCancel}>Cancel</Button>
                <Button size="sm" variant="primary" onClick={save} disabled={busy || !answer.trim()}>{busy ? "Saving…" : "Save answer"}</Button>
            </div>
        </div>
    );
}

function AddAnswer({ open, bots, defaultBot, onClose, onSaved }: {
    open: boolean; bots: { id: string; name: string }[]; defaultBot: string; onClose: () => void; onSaved: () => void;
}) {
    const toast = useToast();
    const [bot, setBot] = useState("");
    const [question, setQuestion] = useState("");
    const [answer, setAnswer] = useState("");
    const [busy, setBusy] = useState(false);
    useEffect(() => { if (open) { setBot(defaultBot || bots[0]?.id || ""); setQuestion(""); setAnswer(""); } }, [open, defaultBot, bots]);

    const save = async () => {
        setBusy(true);
        const res = await apiSave("/api/questions", "POST", { bot_id: bot, question, answer });
        setBusy(false);
        if (!res.ok) return toast(res.message);
        toast("Answer added");
        onSaved();
    };

    return (
        <Dialog open={open} onClose={onClose} title="Add an answer" description="Teach an answer before anyone asks: offers, policies, prices that change."
                footer={<>
                    <Button variant="ghost" onClick={onClose}>Cancel</Button>
                    <Button variant="primary" onClick={save} disabled={busy || !bot || question.trim().length < 3 || !answer.trim()}>{busy ? "Saving…" : "Add answer"}</Button>
                </>}>
            <div className="space-y-3">
                <div>
                    <label htmlFor="qa-bot" className="text-[13px] font-medium">Assistant</label>
                    <Select id="qa-bot" className="mt-1" value={bot} onChange={(e) => setBot(e.target.value)}>
                        {bots.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
                    </Select>
                </div>
                <div>
                    <label htmlFor="qa-q" className="text-[13px] font-medium">Question</label>
                    <Input id="qa-q" className="mt-1" placeholder="e.g. Do you offer EMI?" value={question} maxLength={1000} onChange={(e) => setQuestion(e.target.value)} />
                </div>
                <div>
                    <label htmlFor="qa-a" className="text-[13px] font-medium">Answer</label>
                    <Textarea id="qa-a" className="mt-1" rows={4} maxLength={2000} value={answer} onChange={(e) => setAnswer(e.target.value)} />
                </div>
            </div>
        </Dialog>
    );
}
