"use client";

import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { Button, Card, Input, Status, Textarea, useToast } from "@/components/ui";
import { apiJson } from "@/lib/api";
import { DRAFTS_CHANGED, type AgentDraft } from "@/lib/email";
import { useApi } from "@/lib/useApi";
import { formatWhen } from "@/lib/voice/api";

function Item({ d, onDone }: { d: AgentDraft; onDone: () => void }) {
    const toast = useToast();
    const [open, setOpen] = useState(false);
    const [subject, setSubject] = useState(d.subject);
    const [body, setBody] = useState(d.body);
    const [busy, setBusy] = useState(false);
    const changed = subject !== d.subject || body !== d.body;
    const act = async (what: "send" | "discard") => {
        setBusy(true);
        try {
            if (what === "send" && changed) await apiJson(`/api/email/agent/drafts/${d.id}`, { method: "PUT", json: { subject, body } });
            await apiJson(`/api/email/agent/drafts/${d.id}/${what}`, { method: "POST", json: {} });
            toast(what === "send" ? `It's on its way to ${d.name || d.to}` : "Dropped");
            onDone();
        } catch (e) {
            toast((e as Error).message);
            setBusy(false);
        }
    };
    return (
        <li className="border-t border-line first:border-t-0">
            <button type="button" aria-expanded={open} onClick={() => setOpen(!open)} className="w-full flex items-center gap-4 px-5 py-3.5 text-left hover:bg-paper/70 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-plum">
                <span className="min-w-0 flex-1">
                    <span className="block text-sm truncate">{d.name || d.to}<span className="text-stone-500"> · {d.subject}</span></span>
                    <span className="block text-[13px] text-stone-500 truncate">{d.note || d.why}{d.created_at ? ` · ${formatWhen(d.created_at)}` : ""}{d.bot_name ? ` · ${d.bot_name}` : ""}</span>
                </span>
                <Status tone={d.note ? "warn" : "good"}>{d.note ? "Needs a look" : "Ready"}</Status>
                <ChevronDown size={15} className={`text-stone-400 shrink-0 transition-transform ${open ? "rotate-180" : ""}`} aria-hidden />
            </button>
            {open && (
                <div className="px-5 pb-4 space-y-2">
                    <p className="text-[13px] text-stone-600">To {d.to}. {d.why && <>Why: {d.why}</>}</p>
                    {d.note && <p className="text-[13px] text-stone-700">{d.note}</p>}
                    <Input aria-label="Subject" maxLength={200} value={subject} onChange={(e) => setSubject(e.target.value)} />
                    <Textarea aria-label="Message" rows={7} maxLength={5000} value={body} onChange={(e) => setBody(e.target.value)} />
                    <div className="flex flex-wrap justify-end gap-2">
                        <Button size="sm" variant="ghost" disabled={busy} onClick={() => act("discard")}>Drop it</Button>
                        <Button size="sm" variant="primary" disabled={busy || !subject.trim() || !body.trim()} onClick={() => act("send")}>{changed ? "Save and send" : "Send"}</Button>
                    </div>
                </div>
            )}
        </li>
    );
}

/** The email agent's emails waiting for the team (Drafts). A morning's queue can go in one press; anything a check held needs its own look. */
export function AgentDrafts() {
    const toast = useToast();
    const list = useApi<{ items: AgentDraft[]; total: number }>("/api/email/agent/drafts");
    const [busy, setBusy] = useState(false);
    const { reload } = list;
    const done = () => { void reload(); window.dispatchEvent(new Event(DRAFTS_CHANGED)); };
    const items = list.data?.items ?? [];
    if (!items.length) return null;
    const ready = items.filter((d) => !d.note).length;
    const sendAll = async () => {
        setBusy(true);
        try {
            const r = await apiJson<{ queued: number }>("/api/email/agent/drafts/send-all", { method: "POST", json: {} });
            toast(`${r.queued} on ${r.queued === 1 ? "its" : "their"} way`);
            done();
        } catch (e) {
            toast((e as Error).message);
        } finally {
            setBusy(false);
        }
    };
    return (
        <Card>
            <div className="flex flex-wrap items-center justify-between gap-3 px-5 pt-4 pb-3 border-b border-line">
                <div className="min-w-0">
                    <h3 className="text-sm font-medium">From the email agent</h3>
                    <p className="text-[13px] text-stone-500 mt-0.5">Follow-ups it wrote to leads who went quiet. Nothing goes until you send it.</p>
                </div>
                {ready > 0 && <Button size="sm" variant="primary" disabled={busy} onClick={sendAll}>Send the {ready} ready</Button>}
            </div>
            <ul>{items.map((d) => <Item key={d.id} d={d} onDone={done} />)}</ul>
        </Card>
    );
}
