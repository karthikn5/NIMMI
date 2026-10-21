"use client";

import { useEffect, useRef, useState } from "react";
import { Send } from "lucide-react";
import { Button, Card, Dialog, EmptyState, Input, Notice, Segmented, Select, Skeleton, Status, Textarea, useToast } from "@/components/ui";
import { apiJson } from "@/lib/api";
import { renderTemplate, type Audience, type AudienceSource, type Broadcast, type IntegrationSettings } from "@/lib/integrations";
import { useApi } from "@/lib/useApi";
import { formatWhen } from "@/lib/voice/api";
import { EmailPreview } from "./EmailPanel";

const PERIODS = [
    { value: "7", label: "Last 7 days" }, { value: "30", label: "Last 30 days" }, { value: "90", label: "Last 3 months" },
    { value: "365", label: "Last year" }, { value: "0", label: "Any time" },
];
const SOURCE_LABEL: Record<AudienceSource, string> = { all: "All leads", chat: "From chat", calls: "From calls" };
const PLACEHOLDERS = ["name", "email", "business"];

export function BulkEmail({ draft, saved }: { draft: IntegrationSettings; saved: IntegrationSettings | null }) {
    const toast = useToast();
    const [source, setSource] = useState<AudienceSource>("all");
    const [days, setDays] = useState("90");
    const [hotOnly, setHotOnly] = useState(false);
    const [subject, setSubject] = useState("");
    const [body, setBody] = useState("");
    const [consent, setConsent] = useState(false);
    const [audience, setAudience] = useState<Audience | null>(null);
    const [audienceError, setAudienceError] = useState<string | null>(null);
    const [confirming, setConfirming] = useState(false);
    const [busy, setBusy] = useState<"test" | "send" | null>(null);
    const history = useApi<Broadcast[]>("/api/integrations/email/broadcasts");
    const bodyRef = useRef<HTMLTextAreaElement>(null);

    // Count who would get it whenever the filters change.
    useEffect(() => {
        let live = true;
        setAudience(null);
        setAudienceError(null);
        const t = setTimeout(() => {
            apiJson<Audience>("/api/integrations/email/audience", { method: "POST", json: { source, days: Number(days), hot_only: hotOnly } })
                .then((a) => live && setAudience(a))
                .catch((e) => live && setAudienceError((e as Error).message));
        }, 250);
        return () => { live = false; clearTimeout(t); };
    }, [source, days, hotOnly]);

    // Refresh progress while a send is still going out.
    const sending = (history.data ?? []).some((b) => b.counts.queued > 0);
    useEffect(() => {
        if (!sending) return;
        const t = setInterval(history.reload, 10_000);
        return () => clearInterval(t);
    }, [sending, history.reload]);

    const business = (saved?.sender_name || draft.sender_name) || "Your business";
    const values = { name: "Priya", email: "priya@example.com", business };
    const count = audience?.count ?? 0;
    const blocked = !draft.server.email ? "Email sending isn't set up on the server yet."
        : !saved?.reply_to ? "Add a reply-to address in Automations and save, so people can answer you."
        : !subject.trim() || !body.trim() ? "Add a subject and message."
        : !audience ? "Counting who gets this…"
        : count === 0 ? "No one matches these filters."
        : count > audience.limit ? `That's more than ${audience.limit.toLocaleString("en-IN")} people. Narrow the filters.`
        : !consent ? "Confirm these people agreed to hear from you."
        : null;

    const insert = (name: string) => {
        const el = bodyRef.current;
        const token = `{{${name}}}`;
        if (!el) return setBody(body + token);
        const start = el.selectionStart ?? body.length;
        const end = el.selectionEnd ?? start;
        setBody(body.slice(0, start) + token + body.slice(end));
        requestAnimationFrame(() => { el.focus(); el.setSelectionRange(start + token.length, start + token.length); });
    };

    const sendTest = async () => {
        setBusy("test");
        try {
            await apiJson("/api/integrations/test", { method: "POST", json: { channel: "email_draft", subject, body } });
            toast("Test email sent to your alert address");
        } catch (e) {
            toast((e as Error).message);
        } finally {
            setBusy(null);
        }
    };

    const send = async () => {
        setBusy("send");
        try {
            const r = await apiJson<{ recipients: number }>("/api/integrations/email/broadcasts", {
                method: "POST", json: { source, days: Number(days), hot_only: hotOnly, subject, body, consent },
            });
            toast(`Sending to ${r.recipients.toLocaleString("en-IN")} ${r.recipients === 1 ? "person" : "people"}`);
            setConfirming(false);
            setSubject(""); setBody(""); setConsent(false);
            history.reload();
        } catch (e) {
            toast((e as Error).message);
        } finally {
            setBusy(null);
        }
    };

    const cancel = async (b: Broadcast) => {
        try {
            const r = await apiJson<{ cancelled: number }>(`/api/integrations/email/broadcasts/${b.id}/cancel`, { method: "POST" });
            toast(`Stopped ${r.cancelled} unsent ${r.cancelled === 1 ? "email" : "emails"}`);
            history.reload();
        } catch (e) {
            toast((e as Error).message);
        }
    };

    return (
        <>
            {draft.server.email && !saved?.reply_to && (
                <Notice title="Add a reply-to address first">Set it under Automations and save, so people can answer your email.</Notice>
            )}
            <Card className="mb-6">
                <div className="px-5 pt-4 pb-3 border-b border-line">
                    <h3 className="text-sm font-medium">New bulk email</h3>
                    <p className="text-[13px] text-stone-500 mt-0.5">
                        One email to people who shared their address with your assistant. Each person gets it once, with an unsubscribe link; anyone who unsubscribed is left out.
                    </p>
                </div>

                <div className="px-5 py-4 border-b border-line">
                    <p className="text-[13px] text-stone-600 mb-2">Who gets it</p>
                    <div className="flex flex-wrap items-center gap-3">
                        <Segmented label="Lead source" value={source} onChange={setSource}
                                   options={(["all", "chat", "calls"] as const).map((v) => ({ value: v, label: SOURCE_LABEL[v] }))} />
                        <Select aria-label="Period" className="w-40" value={days} onChange={(e) => setDays(e.target.value)}>
                            {PERIODS.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
                        </Select>
                        <label className="inline-flex items-center gap-2 text-[13px] text-stone-700 cursor-pointer">
                            <input type="checkbox" className="accent-plum h-4 w-4" checked={hotOnly} onChange={(e) => setHotOnly(e.target.checked)} />
                            Only hot leads
                        </label>
                    </div>
                    <div className="mt-3 text-[13px]" aria-live="polite">
                        {audienceError ? <span className="text-signal">{audienceError}</span> : !audience ? (
                            <Skeleton className="h-5 w-56" />
                        ) : (
                            <>
                                <p>
                                    <span className="font-medium">{count.toLocaleString("en-IN")} {count === 1 ? "person" : "people"}</span>
                                    <span className="text-stone-500">
                                        {audience.unsubscribed ? ` · ${audience.unsubscribed} unsubscribed, left out` : ""}
                                    </span>
                                </p>
                                {audience.sample.length > 0 && (
                                    <p className="text-xs text-stone-500 mt-1 truncate">
                                        {audience.sample.map((p) => p.name ? `${p.name} (${p.email})` : p.email).join(", ")}
                                        {count > audience.sample.length ? ` and ${(count - audience.sample.length).toLocaleString("en-IN")} more` : ""}
                                    </p>
                                )}
                            </>
                        )}
                    </div>
                </div>

                <div className="grid lg:grid-cols-2 gap-5 px-5 py-4">
                    <div className="space-y-3 min-w-0">
                        <div>
                            <label htmlFor="bulk_subject" className="text-[13px] text-stone-600">Subject</label>
                            <Input id="bulk_subject" className="mt-1" maxLength={200} value={subject} placeholder="e.g. Open house this Sunday, {{name}}"
                                   onChange={(e) => setSubject(e.target.value)} />
                        </div>
                        <div>
                            <label htmlFor="bulk_body" className="text-[13px] text-stone-600">Message</label>
                            <Textarea id="bulk_body" ref={bodyRef} className="mt-1 leading-relaxed" rows={10} maxLength={10000} value={body}
                                      placeholder={"Hi {{name}},\n\n…\n\nRegards,\n{{business}}"} onChange={(e) => setBody(e.target.value)} />
                            <div className="flex flex-wrap items-center gap-1.5 mt-2">
                                <span className="text-xs text-stone-500 mr-1">Insert</span>
                                {PLACEHOLDERS.map((p) => (
                                    <button key={p} type="button" onClick={() => insert(p)}
                                            className="h-6 px-2 rounded bg-plum-tint text-plum text-xs hover:bg-plum hover:text-white focus-visible:outline-2 focus-visible:outline-plum">
                                        {p}
                                    </button>
                                ))}
                            </div>
                        </div>
                    </div>
                    <EmailPreview
                        from={business} replyTo={saved?.reply_to}
                        subject={renderTemplate(subject, values)} body={renderTemplate(body, values)}
                        action={<Button size="sm" variant="ghost" onClick={sendTest} disabled={busy === "test" || !subject.trim() || !body.trim()}>
                            <Send size={13} /> {busy === "test" ? "Sending…" : "Send me a test"}
                        </Button>}
                    />
                </div>

                <div className="px-5 py-4 border-t border-line flex flex-col sm:flex-row sm:items-center gap-3">
                    <label className="flex items-start gap-2.5 text-[13px] text-stone-700 cursor-pointer flex-1">
                        <input type="checkbox" className="accent-plum h-4 w-4 mt-0.5 shrink-0" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
                        <span>These people contacted {business} and would expect to hear from us. (Don&apos;t use this for bought or scraped lists.)</span>
                    </label>
                    <Button variant="primary" onClick={() => setConfirming(true)} disabled={!!blocked} title={blocked ?? undefined}>
                        Send to {count.toLocaleString("en-IN")} {count === 1 ? "person" : "people"}
                    </Button>
                </div>
                {blocked && audience && (subject || body || consent) && (
                    <p className="px-5 pb-4 -mt-1 text-xs text-stone-500 sm:text-right">{blocked}</p>
                )}
            </Card>

            <Card>
                <div className="px-5 pt-4 pb-3 flex items-center justify-between">
                    <h3 className="text-sm font-medium">Past bulk emails</h3>
                    <Button size="sm" variant="ghost" onClick={history.reload}>Refresh</Button>
                </div>
                {!history.data ? <div className="px-5 pb-5"><Skeleton className="h-10" /></div> : history.data.length === 0 ? (
                    <EmptyState title="No bulk emails yet" body="Emails you send to your leads show here, with how many went out." />
                ) : (
                    <ul className="border-t border-line">
                        {history.data.map((b) => {
                            const done = b.counts.sent + b.counts.failed + b.counts.cancelled;
                            return (
                                <li key={b.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 px-5 py-3 border-t border-line first:border-t-0 text-[13px]">
                                    <div className="min-w-0 flex-1 basis-60">
                                        <p className="truncate font-medium">{b.subject}</p>
                                        <p className="text-xs text-stone-500 mt-0.5">
                                            {SOURCE_LABEL[b.audience.source ?? "all"]}
                                            {b.audience.days ? `, last ${b.audience.days} days` : ""}{b.audience.hot_only ? ", hot leads" : ""}
                                            {b.created_at ? ` · ${formatWhen(b.created_at)}` : ""}
                                        </p>
                                    </div>
                                    <span className="text-stone-600 tabular-nums">
                                        {b.counts.sent.toLocaleString("en-IN")} of {b.recipients.toLocaleString("en-IN")} sent
                                    </span>
                                    {b.counts.failed > 0 && <Status tone="bad">{b.counts.failed} failed</Status>}
                                    {b.counts.queued > 0 ? (
                                        <>
                                            <Status tone="warn">Sending ({done}/{b.recipients})</Status>
                                            <Button size="sm" variant="ghost" onClick={() => cancel(b)}>Stop</Button>
                                        </>
                                    ) : b.counts.cancelled > 0 ? <Status tone="neutral">{b.counts.cancelled} stopped</Status> : null}
                                </li>
                            );
                        })}
                    </ul>
                )}
            </Card>

            <Dialog open={confirming} onClose={() => setConfirming(false)} title={`Send to ${count.toLocaleString("en-IN")} ${count === 1 ? "person" : "people"}?`}
                    description="It starts going out right away, about 150 emails a minute. You can stop what hasn't gone yet."
                    footer={<>
                        <Button variant="ghost" onClick={() => setConfirming(false)}>Cancel</Button>
                        <Button variant="primary" onClick={send} disabled={busy === "send"}>{busy === "send" ? "Starting…" : "Send now"}</Button>
                    </>}>
                <div className="text-[13px] space-y-1">
                    <p><span className="text-stone-500">Subject </span>{subject}</p>
                    <p><span className="text-stone-500">From </span>{business}{saved?.reply_to ? `, replies to ${saved.reply_to}` : ""}</p>
                </div>
            </Dialog>
        </>
    );
}
