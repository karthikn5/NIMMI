"use client";

import { useRef, useState, type ReactNode } from "react";
import Link from "next/link";
import { ArrowRight, Plus, X } from "lucide-react";
import { Button, Card, Input, Select, SettingRow, Switch, Textarea, cn } from "@/components/ui";
import {
    DELAY_LABEL, DELAY_SECONDS, MAX_STEPS, SAMPLE, renderTemplate,
    type Automation, type Delay, type EmailStep,
} from "@/lib/integrations";
import { PanelHeader, type PanelProps } from "./shared";

/** Email has its own section now (dashboard/email); Integrations > Email points there. */
export function EmailMovedPanel() {
    return (
        <>
            <PanelHeader title="Email" description="Alerts to your team, automatic emails to customers, bulk email and what happened to each email." />
            <Card className="p-5">
                <p className="text-sm">Email has its own section now.</p>
                <p className="text-[13px] text-stone-500 mt-1">
                    Your automatic emails, bulk email and history are there, with what happened to each email after it went (delivered,
                    bounced, reported as spam), sending from your own domain, and who each assistant&apos;s emails come from.
                </p>
                <Link href="/dashboard/email" className="mt-4 inline-flex items-center gap-1.5 h-9 px-4 rounded-md bg-plum text-white text-sm font-medium hover:bg-plum-hover">
                    Open Email <ArrowRight size={14} />
                </Link>
            </Card>
        </>
    );
}

/** Alerts to the workspace's team (Email > Automations). Customers' emails are per assistant: AssistantEmails. */
export function TeamAlerts({ draft, set, test, testing }: PanelProps) {
    const alerts: { key: "email_alerts" | "alert_calls" | "alert_handoffs" | "alert_daily" | "alert_engaged"; label: string; hint: string }[] = [
        { key: "email_alerts", label: "New leads", hint: "Someone shares a phone number or email in chat, on WhatsApp or on a call" },
        { key: "alert_calls", label: "Call summaries", hint: "Every answered or transferred call, with the summary and a link to the recording" },
        { key: "alert_handoffs", label: "A customer asks for a person", hint: "So someone can reply from Live chat while they're still there" },
        { key: "alert_daily", label: "Daily summary", hint: "Each morning: yesterday's leads and calls, and what's waiting for you" },
        { key: "alert_engaged", label: "Someone acts on your email", hint: "They download a file, look at prices or open Book a time. Once a day for each person; security scanners' clicks don't count" },
    ];

    return (
        <Card className="mb-6">
            <div className="px-5 pt-4 pb-1">
                <h3 className="text-sm font-medium">Alerts to your team</h3>
            </div>
            <div className="px-5">
                <SettingRow label="Send to" htmlFor="alert_email" hint={`Up to 5 addresses, separated by commas. Empty uses ${draft.default_email}.`}>
                    <div className="flex gap-2">
                        <Input id="alert_email" type="text" inputMode="email" placeholder={draft.default_email} value={draft.alert_email}
                               onChange={(e) => set("alert_email", e.target.value)} />
                        <Button onClick={() => test("email")} disabled={testing === "email"}>{testing === "email" ? "Sending…" : "Send test"}</Button>
                    </div>
                </SettingRow>
            </div>
            <ul className="border-t border-line">
                {alerts.map((a) => (
                    <li key={a.key} className="flex items-start justify-between gap-4 px-5 py-3.5 border-t border-line first:border-t-0">
                        <div>
                            <p className="text-sm">{a.label}</p>
                            <p className="text-[13px] text-stone-500 mt-0.5">{a.hint}</p>
                        </div>
                        <Switch checked={draft[a.key] ?? true} onChange={(v) => set(a.key, v)} label={`Email the team: ${a.label}`} />
                    </li>
                ))}
            </ul>
        </Card>
    );
}

export function summary(auto: Automation) {
    if (auto.steps.length > 1) return `${auto.steps.length} emails`;
    return DELAY_LABEL[auto.steps[0]?.delay ?? "now"].toLowerCase();
}

const FIRST: Delay[] = ["now", "1h", "1d"];
const FOLLOW: Delay[] = ["1d", "2d", "3d", "5d", "7d", "14d"];

/** Delays a step can use: after the previous email, before the next one. */
function delayChoices(steps: EmailStep[], i: number): Delay[] {
    const after = i > 0 ? DELAY_SECONDS[steps[i - 1].delay] : -1;
    const before = i < steps.length - 1 ? DELAY_SECONDS[steps[i + 1].delay] : Infinity;
    return (i === 0 ? FIRST : FOLLOW).filter((d) => DELAY_SECONDS[d] > after && DELAY_SECONDS[d] < before);
}

const STEP_NAME = ["First email", "Follow-up 1", "Follow-up 2"];

/** An automatic email and its follow-ups. `designedFirst`: the first email is a design edited elsewhere, so only the
 * follow-ups are edited here. */
export function SequenceEditor({ automation, trigger, business, replyTo, placeholders, onChange, designedFirst }: {
    automation: Automation; trigger: string; business: string; replyTo?: string | null; placeholders: string[];
    onChange: (steps: EmailStep[]) => void; designedFirst?: boolean;
}) {
    const [active, setActive] = useState(designedFirst ? 1 : 0);
    const steps = automation.steps;
    const first = designedFirst ? 1 : 0;
    const i = Math.max(first, Math.min(active, steps.length - 1));
    const step: EmailStep | undefined = steps[i];
    const body = useRef<HTMLTextAreaElement>(null);
    const values = { ...SAMPLE, business: business || "Your business" };
    const setStep = (patch: Partial<EmailStep>) => onChange(steps.map((s, n) => (n === i ? { ...s, ...patch } : s)));

    const addFollowUp = () => {
        const last = steps[steps.length - 1];
        const after = DELAY_SECONDS[last.delay];
        const delay = FOLLOW.find((d) => DELAY_SECONDS[d] >= after + 2 * 86400) ?? FOLLOW.find((d) => DELAY_SECONDS[d] > after) ?? "14d";
        onChange([...steps, { delay, subject: "", body: "" }]);
        setActive(steps.length);
    };
    const remove = (n: number) => {
        onChange(steps.filter((_, k) => k !== n));
        setActive(Math.max(0, n - 1));
    };

    const insert = (name: string) => {
        if (!step) return;
        const el = body.current;
        const token = `{{${name}}}`;
        if (!el) return setStep({ body: step.body + token });
        const start = el.selectionStart ?? step.body.length;
        const end = el.selectionEnd ?? start;
        setStep({ body: step.body.slice(0, start) + token + step.body.slice(end) });
        requestAnimationFrame(() => { el.focus(); el.setSelectionRange(start + token.length, start + token.length); });
    };

    const lastDelay = DELAY_SECONDS[steps[steps.length - 1].delay];
    const canAdd = steps.length < MAX_STEPS && FOLLOW.some((d) => DELAY_SECONDS[d] > lastDelay);

    return (
        <div className="px-5 pb-5 pt-1">
            <p className="text-[13px] text-stone-500 mb-3">{trigger}</p>

            {/* The sequence, in order. */}
            <ol className="flex flex-wrap items-center gap-1.5 mb-4" aria-label="Emails in this sequence">
                {steps.map((s, n) => (
                    <li key={n} className="flex items-center">
                        {n > 0 && <span className="w-3 h-px bg-line-strong mr-1.5" aria-hidden />}
                        <span className={cn("inline-flex items-center rounded-md border text-[13px]",
                                            n === i ? "border-plum bg-plum-tint text-plum" : "border-line bg-white text-stone-600")}>
                            <button type="button" onClick={() => setActive(n)} aria-current={n === i ? "step" : undefined} disabled={n < first}
                                    className="h-8 pl-3 pr-3 rounded-md focus-visible:outline-2 focus-visible:outline-plum">
                                <span className="font-medium">{designedFirst && n === 0 ? "Welcome email" : STEP_NAME[n]}</span>
                                <span className={n === i ? "text-plum/70" : "text-stone-400"}> · {DELAY_LABEL[s.delay].toLowerCase()}</span>
                            </button>
                            {n > 0 && (
                                <button type="button" onClick={() => remove(n)} aria-label={`Remove ${STEP_NAME[n].toLowerCase()}`}
                                        className="h-8 pr-2 -ml-1.5 text-stone-400 hover:text-ink rounded-md focus-visible:outline-2 focus-visible:outline-plum">
                                    <X size={13} />
                                </button>
                            )}
                        </span>
                    </li>
                ))}
                {canAdd && (
                    <li className="flex items-center">
                        <span className="w-3 h-px bg-line-strong mr-1.5" aria-hidden />
                        <Button size="sm" variant="ghost" onClick={addFollowUp}><Plus size={13} /> Add follow-up</Button>
                    </li>
                )}
            </ol>

            {step && <div className="grid lg:grid-cols-2 gap-5">
                <div className="space-y-3 min-w-0">
                    <div className="grid grid-cols-[auto_minmax(0,1fr)] items-center gap-x-3 gap-y-3">
                        <label htmlFor="delay" className="text-[13px] text-stone-600">Send</label>
                        <div className="flex items-center gap-2">
                            <Select id="delay" className="max-w-48" value={step.delay} onChange={(e) => setStep({ delay: e.target.value as Delay })}>
                                {delayChoices(steps, i).map((d) => <option key={d} value={d}>{DELAY_LABEL[d]}</option>)}
                            </Select>
                            {i > 0 && <span className="text-xs text-stone-500">after the trigger</span>}
                        </div>
                        <label htmlFor="subject" className="text-[13px] text-stone-600">Subject</label>
                        <Input id="subject" maxLength={200} value={step.subject} onChange={(e) => setStep({ subject: e.target.value })}
                               placeholder={i > 0 ? "e.g. Still looking, {{name}}?" : undefined} />
                    </div>
                    <div>
                        <label htmlFor="body" className="text-[13px] text-stone-600">Message</label>
                        <Textarea id="body" ref={body} className="mt-1 leading-relaxed" rows={9} maxLength={5000} value={step.body}
                                  onChange={(e) => setStep({ body: e.target.value })} />
                        <div className="flex flex-wrap items-center gap-1.5 mt-2">
                            <span className="text-xs text-stone-500 mr-1">Insert</span>
                            {placeholders.map((p) => (
                                <button key={p} type="button" onClick={() => insert(p)}
                                        className="h-6 px-2 rounded bg-plum-tint text-plum text-xs hover:bg-plum hover:text-white focus-visible:outline-2 focus-visible:outline-plum">
                                    {p}
                                </button>
                            ))}
                        </div>
                        <p className="text-xs text-stone-500 mt-2">
                            Anything your assistant collected works too, by its name in lower case: {"{{visit_date}}"} for &ldquo;Visit date&rdquo;.
                        </p>
                    </div>
                </div>

                <EmailPreview from={values.business} replyTo={replyTo ?? undefined}
                              subject={renderTemplate(step.subject, values)} body={renderTemplate(step.body, values)} />
            </div>}
        </div>
    );
}

export function EmailPreview({ from, replyTo, subject, body, action }: {
    from: string; replyTo?: string; subject: string; body: string; action?: ReactNode;
}) {
    return (
        <div className="min-w-0">
            <div className="flex items-center justify-between mb-1.5 min-h-8">
                <span className="text-xs text-stone-500">Preview, with sample details</span>
                {action}
            </div>
            <div className="rounded-md border border-line bg-paper p-3">
                <div className="rounded-md bg-white border border-line">
                    <div className="px-4 py-3 border-b border-line text-[13px] space-y-0.5">
                        <p><span className="text-stone-500">From </span>{from}</p>
                        {replyTo && <p><span className="text-stone-500">Reply to </span>{replyTo}</p>}
                        <p className="font-medium pt-1">{subject || <span className="text-stone-400">No subject</span>}</p>
                    </div>
                    <div className="px-4 py-4 text-[13px] leading-relaxed whitespace-pre-wrap break-words min-h-40">
                        {body || <span className="text-stone-400">Write a message on the left.</span>}
                    </div>
                </div>
                <p className="text-[11px] text-stone-500 text-center mt-2">{from} · Unsubscribe</p>
            </div>
        </div>
    );
}
