"use client";

import { useState } from "react";
import { ArrowDown, ArrowUp, Bell, Clock, GitBranch, Mail, MessageCircle, Phone, Plus, Trash2, UserCog, type LucideIcon } from "lucide-react";
import { Button, Card, Dialog, Input, SaveBar, Select, Status, Switch, Textarea, useToast } from "@/components/ui";
import { apiJson } from "@/lib/api";
import { STAGE_LABEL, type Journey, type JourneyRunRow, type Journeys, type JourneyStep, type JourneyStepKind } from "@/lib/email";
import { useApi } from "@/lib/useApi";
import { formatWhen } from "@/lib/voice/api";

const STEP_KINDS: { type: JourneyStepKind; label: string; add: string; icon: LucideIcon; blank: JourneyStep }[] = [
    { type: "email", label: "Send an email", add: "Email", icon: Mail, blank: { type: "email", subject: "", body: "" } },
    { type: "wait", label: "Wait", add: "Wait", icon: Clock, blank: { type: "wait", days: 2, hours: 0 } },
    { type: "whatsapp", label: "Send a WhatsApp message", add: "WhatsApp", icon: MessageCircle, blank: { type: "whatsapp", text: "" } },
    { type: "call", label: "Call them", add: "Call", icon: Phone, blank: { type: "call", about: "" } },
    { type: "branch", label: "Check something", add: "Check", icon: GitBranch, blank: { type: "branch", if: "booked", then: "end" } },
    { type: "update", label: "Update the contact", add: "Update", icon: UserCog, blank: { type: "update", tag: "" } },
    { type: "notify", label: "Tell your team", add: "Tell your team", icon: Bell, blank: { type: "notify", text: "" } },
];
const RUN_STATUS: Record<JourneyRunRow["status"], { tone: "good" | "neutral" | "warn"; text: string }> = {
    active: { tone: "good", text: "On it" }, done: { tone: "neutral", text: "Finished" }, stopped: { tone: "warn", text: "Stopped" },
};
const DAY_LABEL: Record<string, string> = { mon: "Monday", tue: "Tuesday", wed: "Wednesday", thu: "Thursday", fri: "Friday", sat: "Saturday", sun: "Sunday" };

function Check({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
    return (
        <label className="flex items-center gap-2 text-[13px] text-stone-600">
            <input type="checkbox" className="accent-[var(--plum,#6d4aff)]" checked={checked} onChange={(e) => onChange(e.target.checked)} /> {label}
        </label>
    );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
    return <label className="block"><span className="text-xs text-stone-500">{label}</span><span className="block mt-1">{children}</span></label>;
}

/** What a step can check or wait for. A reply ends the journey by itself, so it isn't on the list. */
function tests(meta: Journeys, current: string) {
    const found = [
        ...Object.entries(meta.tests).filter(([k]) => k !== "replied").map(([value, label]) => ({ value, label })),
        ...Object.entries(meta.statuses).map(([k, v]) => ({ value: `status:${k}`, label: `Their status is ${v}` })),
        ...meta.details.map((d) => ({ value: `detail:${d}`, label: `You know their ${d}` })),
    ];
    return current && !found.some((t) => t.value === current) ? [...found, { value: current, label: current }] : found;
}

function waitMode(step: Extract<JourneyStep, { type: "wait" }>) {
    return step.weekday ? "weekday" : step.until ? "until" : "time";
}

function StepFields({ step, set, meta }: { step: JourneyStep; set: (s: JourneyStep) => void; meta: Journeys }) {
    switch (step.type) {
    case "email":
        return (
            <div className="space-y-2">
                <Field label="Subject"><Input value={step.subject} maxLength={200} onChange={(e) => set({ ...step, subject: e.target.value })} /></Field>
                <Field label="Message"><Textarea rows={5} maxLength={5000} value={step.body} onChange={(e) => set({ ...step, body: e.target.value })} /></Field>
                <p className="text-xs text-stone-500">Fills in by itself: {"{{first_name|there}}"}, {"{{business}}"}, {"{{feedback_link}}"}, and anything you collected, such as {"{{city}}"}.</p>
                <Check label="Let the AI fit it to each person (one AI reply each; it never adds prices or dates you didn't give it)" checked={!!step.ai} onChange={(ai) => set({ ...step, ai })} />
            </div>
        );
    case "wait": {
        const mode = waitMode(step);
        const times = (
            <>
                <Field label="Days"><Input type="number" min={0} max={365} value={step.days ?? 0} onChange={(e) => set({ ...step, days: Number(e.target.value) })} /></Field>
                <Field label="Hours"><Input type="number" min={0} max={23} value={step.hours ?? 0} onChange={(e) => set({ ...step, hours: Number(e.target.value) })} /></Field>
            </>
        );
        return (
            <div className="grid sm:grid-cols-3 gap-3">
                <Field label="Wait">
                    <Select aria-label="How to wait" value={mode} onChange={(e) => set(e.target.value === "weekday" ? { type: "wait", weekday: "mon", at: "10:00" }
                        : e.target.value === "until" ? { type: "wait", days: 3, hours: 0, until: "booked" } : { type: "wait", days: 2, hours: 0 })}>
                        <option value="time">For a time</option>
                        <option value="weekday">Until a day and hour</option>
                        <option value="until">Until something happens</option>
                    </Select>
                </Field>
                {mode === "time" && times}
                {mode === "weekday" && <>
                    <Field label="Day">
                        <Select value={step.weekday} onChange={(e) => set({ ...step, weekday: e.target.value })}>{meta.days.map((d) => <option key={d} value={d}>{DAY_LABEL[d] ?? d}</option>)}</Select>
                    </Field>
                    <Field label="Hour"><Input type="time" value={step.at ?? "10:00"} onChange={(e) => set({ ...step, at: e.target.value })} /></Field>
                </>}
                {mode === "until" && <>
                    <Field label="Until">
                        <Select value={step.until} onChange={(e) => set({ ...step, until: e.target.value })}>{tests(meta, step.until ?? "").map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}</Select>
                    </Field>
                    <Field label="Or at most (days)"><Input type="number" min={0} max={365} value={step.days ?? 0} onChange={(e) => set({ ...step, days: Number(e.target.value) })} /></Field>
                </>}
            </div>
        );
    }
    case "whatsapp":
        return (
            <div className="space-y-2">
                <Field label="Message"><Textarea rows={3} maxLength={1000} value={step.text} onChange={(e) => set({ ...step, text: e.target.value })} /></Field>
                <p className="text-xs text-stone-500">Inside WhatsApp&apos;s 24-hour window it goes on WhatsApp. Outside it, the same words go by email, which costs far less than a template.</p>
                <Field label="Approved template, only for people without an email (optional)"><Input value={step.template ?? ""} maxLength={120} onChange={(e) => set({ ...step, template: e.target.value })} /></Field>
            </div>
        );
    case "call":
        return (
            <div className="space-y-2">
                <Field label="What the call is for"><Input value={step.about} maxLength={300} placeholder="Follow up on their enquiry and offer a meeting" onChange={(e) => set({ ...step, about: e.target.value })} /></Field>
                <p className="text-xs text-stone-500">A follow-up call from Voice &gt; Schedule: it uses that page&apos;s hours and limits, and needs follow-ups turned on there. It won&apos;t ring more than 7 days after they last spoke with you.</p>
            </div>
        );
    case "branch":
        return (
            <div className="grid sm:grid-cols-3 gap-3">
                <Field label="If">
                    <Select value={step.if} onChange={(e) => set({ ...step, if: e.target.value })}>{tests(meta, step.if).map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}</Select>
                </Field>
                <Field label="Is">
                    <Select value={step.not ? "no" : "yes"} onChange={(e) => set({ ...step, not: e.target.value === "no" })}>
                        <option value="yes">True</option>
                        <option value="no">Not true</option>
                    </Select>
                </Field>
                <Field label="Then">
                    <Select value={step.then === "end" ? "end" : String(step.skip ?? 1)} onChange={(e) => set(e.target.value === "end" ? { ...step, then: "end" } : { ...step, then: "skip", skip: Number(e.target.value) })}>
                        <option value="end">End the journey</option>
                        {[1, 2, 3].map((n) => <option key={n} value={n}>Skip the next {n === 1 ? "step" : `${n} steps`}</option>)}
                    </Select>
                </Field>
            </div>
        );
    case "update":
        return (
            <div className="grid sm:grid-cols-2 gap-3">
                <Field label="Stage">
                    <Select value={step.stage ?? ""} onChange={(e) => set({ ...step, stage: e.target.value })}>
                        <option value="">No change</option>
                        {meta.stages.map((s) => <option key={s} value={s}>{STAGE_LABEL[s] ?? s}</option>)}
                    </Select>
                </Field>
                <Field label="Lead status">
                    <Select value={step.status ?? ""} onChange={(e) => set({ ...step, status: e.target.value })}>
                        <option value="">No change</option>
                        {Object.entries(meta.statuses).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                    </Select>
                </Field>
                <Field label="Add a tag"><Input value={step.tag ?? ""} maxLength={40} onChange={(e) => set({ ...step, tag: e.target.value })} /></Field>
                <Field label="Looked after by">
                    <Select value={step.owner ?? ""} onChange={(e) => set({ ...step, owner: e.target.value })}>
                        <option value="">No change</option>
                        {meta.team.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
                    </Select>
                </Field>
            </div>
        );
    case "notify":
        return (
            <div className="space-y-2">
                <Field label="What to tell them"><Textarea rows={2} maxLength={500} value={step.text} onChange={(e) => set({ ...step, text: e.target.value })} /></Field>
                <Check label="Make it a to-do in Voice > Schedule (needs their number)" checked={!!step.todo} onChange={(todo) => set({ ...step, todo })} />
            </div>
        );
    }
}

function People({ id }: { id: string }) {
    const runs = useApi<JourneyRunRow[]>(`/api/email/journeys/${id}/runs`);
    const rows = runs.data ?? [];
    return (
        <Card>
            <div className="px-5 pt-4 pb-3 border-b border-line"><h3 className="text-sm font-medium">Who&apos;s on it</h3></div>
            {rows.length === 0 ? <p className="px-5 py-4 text-[13px] text-stone-500">Nobody yet. People start when it&apos;s on and its trigger happens.</p> : (
                <ul>
                    {rows.map((r) => {
                        const s = RUN_STATUS[r.status];
                        return (
                            <li key={r.id} className="px-5 py-3 border-t border-line first:border-t-0">
                                <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                                    <span className="text-sm min-w-0 flex-1 truncate">{r.name || r.email || "Someone"}</span>
                                    <Status tone={s.tone}>{s.text}</Status>
                                </div>
                                <p className="text-[13px] text-stone-500 mt-0.5">{r.status === "active" ? (r.next_at ? `Next: ${formatWhen(r.next_at)}` : "Working on it") : r.reason}</p>
                                {r.history.length > 0 && (
                                    <details className="mt-1 text-[13px] text-stone-600">
                                        <summary className="cursor-pointer text-stone-500">What happened</summary>
                                        <ul className="mt-1 space-y-0.5">{r.history.map((h, n) => <li key={n}>{formatWhen(h.at)}: {h.what}</li>)}</ul>
                                    </details>
                                )}
                            </li>
                        );
                    })}
                </ul>
            )}
        </Card>
    );
}

/** One journey, as a list of steps: it works on a phone, and nothing runs until it's turned on. */
export function JourneyEditor({ journey, meta, onBack, onChanged }: { journey: Journey; meta: Journeys; onBack: () => void; onChanged: () => void }) {
    const toast = useToast();
    const [saved, setSaved] = useState(journey);
    const [draft, setDraft] = useState(journey);
    const [busy, setBusy] = useState(false);
    const [removing, setRemoving] = useState(false);
    const changed = JSON.stringify([draft.name, draft.trigger, draft.trigger_value, draft.goal, draft.options, draft.steps]) !== JSON.stringify([saved.name, saved.trigger, saved.trigger_value, saved.goal, saved.options, saved.steps]);

    const save = async (enabled: boolean) => {
        setBusy(true);
        try {
            const done = await apiJson<Journey>(`/api/email/journeys/${journey.id}`, {
                method: "PUT", json: { name: draft.name, trigger: draft.trigger, trigger_value: draft.trigger_value, goal: draft.goal, options: draft.options, steps: draft.steps, enabled },
            });
            setSaved(done);
            setDraft(done);
            onChanged();
            toast(enabled === saved.enabled ? "Saved" : enabled ? "It's on: people start when its trigger happens" : "It's off: nobody new starts, and those on it stop");
        } catch (e) {
            toast((e as Error).message);
        } finally {
            setBusy(false);
        }
    };
    const remove = async () => {
        setBusy(true);
        try {
            await apiJson(`/api/email/journeys/${journey.id}`, { method: "DELETE" });
            onChanged();
            onBack();
        } catch (e) {
            toast((e as Error).message);
            setBusy(false);
        }
    };
    const setStep = (n: number, step: JourneyStep) => setDraft({ ...draft, steps: draft.steps.map((s, i) => (i === n ? step : s)) });
    const move = (n: number, by: number) => {
        const steps = [...draft.steps];
        [steps[n], steps[n + by]] = [steps[n + by], steps[n]];
        setDraft({ ...draft, steps });
    };

    return (
        <div className="space-y-5">
            <button type="button" onClick={onBack} className="text-sm text-plum hover:underline">Back to journeys</button>
            <Card className="p-5 space-y-4">
                <div className="flex flex-wrap items-end gap-3">
                    <div className="flex-1 min-w-48"><Field label="Name"><Input value={draft.name} maxLength={120} onChange={(e) => setDraft({ ...draft, name: e.target.value })} /></Field></div>
                    <div className="flex items-center gap-2 pb-1.5">
                        <span className="text-sm">{saved.enabled ? "On" : "Off"}</span>
                        <Switch checked={saved.enabled} disabled={busy} onChange={save} label="Turn this journey on" />
                    </div>
                </div>
                <div className="grid sm:grid-cols-3 gap-3">
                    <Field label="Starts when">
                        <Select value={draft.trigger} onChange={(e) => setDraft({ ...draft, trigger: e.target.value, trigger_value: e.target.value === "status" ? "hot" : null })}>
                            {Object.entries(meta.triggers).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                        </Select>
                    </Field>
                    {draft.trigger === "new_lead" && (
                        <Field label="From">
                            <Select value={draft.trigger_value ?? ""} onChange={(e) => setDraft({ ...draft, trigger_value: e.target.value || null })}>
                                <option value="">Anywhere</option>
                                {Object.entries(meta.sources).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                            </Select>
                        </Field>
                    )}
                    {draft.trigger === "status" && (
                        <Field label="Becomes">
                            <Select value={draft.trigger_value ?? ""} onChange={(e) => setDraft({ ...draft, trigger_value: e.target.value })}>
                                {Object.entries(meta.statuses).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                            </Select>
                        </Field>
                    )}
                    {draft.trigger === "date" && <>
                        <Field label="Which detail holds the date">
                            <Input list="journey-details" value={draft.trigger_value ?? ""} maxLength={60} placeholder="service_due" onChange={(e) => setDraft({ ...draft, trigger_value: e.target.value })} />
                            <datalist id="journey-details">{meta.details.map((d) => <option key={d} value={d} />)}</datalist>
                        </Field>
                        <Field label="Days before">
                            <Input type="number" min={0} max={365} value={draft.options.days_before ?? 0} onChange={(e) => setDraft({ ...draft, options: { ...draft.options, days_before: Number(e.target.value) } })} />
                        </Field>
                    </>}
                    <Field label="Ends when">
                        <Select value={draft.goal ?? ""} onChange={(e) => setDraft({ ...draft, goal: e.target.value || null })}>
                            <option value="">It reaches the last step</option>
                            {Object.entries(meta.goals).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                        </Select>
                    </Field>
                </div>
                {draft.trigger === "date" && <Check label="Every year, such as a birthday" checked={!!draft.options.yearly} onChange={(yearly) => setDraft({ ...draft, options: { ...draft.options, yearly } })} />}
                <p className="text-[13px] text-stone-500">A reply from them ends it too, and an unsubscribe or the do-not-call list stops it before the next step.</p>
            </Card>
            <ol className="space-y-3">
                {draft.steps.map((step, n) => {
                    const kind = STEP_KINDS.find((k) => k.type === step.type)!;
                    const Icon = kind.icon;
                    return (
                        <li key={n}>
                            <Card className="p-5">
                                <div className="flex items-center gap-2 mb-3">
                                    <Icon size={15} className="text-plum shrink-0" aria-hidden />
                                    <h3 className="text-sm font-medium flex-1">{n + 1}. {kind.label}</h3>
                                    <Button size="sm" variant="ghost" disabled={n === 0} aria-label={`Move step ${n + 1} up`} onClick={() => move(n, -1)}><ArrowUp size={13} aria-hidden /></Button>
                                    <Button size="sm" variant="ghost" disabled={n === draft.steps.length - 1} aria-label={`Move step ${n + 1} down`} onClick={() => move(n, 1)}><ArrowDown size={13} aria-hidden /></Button>
                                    <Button size="sm" variant="ghost" aria-label={`Remove step ${n + 1}`} onClick={() => setDraft({ ...draft, steps: draft.steps.filter((_, i) => i !== n) })}><Trash2 size={13} aria-hidden /></Button>
                                </div>
                                <StepFields step={step} set={(s) => setStep(n, s)} meta={meta} />
                            </Card>
                        </li>
                    );
                })}
            </ol>
            <Card className="p-4">
                <p className="text-xs text-stone-500 mb-2">Add a step</p>
                <div className="flex flex-wrap gap-2">
                    {STEP_KINDS.map((k) => <Button key={k.type} size="sm" onClick={() => setDraft({ ...draft, steps: [...draft.steps, k.blank] })}><Plus size={13} aria-hidden /> {k.add}</Button>)}
                </div>
            </Card>
            <People id={journey.id} />
            <div><Button variant="ghost" onClick={() => setRemoving(true)}>Delete this journey</Button></div>
            <Dialog open={removing} onClose={() => setRemoving(false)} title="Delete this journey?" description="Everyone on it stops, and emails waiting to go are cancelled."
                    footer={<>
                        <Button variant="ghost" onClick={() => setRemoving(false)}>Keep it</Button>
                        <Button variant="primary" disabled={busy} onClick={remove}>Delete</Button>
                    </>}>
                <span />
            </Dialog>
            <SaveBar visible={changed} saving={busy} onDiscard={() => setDraft(saved)} onSave={() => save(saved.enabled)} />
        </div>
    );
}
