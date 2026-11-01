"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ChevronDown, Pencil } from "lucide-react";
import { Button, Card, Select, Skeleton, Status, Switch, cn, useToast } from "@/components/ui";
import { SequenceEditor, summary } from "@/components/integrations/EmailPanel";
import { apiJson } from "@/lib/api";
import { REPLY_MODES, type AfterCallMode, type AssistantEmails as Setup, type EmailKind, type ReplyMode, type Senders } from "@/lib/email";
import { AUTOMATIONS, type Automation, type AutomationKey, type EmailStep } from "@/lib/integrations";
import { useLimits } from "@/lib/plan";
import { useApi } from "@/lib/useApi";
import { DesignEditor } from "./DesignEditor";

const PLACEHOLDERS = ["name", "business", "assistant", "email", "phone", "summary", "details"];
const PLAIN: AutomationKey[] = ["call_lead", "goal_met", "call_missed", "handoff_done"];
const TITLES: Partial<Record<AutomationKey, string>> = { call_lead: "Fixed email after a call", goal_met: "Fixed email when a call reaches its goal" };
type SmallKind = "lead_email" | "callback_booked" | "voicemail" | "missed_chat" | "chat_copy";
const SMALL: { key: SmallKind; title: string; about: string }[] = [
    { key: "lead_email", title: "New lead from another place", about: "When a lead comes in from a portal or a form (Lead sources) and gave an email." },
    { key: "callback_booked", title: "Call-back booked", about: "When a call-back is booked for them: when you'll call." },
    { key: "voicemail", title: "Voicemail left", about: "When you called them and reached their voicemail." },
    { key: "missed_chat", title: "Missed live chat", about: "When they asked for a person in the chat and nobody came in time." },
    { key: "chat_copy", title: "Copy of the chat", about: "Adds Email me this chat to the chat. It goes only to the address they gave." },
];
const MODES: { value: AfterCallMode; label: string }[] = [{ value: "off", label: "Off" }, { value: "review", label: "Review first" }, { value: "auto", label: "Automatic" }];

/** Each assistant's emails to customers: one account can run several businesses (backend mail/setup.py). */
export function AssistantEmails() {
    const toast = useToast();
    const limits = useLimits();
    const senders = useApi<Senders>("/api/email/senders");
    const [botId, setBotId] = useState("");
    const setup = useApi<Setup>(botId ? `/api/email/setup/${botId}` : null);
    const [open, setOpen] = useState<AutomationKey | null>(null);
    const [draft, setDraft] = useState<EmailStep[] | null>(null);
    const [saving, setSaving] = useState(false);
    const [editing, setEditing] = useState<EmailKind | null>(null);

    const assistants = senders.data?.assistants ?? [];
    useEffect(() => { if (!botId && assistants[0]) setBotId(assistants[0].bot_id); }, [botId, assistants]);
    useEffect(() => { setOpen(null); setDraft(null); }, [botId]);

    if (senders.error) return <p className="text-sm text-signal">{senders.error}</p>;
    if (!senders.data) return <Skeleton className="h-64" />;
    if (assistants.length === 0) return <Card className="p-5 text-[13px] text-stone-600">Make an assistant first: its emails are set here.</Card>;

    // While a new version deploys, this page can be newer than the server: a row whose setting hasn't arrived stays out until it has.
    const s = setup.data;
    const plan = limits?.assistant_plans?.[botId];
    const growth = plan ? plan.email_alerts : limits?.includes?.email_alerts ?? true;
    const sender = assistants.find((a) => a.bot_id === botId)?.sends_as;

    const save = async (key: AutomationKey, auto: Automation) => {
        setSaving(true);
        try {
            setup.setData(await apiJson<Setup>(`/api/email/setup/${botId}`, { method: "PUT", json: { automations: { [key]: auto } } }));
            setDraft(null);
            toast("Saved");
        } catch (e) {
            toast((e as Error).message);
        } finally {
            setSaving(false);
        }
    };
    const expand = (key: AutomationKey) => { setDraft(null); setOpen(open === key ? null : key); };
    const setSetting = async (kind: string, values: Record<string, unknown>) => {
        setSaving(true);
        try {
            setup.setData(await apiJson<Setup>(`/api/email/setup/${botId}`, { method: "PUT", json: { settings: { [kind]: values } } }));
            toast("Saved");
        } catch (e) {
            toast((e as Error).message);
        } finally {
            setSaving(false);
        }
    };
    const setReplies = async (mode: ReplyMode) => {
        setSaving(true);
        try {
            setup.setData(await apiJson<Setup>(`/api/email/setup/${botId}`, { method: "PUT", json: { settings: { replies: { mode } } } }));
            toast("Saved");
        } catch (e) {
            toast((e as Error).message);
        } finally {
            setSaving(false);
        }
    };
    const setMode = async (direction: "inbound" | "outbound", mode: AfterCallMode) => {
        setSaving(true);
        try {
            setup.setData(await apiJson<Setup>(`/api/email/setup/${botId}`, { method: "PUT", json: { settings: { after_call: { [direction]: mode } } } }));
            toast("Saved");
        } catch (e) {
            toast((e as Error).message);
        } finally {
            setSaving(false);
        }
    };

    const row = (key: AutomationKey, title: string, about: string, locked: boolean, designed = false) => {
        if (!s) return null;
        const auto = s.automations[key] as Automation;
        const expanded = open === key;
        const steps = expanded && draft ? draft : auto.steps;
        const changed = expanded && draft !== null && JSON.stringify(draft) !== JSON.stringify(auto.steps);
        return (
            <li key={key} className="border-t border-line">
                <div className="flex flex-wrap items-center gap-3 px-5 py-3.5">
                    <button type="button" onClick={() => expand(key)} aria-expanded={expanded} disabled={locked && !designed}
                            className="flex-1 min-w-48 flex items-center gap-3 text-left rounded focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-plum">
                        <ChevronDown size={15} className={cn("text-stone-400 shrink-0 transition-transform", expanded && "rotate-180", locked && !designed && "invisible")} aria-hidden />
                        <span className="min-w-0">
                            <span className="flex flex-wrap items-center gap-x-2.5">
                                <span className="text-sm">{title}</span>
                                {locked ? <span className="text-xs text-stone-500">Comes with Growth</span>
                                    : <Status tone={auto.enabled ? "good" : "neutral"}>{auto.enabled ? `On · ${summary(auto)}` : "Off"}</Status>}
                            </span>
                            <span className="block text-[13px] text-stone-500 mt-0.5">{about}</span>
                        </span>
                    </button>
                    {designed && <Button size="sm" onClick={() => setEditing("welcome")} aria-label="Edit the welcome email"><Pencil size={13} aria-hidden /> Edit email</Button>}
                    <Switch checked={auto.enabled && !locked} disabled={locked || saving} onChange={(v) => save(key, { ...auto, enabled: v })} label={`Send: ${title}`} />
                </div>
                {expanded && (
                    <div className="border-t border-line">
                        {designed && !growth ? (
                            <p className="px-5 py-3 text-[13px] text-stone-600">Follow-ups after the welcome email come with Growth or Pro.</p>
                        ) : (
                            <>
                                <div className="pt-3">
                                    <SequenceEditor automation={{ ...auto, steps }} trigger={designed ? "Follow-ups go out if the person hasn't booked or unsubscribed." : AUTOMATIONS.find((a) => a.key === key)?.trigger ?? ""}
                                                    business={sender?.name ?? ""} replyTo={sender?.reply_to} placeholders={PLACEHOLDERS} onChange={setDraft} designedFirst={designed} />
                                </div>
                                {changed && (
                                    <div className="flex justify-end gap-2 px-5 pb-4">
                                        <Button variant="ghost" onClick={() => setDraft(null)}>Discard</Button>
                                        <Button variant="primary" disabled={saving} onClick={() => save(key, { ...auto, steps: draft! })}>{saving ? "Saving…" : "Save"}</Button>
                                    </div>
                                )}
                            </>
                        )}
                    </div>
                )}
            </li>
        );
    };

    const kind = s?.kinds.find((k) => k.kind === editing);
    const duringCall = () => {
        if (!s?.settings.during_call) return null;
        return (
            <li className="border-t border-line px-5 py-3.5">
                <div className="flex flex-wrap items-center gap-3">
                    <div className="flex-1 min-w-48 pl-[27px]">
                        <span className="flex flex-wrap items-center gap-x-2.5">
                            <span className="text-sm">During a call</span>
                            {growth ? <Status tone={s.settings.during_call.enabled ? "good" : "neutral"}>{s.settings.during_call.enabled ? "On" : "Off"}</Status>
                                : <span className="text-xs text-stone-500">Comes with Growth</span>}
                        </span>
                        <span className="block text-[13px] text-stone-500 mt-0.5">
                            The phone agent can email a file or a note while they talk, like &quot;email me the price list&quot;. It never reads their address out.
                        </span>
                    </div>
                    <Button size="sm" onClick={() => setEditing("during_call")} aria-label="Edit the email sent during a call"><Pencil size={13} aria-hidden /> Edit email</Button>
                    <Switch checked={s.settings.during_call.enabled && growth} disabled={!growth || saving} onChange={(v) => setSetting("during_call", { enabled: v })} label="Email during a call" />
                </div>
            </li>
        );
    };
    const small = (item: (typeof SMALL)[number]) => {
        if (!s?.settings[item.key]) return null;
        const on = s.settings[item.key].enabled;
        return (
            <li key={item.key} className="border-t border-line px-5 py-3.5">
                <div className="flex flex-wrap items-center gap-3">
                    <div className="flex-1 min-w-48 pl-[27px]">
                        <span className="flex flex-wrap items-center gap-x-2.5">
                            <span className="text-sm">{item.title}</span>
                            {growth ? <Status tone={on ? "good" : "neutral"}>{on ? "On" : "Off"}</Status> : <span className="text-xs text-stone-500">Comes with Growth</span>}
                        </span>
                        <span className="block text-[13px] text-stone-500 mt-0.5">{item.about}</span>
                    </div>
                    {item.key === "missed_chat" && (
                        <Select aria-label="How long to wait" className="w-32" value={s.settings.missed_chat.minutes} disabled={!growth || saving}
                                onChange={(e) => setSetting("missed_chat", { minutes: Number(e.target.value) })}>
                            {[5, 10, 15, 30].map((m) => <option key={m} value={m}>After {m} min</option>)}
                        </Select>
                    )}
                    <Button size="sm" onClick={() => setEditing(item.key)} aria-label={`Edit the email: ${item.title}`}><Pencil size={13} aria-hidden /> Edit email</Button>
                    <Switch checked={on && growth} disabled={!growth || saving} onChange={(v) => setSetting(item.key, { enabled: v })} label={`Send: ${item.title}`} />
                </div>
            </li>
        );
    };
    const meetingEmails = () => {
        if (!s?.settings.meeting) return null;
        const m = s.settings.meeting;
        return (
            <li className="border-t border-line px-5 py-3.5">
                <div className="flex flex-wrap items-center gap-3">
                    <div className="flex-1 min-w-48 pl-[27px]">
                        <span className="text-sm">Meeting emails</span>
                        <span className="block text-[13px] text-stone-500 mt-0.5">The confirmation with its invite, the reminder and the joining details always go. These two go after it:</span>
                    </div>
                    <Button size="sm" onClick={() => setEditing("meeting")} aria-label="Edit the meeting emails"><Pencil size={13} aria-hidden /> Edit email</Button>
                </div>
                <div className="mt-2 pl-[27px] space-y-2">
                    <div className="flex items-center justify-between gap-3 text-[13px]"><span>A thank-you after they attend</span><Switch checked={m.thanks} disabled={saving} onChange={(v) => setSetting("meeting", { thanks: v })} label="A thank-you after they attend" /></div>
                    <div className="flex items-center justify-between gap-3 text-[13px]"><span>Sorry we missed you, with a link to book again</span><Switch checked={m.missed} disabled={saving} onChange={(v) => setSetting("meeting", { missed: v })} label="Sorry we missed you" /></div>
                </div>
            </li>
        );
    };
    const replies = () => {
        if (!s?.settings.replies) return null;
        return (
            <li className="border-t border-line px-5 py-3.5">
                <div className="flex flex-wrap items-center gap-3">
                    <div className="flex-1 min-w-48 pl-[27px]">
                        <span className="flex flex-wrap items-center gap-x-2.5">
                            <span className="text-sm">When someone replies</span>
                            {!growth ? <span className="text-xs text-stone-500">Comes with Growth</span>
                                : !s.replies_on && <span className="text-xs text-stone-500">Not switched on for your account yet</span>}
                        </span>
                        <span className="block text-[13px] text-stone-500 mt-0.5">
                            Their reply shows in <Link href="/dashboard/email/inbox" className="text-plum hover:underline">Inbox</Link> and a copy goes to your mailbox. Follow-ups to them stop.
                        </span>
                    </div>
                    <Select aria-label="Who answers replies" className="w-60" value={s.settings.replies.mode} disabled={!growth || saving} onChange={(e) => setReplies(e.target.value as ReplyMode)}>
                        {REPLY_MODES.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
                    </Select>
                </div>
            </li>
        );
    };
    const afterCall = () => {
        if (!s?.settings.after_call) return null;
        const prefs = s.settings.after_call;
        const on = prefs.inbound !== "off" || prefs.outbound !== "off";
        const mode = (direction: "inbound" | "outbound", label: string) => (
            <label className="block">
                <span className="text-xs text-stone-500">{label}</span>
                <Select className="mt-1" value={growth ? prefs[direction] : "off"} disabled={!growth || saving} onChange={(e) => setMode(direction, e.target.value as AfterCallMode)}>
                    {MODES.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
                </Select>
            </label>
        );
        return (
            <li className="border-t border-line px-5 py-3.5">
                <div className="flex flex-wrap items-center gap-3">
                    <div className="flex-1 min-w-48 pl-[27px]">
                        <span className="flex flex-wrap items-center gap-x-2.5">
                            <span className="text-sm">After a call, written by the AI</span>
                            {growth ? <Status tone={on ? "good" : "neutral"}>{on ? "On" : "Off"}</Status> : <span className="text-xs text-stone-500">Comes with Growth</span>}
                        </span>
                        <span className="block text-[13px] text-stone-500 mt-0.5">
                            A recap, answers to their questions from your knowledge and the next step, in the language of the call. Each counts as one AI reply.
                        </span>
                    </div>
                    <Button size="sm" onClick={() => setEditing("after_call")} aria-label="Edit the email after a call"><Pencil size={13} aria-hidden /> Edit email</Button>
                </div>
                <div className="grid sm:grid-cols-2 gap-3 mt-3 pl-[27px] max-w-xl">
                    {mode("inbound", "Incoming calls")}
                    {mode("outbound", "Outgoing calls")}
                </div>
                {on && (
                    <p className="text-[13px] text-stone-500 mt-2 pl-[27px]">
                        Review first: each waits in <Link href="/dashboard/email/drafts" className="text-plum hover:underline">Drafts</Link> for your OK. Automatic: it goes by itself, unless the
                        AI&apos;s check isn&apos;t sure or the caller was unhappy. Not sent after a call handed to a person.
                    </p>
                )}
            </li>
        );
    };
    return (
        <Card>
            <div className="flex flex-wrap items-center justify-between gap-3 px-5 pt-4 pb-3">
                <div className="min-w-0">
                    <h3 className="text-sm font-medium">Emails to customers</h3>
                    <p className="text-[13px] text-stone-500 mt-0.5">Each assistant has its own. They stop if the person unsubscribes, reports spam, or their address bounces.</p>
                </div>
                {assistants.length > 1 && (
                    <Select aria-label="Assistant" className="w-56" value={botId} onChange={(e) => setBotId(e.target.value)}>
                        {assistants.map((a) => <option key={a.bot_id} value={a.bot_id}>{a.bot_name}</option>)}
                    </Select>
                )}
            </div>
            {setup.error ? <p className="px-5 pb-4 text-sm text-signal">{setup.error}</p> : !s ? (
                <div className="px-5 pb-5 space-y-3"><Skeleton className="h-14" /><Skeleton className="h-14" /></div>
            ) : (
                <ul>
                    {row("chat_lead", "Welcome email", "When someone gives their email in a chat. It goes when the chat goes quiet.", false, true)}
                    {afterCall()}
                    {duringCall()}
                    {replies()}
                    {meetingEmails()}
                    {SMALL.map(small)}
                    {PLAIN.map((key) => {
                        const a = AUTOMATIONS.find((x) => x.key === key)!;
                        const fixed = key === "call_lead" || key === "goal_met";
                        return row(key, TITLES[key] ?? a.title, fixed ? `${a.trigger.split(" {{")[0]} Not sent for calls the AI writes to.` : a.trigger, !growth);
                    })}
                </ul>
            )}
            {s && kind && (
                <DesignEditor open onClose={() => setEditing(null)} botId={botId} botName={s.bot_name} kind={kind.kind} label={kind.label}
                              placeholders={kind.placeholders} languages={kind.languages} growth={growth} setup={s} onSetup={setup.setData} />
            )}
        </Card>
    );
}
