"use client";

import { useEffect, useState, type ReactNode } from "react";
import Link from "next/link";
import { Card, Input, SaveBar, Select, SectionHeader, SettingRow, Skeleton, Switch, cn, useToast } from "@/components/ui";
import { apiSave, useApi } from "@/lib/useApi";
import { LEADS, MEETING_KINDS, TEMPLATE_BODY, TIME_ZONES, WEEKDAYS } from "@/lib/voice/schedule";
import type { FollowedUp, MeetingKind, ScheduleSettings, ScheduleSettingsView, Weekday } from "@/lib/voice/types";

function Toggle({ checked, onChange, label, children }: { checked: boolean; onChange: (v: boolean) => void; label: string; children?: ReactNode }) {
    return (
        <label className="flex items-start gap-3 text-sm">
            <Switch checked={checked} onChange={onChange} label={label} />
            <span className="text-stone-700">{children ?? (checked ? "On" : "Off")}</span>
        </label>
    );
}

function Hours({ value, onChange, label }: { value: [string, string]; onChange: (v: [string, string]) => void; label: string }) {
    return (
        <div className="flex items-center gap-2">
            <Input type="time" aria-label={`${label}: from`} className="w-32 tabular-nums" value={value[0]} onChange={(e) => onChange([e.target.value, value[1]])} />
            <span className="text-[13px] text-stone-500">to</span>
            <Input type="time" aria-label={`${label}: until`} className="w-32 tabular-nums" value={value[1]} onChange={(e) => onChange([value[0], e.target.value])} />
        </div>
    );
}

function Chips<T extends string>({ value, onChange, options, label }: {
    value: T[]; onChange: (v: T[]) => void; options: { value: T; label: string }[]; label: string;
}) {
    return (
        <div role="group" aria-label={label} className="flex flex-wrap gap-1.5">
            {options.map((o) => {
                const on = value.includes(o.value);
                return (
                    <button key={o.value} type="button" aria-pressed={on}
                            onClick={() => onChange(on ? value.filter((v) => v !== o.value) : options.filter((x) => x.value === o.value || value.includes(x.value)).map((x) => x.value))}
                            className={cn("h-8 px-3 rounded-md border text-[13px] transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-plum",
                                on ? "border-plum bg-plum/10 text-plum font-medium" : "border-line-strong bg-white text-stone-600 hover:bg-stone-50")}>
                        {o.label}
                    </button>
                );
            })}
        </div>
    );
}

const COUNTS = [0, 1, 2, 3, 4, 5];
const EVERY = [1, 2, 3, 4, 5, 7, 10, 14];

export function ScheduleSettingsForm({ botId }: { botId: string }) {
    const toast = useToast();
    const view = useApi<ScheduleSettingsView>(`/api/voice/schedule/settings/${botId}`);
    const [draft, setDraft] = useState<ScheduleSettings | null>(null);
    const [saving, setSaving] = useState(false);

    useEffect(() => { if (view.data) setDraft(view.data.settings); }, [view.data]);
    if (!draft || !view.data) return view.error ? <p className="text-sm text-signal">Couldn&apos;t load the settings. {view.error}</p> : <Skeleton className="h-96" />;

    const dirty = JSON.stringify(draft) !== JSON.stringify(view.data.settings);
    const cb = draft.callbacks, fu = draft.follow_ups, mt = draft.meetings;
    const setCb = (v: Partial<typeof cb>) => setDraft({ ...draft, callbacks: { ...cb, ...v } });
    const setFu = (v: Partial<typeof fu>) => setDraft({ ...draft, follow_ups: { ...fu, ...v } });
    const setMt = (v: Partial<typeof mt>) => setDraft({ ...draft, meetings: { ...mt, ...v } });
    const setRule = (status: FollowedUp, v: Partial<{ count: number; every: number }>) =>
        setFu({ rules: { ...fu.rules, [status]: { ...fu.rules[status], ...v } } });
    const save = async () => {
        setSaving(true);
        const res = await apiSave(`/api/voice/schedule/settings/${botId}`, "PUT", draft);
        setSaving(false);
        if (!res.ok) return toast(res.message);
        view.setData(res.data as ScheduleSettingsView);
        toast("Saved");
    };
    const noNumber = view.data.numbers.length === 0;

    return (
        <div className="space-y-10">
            {noNumber && (
                <p className="text-[13px] text-amber-800 bg-amber-50 border border-amber-200 rounded-md px-4 py-3">
                    These calls need a phone number to call from. <Link href="/dashboard/voice/numbers" className="underline underline-offset-4">Get a number</Link> first.
                </p>
            )}

            <section>
                <SectionHeader title="Call-backs" description="When a caller says “call me after 10 minutes” or “call me tomorrow at 11”, the agent books it and calls them then, from the number they called." />
                <Card className="px-5 py-1">
                    <SettingRow label="Book call-backs on calls">
                        <Toggle checked={cb.enabled} onChange={(v) => setCb({ enabled: v })} label="Book call-backs on calls" />
                    </SettingRow>
                    <SettingRow label="Calling hours" hint="Any day. For a time outside these, the agent offers the nearest one instead.">
                        <Hours value={cb.hours} onChange={(v) => setCb({ hours: v })} label="Call-back hours" />
                    </SettingRow>
                    <SettingRow label="If they don't pick up" htmlFor="cb-tries">
                        <div className="flex flex-wrap items-center gap-2">
                            <Select id="cb-tries" className="w-auto" value={cb.attempts} onChange={(e) => setCb({ attempts: Number(e.target.value) })}>
                                {[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n === 1 ? "Try once" : `Try ${n} times`}</option>)}
                            </Select>
                            {cb.attempts > 1 && (
                                <Select aria-label="Minutes between tries" className="w-auto" value={cb.retry_minutes} onChange={(e) => setCb({ retry_minutes: Number(e.target.value) })}>
                                    {[5, 10, 15, 30, 60].map((n) => <option key={n} value={n}>{n} minutes apart</option>)}
                                </Select>
                            )}
                        </div>
                    </SettingRow>
                </Card>
            </section>

            <section>
                <SectionHeader title="Follow-ups"
                               description="After each call the assistant rates the caller as a lead and writes what the next call should say. These rules decide how many follow-ups each rating gets." />
                <Card className="px-5 py-1">
                    <SettingRow label="Follow up with leads"
                                hint="They stop when someone books a meeting, asks for a call-back or a person, says no, opts out, or is marked a customer. Each new conversation starts the count again.">
                        <Toggle checked={fu.enabled} onChange={(v) => setFu({ enabled: v })} label="Follow up with leads" />
                    </SettingRow>
                    <SettingRow label="Check each one first" hint="Follow-ups wait in Schedule for your OK before the assistant makes them.">
                        <Toggle checked={fu.review} onChange={(v) => setFu({ review: v })} label="Check each follow-up first">
                            {fu.review ? "On: they wait for your OK" : "Off: made automatically"}
                        </Toggle>
                    </SettingRow>
                    <SettingRow label="How many, how often">
                        <table className="w-full text-[13px]">
                            <tbody>
                                {(["hot", "warm", "cold", "new"] as FollowedUp[]).map((status) => (
                                    <tr key={status} className="border-t border-line first:border-t-0">
                                        <td className="py-2 pr-3">
                                            <span className="font-medium text-ink">{LEADS[status].label}</span>
                                            <span className="block text-xs text-stone-500">{LEADS[status].about}</span>
                                        </td>
                                        <td className="py-2 pr-2">
                                            <Select aria-label={`${LEADS[status].label}: how many`} className="w-auto" value={fu.rules[status].count}
                                                    onChange={(e) => setRule(status, { count: Number(e.target.value) })}>
                                                {COUNTS.map((n) => <option key={n} value={n}>{n === 0 ? "None" : n === 1 ? "1 follow-up" : `${n} follow-ups`}</option>)}
                                            </Select>
                                        </td>
                                        <td className="py-2">
                                            {fu.rules[status].count > 0 && (
                                                <Select aria-label={`${LEADS[status].label}: days apart`} className="w-auto" value={fu.rules[status].every}
                                                        onChange={(e) => setRule(status, { every: Number(e.target.value) })}>
                                                    {EVERY.map((n) => <option key={n} value={n}>{n === 1 ? "every day" : `every ${n} days`}</option>)}
                                                </Select>
                                            )}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </SettingRow>
                    <SettingRow label="Stop after" htmlFor="fu-stop"
                                hint="Days since they last spoke with you. In India, consent to be called about an enquiry lasts 7 days (TRAI, 2025); keep it at 7 unless they've agreed to more.">
                        <div className="flex flex-wrap items-center gap-2">
                            <Select id="fu-stop" className="w-auto" value={fu.stop_after_days} onChange={(e) => setFu({ stop_after_days: Number(e.target.value) })}>
                                {[3, 5, 7, 10, 14, 30].map((n) => <option key={n} value={n}>{n} days</option>)}
                            </Select>
                            <Select aria-label="Most follow-ups per person" className="w-auto" value={fu.max_total} onChange={(e) => setFu({ max_total: Number(e.target.value) })}>
                                {[1, 2, 3, 4, 5, 6, 8, 10].map((n) => <option key={n} value={n}>at most {n} per person</option>)}
                            </Select>
                        </div>
                    </SettingRow>
                    <SettingRow label="Calling hours and days" hint="One follow-up a day at most, at about the hour they last picked up. No calls on your holidays (Settings > Business hours).">
                        <div className="space-y-3">
                            <Hours value={fu.hours} onChange={(v) => setFu({ hours: v })} label="Follow-up hours" />
                            <Chips label="Follow-up days" value={fu.days} onChange={(v) => v.length && setFu({ days: v as Weekday[] })} options={WEEKDAYS} />
                        </div>
                    </SettingRow>
                    <SettingRow label="If they don't pick up" htmlFor="fu-tries" hint="After the last try, the next follow-up in the rules is planned.">
                        <Select id="fu-tries" className="max-w-64" value={fu.attempts} onChange={(e) => setFu({ attempts: Number(e.target.value) })}>
                            <option value={1}>Don&apos;t try again that day</option>
                            <option value={2}>Try once more, 2 hours later</option>
                            <option value={3}>Try twice more, 2 hours apart</option>
                        </Select>
                    </SettingRow>
                    <p className="text-xs text-stone-500 leading-relaxed pb-4">
                        A follow-up that promotes or sells counts as a promotional call in India: it must come from a 140-series number,
                        and can&apos;t go to numbers on the national Do Not Disturb list unless they agreed. Call-backs people ask for and
                        calls about their meetings are service calls.
                    </p>
                </Card>
            </section>

            <section>
                <SectionHeader title="Meetings"
                               description="The agent offers your free times on the call and books the one the caller picks. You approve it, the assistant calls them to confirm, and they get the link before it starts." />
                <Card className="px-5 py-1">
                    <SettingRow label="Book meetings on calls">
                        <Toggle checked={mt.enabled} onChange={(v) => setMt({ enabled: v })} label="Book meetings on calls" />
                    </SettingRow>
                    <SettingRow label="Approve each request">
                        <Toggle checked={mt.approval} onChange={(v) => setMt({ approval: v })} label="Approve each meeting request">
                            {mt.approval ? "On: requests wait for your OK" : "Off: confirmed on the call"}
                        </Toggle>
                    </SettingRow>
                    <SettingRow label="Kinds of meeting">
                        <Chips label="Kinds of meeting" value={mt.kinds} onChange={(v) => v.length && setMt({ kinds: v as MeetingKind[] })}
                               options={(Object.keys(MEETING_KINDS) as MeetingKind[]).map((k) => ({ value: k, label: MEETING_KINDS[k] }))} />
                    </SettingRow>
                    {mt.kinds.includes("online") && (
                        <SettingRow label="Meeting link" htmlFor="mt-link" hint="Your Google Meet, Zoom or Teams room. You can give a meeting its own link when you approve it.">
                            <Input id="mt-link" value={mt.link} maxLength={500} placeholder="https://meet.google.com/abc-defg-hij" onChange={(e) => setMt({ link: e.target.value })} />
                        </SettingRow>
                    )}
                    {mt.kinds.includes("in_person") && (
                        <SettingRow label="Address" htmlFor="mt-address" hint="Where in-person meetings happen. It's sent with the reminders.">
                            <Input id="mt-address" value={mt.address} maxLength={300} placeholder="12 Anna Salai, Chennai 600002" onChange={(e) => setMt({ address: e.target.value })} />
                        </SettingRow>
                    )}
                    <SettingRow label="When your team meets" hint="The agent only offers times inside these, never on your holidays.">
                        <div className="space-y-3">
                            <Hours value={mt.hours} onChange={(v) => setMt({ hours: v })} label="Meeting hours" />
                            <Chips label="Meeting days" value={mt.days} onChange={(v) => v.length && setMt({ days: v as Weekday[] })} options={WEEKDAYS} />
                        </div>
                    </SettingRow>
                    <SettingRow label="Length and notice">
                        <div className="flex flex-wrap items-center gap-2">
                            <Select aria-label="Meeting length" className="w-auto" value={mt.minutes} onChange={(e) => setMt({ minutes: Number(e.target.value) })}>
                                {[15, 30, 45, 60, 90].map((n) => <option key={n} value={n}>{n} minutes</option>)}
                            </Select>
                            <Select aria-label="Notice" className="w-auto" value={mt.notice_hours} onChange={(e) => setMt({ notice_hours: Number(e.target.value) })}>
                                {[0, 1, 2, 4, 12, 24, 48].map((n) => <option key={n} value={n}>{n === 0 ? "no notice needed" : `${n} hours' notice`}</option>)}
                            </Select>
                            <Select aria-label="How far ahead" className="w-auto" value={mt.ahead_days} onChange={(e) => setMt({ ahead_days: Number(e.target.value) })}>
                                {[7, 14, 30, 60].map((n) => <option key={n} value={n}>up to {n} days ahead</option>)}
                            </Select>
                            <Select aria-label="Meetings at the same time" className="w-auto" value={mt.at_once} onChange={(e) => setMt({ at_once: Number(e.target.value) })}>
                                {[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n === 1 ? "one at a time" : `${n} at the same time`}</option>)}
                            </Select>
                        </div>
                    </SettingRow>
                    <SettingRow label="When to offer one" htmlFor="mt-when" hint="The agent always books one when a caller asks.">
                        <Input id="mt-when" value={mt.offer_when} maxLength={300} placeholder="they're interested and want to discuss details with the team"
                               onChange={(e) => setMt({ offer_when: e.target.value })} />
                    </SettingRow>
                    <SettingRow label="Confirm and remind">
                        <div className="space-y-3">
                            <Toggle checked={mt.confirm_call} onChange={(v) => setMt({ confirm_call: v })} label="Call to confirm">
                                Call them to confirm once you approve
                            </Toggle>
                            <div className="flex flex-wrap items-center gap-2 text-sm text-stone-700">
                                Send the joining details
                                <Select aria-label="Minutes before" className="w-auto" value={mt.link_minutes} onChange={(e) => setMt({ link_minutes: Number(e.target.value) })}>
                                    {[5, 10, 15, 30, 60].map((n) => <option key={n} value={n}>{n} minutes before</option>)}
                                </Select>
                            </div>
                            <Toggle checked={mt.day_before} onChange={(v) => setMt({ day_before: v })} label="Day-before reminder">A reminder the day before</Toggle>
                            <Toggle checked={mt.no_show_call} onChange={(v) => setMt({ no_show_call: v })} label="Call after a missed meeting">
                                If they don&apos;t join, call them to pick another time
                            </Toggle>
                        </div>
                    </SettingRow>
                    <SettingRow label="WhatsApp template" htmlFor="mt-template"
                                hint={<>
                                    Outside WhatsApp&apos;s 24-hour window, Meta only allows approved templates. In WhatsApp Manager &gt; Message templates,
                                    create a Utility template with this text, then enter its name here: <span className="font-mono text-[12px] text-ink">{TEMPLATE_BODY}</span>
                                    {!view.data.whatsapp && <> Connect a number in <Link href="/dashboard/whatsapp" className="text-plum underline underline-offset-4">WhatsApp</Link> first.</>}
                                    {" "}Email is used too, when they gave one.
                                </>}>
                        <div className="flex flex-wrap gap-2">
                            <Input id="mt-template" className="max-w-64" value={mt.whatsapp_template} maxLength={120} placeholder="meeting_update"
                                   onChange={(e) => setMt({ whatsapp_template: e.target.value.trim().toLowerCase() })} />
                            <Select aria-label="Template language" className="w-auto" value={mt.template_language} onChange={(e) => setMt({ template_language: e.target.value })}>
                                <option value="en">English</option>
                                <option value="en_US">English (US)</option>
                                <option value="en_GB">English (UK)</option>
                                <option value="hi">Hindi</option>
                                <option value="ta">Tamil</option>
                            </Select>
                        </div>
                    </SettingRow>
                </Card>
            </section>

            <section>
                <SectionHeader title="Calling from" />
                <Card className="px-5 py-1">
                    <SettingRow label="Call from" htmlFor="from-number" hint="People pick up more often when the number is one they know.">
                        <Select id="from-number" className="max-w-72" value={draft.from_number_id ?? ""} onChange={(e) => setDraft({ ...draft, from_number_id: e.target.value || null })}>
                            <option value="">The number they called (recommended)</option>
                            {view.data.numbers.map((n) => <option key={n.id} value={n.id}>{n.number}{n.own ? " (this assistant's)" : ""}</option>)}
                        </Select>
                    </SettingRow>
                    <SettingRow label="Time zone" htmlFor="tz" hint="For calling hours, meeting times and what the agent calls “tomorrow”.">
                        <Select id="tz" className="max-w-64" value={draft.timezone} onChange={(e) => setDraft({ ...draft, timezone: e.target.value })}>
                            {!TIME_ZONES.some((z) => z.value === draft.timezone) && <option value={draft.timezone}>{draft.timezone}</option>}
                            {TIME_ZONES.map((z) => <option key={z.value} value={z.value}>{z.label}</option>)}
                        </Select>
                    </SettingRow>
                </Card>
            </section>

            <SaveBar visible={dirty} saving={saving} onDiscard={() => setDraft(view.data!.settings)} onSave={save} />
        </div>
    );
}
