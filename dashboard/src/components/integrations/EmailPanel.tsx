"use client";

import { useRef, useState } from "react";
import { ChevronDown, Send } from "lucide-react";
import { Button, Card, Input, Notice, Select, SettingRow, Status, Switch, Textarea, cn } from "@/components/ui";
import { AUTOMATIONS, SAMPLE, renderTemplate, type Automation, type AutomationKey, type IntegrationSettings } from "@/lib/integrations";
import { PanelHeader, type PanelProps } from "./shared";

export function EmailPanel({ draft, set, test, testing }: PanelProps) {
    const [open, setOpen] = useState<AutomationKey | null>(null);
    const setAuto = (key: AutomationKey, patch: Partial<Automation>) =>
        set("automations", { ...draft.automations, [key]: { ...draft.automations[key], ...patch } });

    const alerts: { key: "email_alerts" | "alert_calls" | "alert_handoffs"; label: string; hint: string }[] = [
        { key: "email_alerts", label: "New leads", hint: "Someone shares a phone number or email in chat, on WhatsApp or on a call" },
        { key: "alert_calls", label: "Call summaries", hint: "Every answered or transferred call, with the summary and a link to the recording" },
        { key: "alert_handoffs", label: "A customer asks for a person", hint: "So someone can reply from Live chat while they're still there" },
    ];

    return (
        <>
            <PanelHeader title="Email" description="Alerts to your team when something happens, and automatic follow-ups to your customers." />
            {!draft.server.email && (
                <Notice title="Email sending isn't set up on the server">
                    Everything below is saved, and shows in Activity, but nothing is delivered until an email provider (Resend or SMTP) is configured.
                </Notice>
            )}

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
                            <Switch checked={draft[a.key]} onChange={(v) => set(a.key, v)} label={`Email the team: ${a.label}`} />
                        </li>
                    ))}
                </ul>
            </Card>

            <Card>
                <div className="px-5 pt-4 pb-1">
                    <h3 className="text-sm font-medium">Emails to customers</h3>
                    <p className="text-[13px] text-stone-500 mt-0.5">Sent once per customer, with an unsubscribe link. Anyone who unsubscribes is never emailed again.</p>
                </div>
                <div className="px-5">
                    <SettingRow label="From name" htmlFor="sender_name" hint="Customers see this as the sender.">
                        <Input id="sender_name" placeholder="e.g. Acme Realty" maxLength={60} value={draft.sender_name} onChange={(e) => set("sender_name", e.target.value)} />
                    </SettingRow>
                    <SettingRow label="Replies go to" htmlFor="reply_to" hint="When a customer replies, it lands in this inbox.">
                        <Input id="reply_to" type="email" placeholder="e.g. hello@acmerealty.in" value={draft.reply_to} onChange={(e) => set("reply_to", e.target.value)} />
                    </SettingRow>
                </div>

                <ul className="border-t border-line">
                    {AUTOMATIONS.map((a) => {
                        const auto = draft.automations[a.key];
                        const expanded = open === a.key;
                        return (
                            <li key={a.key} className="border-t border-line first:border-t-0">
                                <div className="flex items-center gap-3 px-5 py-3.5">
                                    <button type="button" onClick={() => setOpen(expanded ? null : a.key)} aria-expanded={expanded}
                                            className="flex-1 min-w-0 flex items-center gap-3 text-left rounded focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-plum">
                                        <ChevronDown size={15} className={cn("text-stone-400 shrink-0 transition-transform", expanded && "rotate-180")} aria-hidden />
                                        <span className="min-w-0">
                                            <span className="flex items-center gap-2.5">
                                                <span className="text-sm">{a.title}</span>
                                                <Status tone={auto.enabled ? "good" : "neutral"}>{auto.enabled ? `On · ${DELAY_LABEL[auto.delay]}` : "Off"}</Status>
                                            </span>
                                            <span className="block text-[13px] text-stone-500 mt-0.5 truncate">{auto.subject ? renderTemplate(auto.subject, { ...SAMPLE, business: draft.sender_name || "Your business" }) : a.trigger}</span>
                                        </span>
                                    </button>
                                    <Switch checked={auto.enabled} onChange={(v) => setAuto(a.key, { enabled: v })} label={`Send email ${a.title.toLowerCase()}`} />
                                </div>
                                {expanded && (
                                    <AutomationEditor
                                        automation={auto} trigger={a.trigger} draft={draft}
                                        onChange={(patch) => setAuto(a.key, patch)}
                                        onTest={() => test("email_automation", a.key)} testing={testing === `email_automation:${a.key}`}
                                    />
                                )}
                            </li>
                        );
                    })}
                </ul>
            </Card>
        </>
    );
}

const DELAY_LABEL: Record<Automation["delay"], string> = { now: "right away", "1h": "after 1 hour", "1d": "next day" };

function AutomationEditor({ automation, trigger, draft, onChange, onTest, testing }: {
    automation: Automation; trigger: string; draft: IntegrationSettings;
    onChange: (patch: Partial<Automation>) => void; onTest: () => void; testing: boolean;
}) {
    const body = useRef<HTMLTextAreaElement>(null);
    const values = { ...SAMPLE, business: draft.sender_name || "Your business" };

    const insert = (name: string) => {
        const el = body.current;
        const token = `{{${name}}}`;
        if (!el) return onChange({ body: automation.body + token });
        const start = el.selectionStart ?? automation.body.length;
        const end = el.selectionEnd ?? start;
        onChange({ body: automation.body.slice(0, start) + token + automation.body.slice(end) });
        requestAnimationFrame(() => { el.focus(); el.setSelectionRange(start + token.length, start + token.length); });
    };

    return (
        <div className="grid lg:grid-cols-2 gap-5 px-5 pb-5 pt-1">
            <div className="space-y-3 min-w-0">
                <p className="text-[13px] text-stone-500">{trigger}</p>
                <div className="grid grid-cols-[auto_minmax(0,1fr)] items-center gap-x-3 gap-y-3">
                    <label htmlFor="delay" className="text-[13px] text-stone-600">Send</label>
                    <Select id="delay" className="max-w-48" value={automation.delay} onChange={(e) => onChange({ delay: e.target.value as Automation["delay"] })}>
                        <option value="now">Right away</option>
                        <option value="1h">1 hour later</option>
                        <option value="1d">The next day</option>
                    </Select>
                    <label htmlFor="subject" className="text-[13px] text-stone-600">Subject</label>
                    <Input id="subject" maxLength={200} value={automation.subject} onChange={(e) => onChange({ subject: e.target.value })} />
                </div>
                <div>
                    <label htmlFor="body" className="text-[13px] text-stone-600">Message</label>
                    <Textarea id="body" ref={body} className="mt-1 leading-relaxed" rows={9} maxLength={5000} value={automation.body}
                              onChange={(e) => onChange({ body: e.target.value })} />
                    <div className="flex flex-wrap items-center gap-1.5 mt-2">
                        <span className="text-xs text-stone-500 mr-1">Insert</span>
                        {draft.placeholders.map((p) => (
                            <button key={p} type="button" onClick={() => insert(p)}
                                    className="h-6 px-2 rounded bg-plum-tint text-plum text-xs hover:bg-plum hover:text-white focus-visible:outline-2 focus-visible:outline-plum">
                                {p}
                            </button>
                        ))}
                    </div>
                </div>
            </div>

            <div className="min-w-0">
                <div className="flex items-center justify-between mb-1.5">
                    <span className="text-xs text-stone-500">Preview, with sample details</span>
                    <Button size="sm" variant="ghost" onClick={onTest} disabled={testing}><Send size={13} /> {testing ? "Sending…" : "Send me a test"}</Button>
                </div>
                <div className="rounded-md border border-line bg-paper p-3">
                    <div className="rounded-md bg-white border border-line">
                        <div className="px-4 py-3 border-b border-line text-[13px] space-y-0.5">
                            <p><span className="text-stone-500">From </span>{values.business}</p>
                            {draft.reply_to && <p><span className="text-stone-500">Reply to </span>{draft.reply_to}</p>}
                            <p className="font-medium pt-1">{renderTemplate(automation.subject, values) || <span className="text-stone-400">No subject</span>}</p>
                        </div>
                        <div className="px-4 py-4 text-[13px] leading-relaxed whitespace-pre-wrap break-words min-h-40">
                            {renderTemplate(automation.body, values) || <span className="text-stone-400">Write a message on the left.</span>}
                        </div>
                    </div>
                    <p className="text-[11px] text-stone-500 text-center mt-2">{values.business} · Unsubscribe</p>
                </div>
            </div>
        </div>
    );
}
