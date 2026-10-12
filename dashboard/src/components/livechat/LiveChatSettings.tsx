"use client";

import { useEffect, useState } from "react";
import { Plus, Trash2, X } from "lucide-react";
import { Button, Input, Sheet, Skeleton, Status, Switch, Textarea, cn, useToast } from "@/components/ui";
import { apiSave, useApi } from "@/lib/useApi";

export type Day = "mon" | "tue" | "wed" | "thu" | "fri" | "sat" | "sun";
export type Hours = {
    enabled: boolean;
    days: Record<Day, { open: boolean; from: string; to: string }>;
    holidays: string[];
    away_message: string;
};
export type WorkspaceSettings = { business_hours: Hours; escalate_upset: boolean; open_now: boolean; next_open: string | null };
export type SavedReply = { id: string; title: string; body: string };

const DAYS: [Day, string][] = [["mon", "Monday"], ["tue", "Tuesday"], ["wed", "Wednesday"], ["thu", "Thursday"],
                               ["fri", "Friday"], ["sat", "Saturday"], ["sun", "Sunday"]];

export function LiveChatSettings({ open, onClose, onSaved, replies, onRepliesChange }: {
    open: boolean; onClose: () => void; onSaved: (s: WorkspaceSettings) => void;
    replies: SavedReply[] | null; onRepliesChange: () => void;
}) {
    const toast = useToast();
    const settings = useApi<WorkspaceSettings>(open ? "/api/workspace/settings" : null);
    const [draft, setDraft] = useState<WorkspaceSettings | null>(null);
    const [holiday, setHoliday] = useState("");
    const [saving, setSaving] = useState(false);
    useEffect(() => { if (settings.data) setDraft(settings.data); }, [settings.data]);

    const hours = draft?.business_hours;
    const setHours = (patch: Partial<Hours>) => draft && setDraft({ ...draft, business_hours: { ...draft.business_hours, ...patch } });
    const setDay = (d: Day, patch: Partial<Hours["days"][Day]>) => hours && setHours({ days: { ...hours.days, [d]: { ...hours.days[d], ...patch } } });

    const save = async () => {
        if (!draft) return;
        setSaving(true);
        const res = await apiSave("/api/workspace/settings", "PUT", { business_hours: draft.business_hours, escalate_upset: draft.escalate_upset });
        setSaving(false);
        if (!res.ok) return toast(res.message);
        toast("Saved");
        onSaved(res.data as WorkspaceSettings);
        settings.setData(res.data as WorkspaceSettings);
    };

    return (
        <Sheet open={open} onClose={onClose} title="Live chat settings" subtitle="When your team is available, and how assistants hand over.">
            {!draft || !hours ? <div className="p-6"><Skeleton className="h-96" /></div> : (
                <div className="divide-y divide-line">
                    <section className="px-6 py-5">
                        <div className="flex items-start justify-between gap-4">
                            <div>
                                <h3 className="text-sm font-medium">Business hours</h3>
                                <p className="text-[13px] text-stone-500 mt-0.5">
                                    Outside these hours, &quot;talk to a person&quot; gets your away message, and calls aren&apos;t transferred. India time.
                                </p>
                            </div>
                            <Switch checked={hours.enabled} onChange={(v) => setHours({ enabled: v })} label="Use business hours" />
                        </div>
                        <div className={cn("mt-4 space-y-1.5", !hours.enabled && "opacity-50 pointer-events-none")}>
                            {DAYS.map(([d, label]) => (
                                <div key={d} className="grid grid-cols-[6.5rem_auto_minmax(0,1fr)] items-center gap-3">
                                    <span className="text-[13px]">{label}</span>
                                    <Switch checked={hours.days[d].open} onChange={(v) => setDay(d, { open: v })} label={`Open on ${label}`} />
                                    {hours.days[d].open ? (
                                        <div className="flex items-center gap-1.5">
                                            <Input type="time" aria-label={`${label} opens`} className="h-8 w-28 tabular-nums" value={hours.days[d].from} onChange={(e) => setDay(d, { from: e.target.value })} />
                                            <span className="text-xs text-stone-500">to</span>
                                            <Input type="time" aria-label={`${label} closes`} className="h-8 w-28 tabular-nums" value={hours.days[d].to} onChange={(e) => setDay(d, { to: e.target.value })} />
                                        </div>
                                    ) : <span className="text-[13px] text-stone-400">Closed</span>}
                                </div>
                            ))}

                            <div className="pt-4">
                                <span className="text-[13px] font-medium">Holidays</span>
                                <div className="flex flex-wrap items-center gap-1.5 mt-1.5">
                                    {hours.holidays.map((h) => (
                                        <span key={h} className="inline-flex items-center gap-1 h-7 pl-2.5 pr-1 rounded bg-stone-100 text-xs tabular-nums">
                                            {new Date(`${h}T00:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })}
                                            <button type="button" aria-label={`Remove ${h}`} onClick={() => setHours({ holidays: hours.holidays.filter((x) => x !== h) })}
                                                    className="p-0.5 rounded text-stone-400 hover:text-ink"><X size={12} /></button>
                                        </span>
                                    ))}
                                    <Input type="date" aria-label="Add a holiday" className="h-8 w-40" value={holiday} onChange={(e) => setHoliday(e.target.value)} />
                                    <Button size="sm" disabled={!holiday} onClick={() => { setHours({ holidays: [...new Set([...hours.holidays, holiday])].sort() }); setHoliday(""); }}>Add</Button>
                                </div>
                            </div>

                            <div className="pt-4">
                                <label htmlFor="away" className="text-[13px] font-medium">Away message</label>
                                <Textarea id="away" className="mt-1.5" rows={3} maxLength={400} value={hours.away_message} onChange={(e) => setHours({ away_message: e.target.value })} />
                                <p className="text-xs text-stone-500 mt-1">
                                    <code className="text-[11px] bg-stone-100 rounded px-1">{"{next_open}"}</code> becomes when you&apos;re back, like &quot;tomorrow at 9:00 AM&quot;.
                                </p>
                            </div>
                        </div>
                    </section>

                    <section className="px-6 py-5 flex items-start justify-between gap-4">
                        <div>
                            <h3 className="text-sm font-medium">Hand upset customers to a person</h3>
                            <p className="text-[13px] text-stone-500 mt-0.5">
                                When someone is clearly unhappy (strong words, &quot;worst service&quot;, &quot;bakwas&quot;, shouting), the assistant apologises and brings in your team.
                            </p>
                        </div>
                        <Switch checked={draft.escalate_upset} onChange={(v) => setDraft({ ...draft, escalate_upset: v })} label="Hand upset customers to a person" />
                    </section>

                    <div className="px-6 py-4 flex items-center justify-between gap-3 bg-stone-50/60">
                        <Status tone={settings.data?.open_now ? "good" : "warn"}>
                            {settings.data?.open_now ? "Open now" : `Closed, back ${settings.data?.next_open}`}
                        </Status>
                        <Button variant="primary" onClick={save} disabled={saving}>{saving ? "Saving…" : "Save settings"}</Button>
                    </div>

                    <SavedRepliesManager replies={replies} onChange={onRepliesChange} />
                </div>
            )}
        </Sheet>
    );
}

function SavedRepliesManager({ replies, onChange }: { replies: SavedReply[] | null; onChange: () => void }) {
    const toast = useToast();
    const [editing, setEditing] = useState<SavedReply | { id: ""; title: string; body: string } | null>(null);

    const save = async () => {
        if (!editing) return;
        const res = editing.id
            ? await apiSave(`/api/workspace/replies/${editing.id}`, "PUT", { title: editing.title, body: editing.body })
            : await apiSave("/api/workspace/replies", "POST", { title: editing.title, body: editing.body });
        if (!res.ok) return toast(res.message);
        setEditing(null);
        onChange();
    };
    const remove = async (r: SavedReply) => {
        const res = await apiSave(`/api/workspace/replies/${r.id}`, "DELETE");
        if (!res.ok) return toast(res.message);
        onChange();
    };

    return (
        <section className="px-6 py-5">
            <div className="flex items-start justify-between gap-4">
                <div>
                    <h3 className="text-sm font-medium">Saved replies</h3>
                    <p className="text-[13px] text-stone-500 mt-0.5">Answers your team sends often. Type / in a reply to use one.</p>
                </div>
                <Button size="sm" onClick={() => setEditing({ id: "", title: "", body: "" })}><Plus size={13} /> New</Button>
            </div>
            {editing && (
                <div className="mt-3 p-3 rounded-md border border-line space-y-2">
                    <Input aria-label="Name" placeholder="Name, e.g. Timings" maxLength={80} value={editing.title} onChange={(e) => setEditing({ ...editing, title: e.target.value })} />
                    <Textarea aria-label="Reply text" rows={3} maxLength={2000} placeholder="The reply your team sends" value={editing.body}
                              onChange={(e) => setEditing({ ...editing, body: e.target.value })} />
                    <div className="flex justify-end gap-2">
                        <Button size="sm" variant="ghost" onClick={() => setEditing(null)}>Cancel</Button>
                        <Button size="sm" variant="primary" onClick={save} disabled={!editing.title.trim() || !editing.body.trim()}>Save reply</Button>
                    </div>
                </div>
            )}
            <ul className="mt-3 space-y-1.5">
                {replies === null && <Skeleton className="h-10" />}
                {replies?.length === 0 && !editing && <p className="text-[13px] text-stone-400">No saved replies yet.</p>}
                {replies?.map((r) => (
                    <li key={r.id} className="group flex items-start gap-3 px-3 py-2 rounded-md hover:bg-stone-50">
                        <button type="button" className="flex-1 min-w-0 text-left" onClick={() => setEditing(r)}>
                            <span className="block text-[13px] font-medium">{r.title}</span>
                            <span className="block text-xs text-stone-500 truncate">{r.body}</span>
                        </button>
                        <button type="button" aria-label={`Delete ${r.title}`} onClick={() => remove(r)}
                                className="p-1.5 rounded text-stone-400 hover:text-signal hover:bg-red-50"><Trash2 size={13} /></button>
                    </li>
                ))}
            </ul>
        </section>
    );
}
