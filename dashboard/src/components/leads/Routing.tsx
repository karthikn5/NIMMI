"use client";

import { useEffect, useState } from "react";
import { Button, Card, Input, Select, Skeleton, Switch, useToast } from "@/components/ui";
import { apiJson } from "@/lib/api";
import type { LeadRouting } from "@/lib/leads";
import { useApi } from "@/lib/useApi";

/** Who gets each assistant's new leads, and how long they have before the lead moves to the backup. */
export function Routing({ botId }: { botId: string }) {
    const toast = useToast();
    const page = useApi<LeadRouting>(`/api/crm/settings/${botId}`);
    const [draft, setDraft] = useState<LeadRouting["settings"] | null>(null);
    const [saving, setSaving] = useState(false);
    useEffect(() => { if (page.data) setDraft(page.data.settings); }, [page.data]);
    if (page.error) return <p className="text-sm text-signal">{page.error}</p>;
    if (!page.data || !draft) return <Skeleton className="h-40" />;
    const team = page.data.team;
    const set = (values: Partial<LeadRouting["settings"]>) => setDraft({ ...draft, ...values });
    const dirty = JSON.stringify(draft) !== JSON.stringify(page.data.settings);
    const toggle = (id: string) => set({ people: draft.people.includes(id) ? draft.people.filter((p) => p !== id) : [...draft.people, id] });
    const save = async () => {
        setSaving(true);
        try {
            await apiJson(`/api/crm/settings/${botId}`, { method: "PUT", json: draft });
            await page.reload();
            toast("Saved");
        } catch (e) {
            toast((e as Error).message);
        } finally {
            setSaving(false);
        }
    };
    return (
        <Card>
            <div className="px-5 pt-4 pb-3 border-b border-line">
                <h2 className="text-sm font-medium">Who gets new leads</h2>
                <p className="text-[13px] text-stone-500 mt-0.5">Leads from every place, for this assistant. A lead someone already looks after stays with them.</p>
            </div>
            <div className="p-5 space-y-4">
                <label className="block max-w-sm">
                    <span className="text-xs text-stone-500">New leads go to</span>
                    <Select className="mt-1" aria-label="New leads go to" value={draft.assign} onChange={(e) => set({ assign: e.target.value as LeadRouting["settings"]["assign"], people: e.target.value === "one" ? draft.people.slice(0, 1) : draft.people })}>
                        <option value="off">Nobody yet: a manager gives them out</option>
                        <option value="one">One person</option>
                        <option value="turns">The team, by turns</option>
                    </Select>
                </label>
                {draft.assign === "one" && (
                    <label className="block max-w-sm">
                        <span className="text-xs text-stone-500">Person</span>
                        <Select className="mt-1" aria-label="Person" value={draft.people[0] ?? ""} onChange={(e) => set({ people: e.target.value ? [e.target.value] : [] })}>
                            <option value="">Choose someone</option>
                            {team.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
                        </Select>
                    </label>
                )}
                {draft.assign === "turns" && (
                    <fieldset>
                        <legend className="text-xs text-stone-500">Who takes turns</legend>
                        <div className="mt-1.5 space-y-1.5">
                            {team.map((t) => (
                                <label key={t.id} className="flex items-center gap-2 text-sm">
                                    <input type="checkbox" className="accent-plum" checked={draft.people.includes(t.id)} onChange={() => toggle(t.id)} />
                                    {t.name}
                                </label>
                            ))}
                        </div>
                    </fieldset>
                )}
                <div className="flex items-center justify-between gap-4 max-w-sm">
                    <span className="text-sm">Make a first task for each new lead</span>
                    <Switch label="Make a first task for each new lead" checked={draft.first_task} onChange={(v) => set({ first_task: v })} />
                </div>
                {draft.first_task && (
                    <div className="grid sm:grid-cols-2 gap-3 max-w-xl">
                        <label className="block">
                            <span className="text-xs text-stone-500">Minutes to respond</span>
                            <Input className="mt-1" type="number" min={1} max={1440} value={draft.respond_minutes} onChange={(e) => set({ respond_minutes: Math.min(Math.max(Number(e.target.value) || 1, 1), 1440) })} />
                        </label>
                        <label className="block">
                            <span className="text-xs text-stone-500">If nobody does it in time, it goes to</span>
                            <Select className="mt-1" aria-label="Backup" value={draft.backup ?? ""} onChange={(e) => set({ backup: e.target.value || null })}>
                                <option value="">Nobody: it just stays overdue</option>
                                {team.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
                            </Select>
                        </label>
                    </div>
                )}
                {"whatsapp_first" in draft && (
                    <div className="border-t border-line pt-4 space-y-3 max-w-xl">
                        <h3 className="text-sm font-medium">On WhatsApp</h3>
                        <p className="text-[13px] text-stone-500">Templates you made and Meta approved in WhatsApp Manager, by their exact name. Leave empty to send nothing.</p>
                        <div className="grid sm:grid-cols-[1fr_120px] gap-3">
                            <label className="block">
                                <span className="text-xs text-stone-500">First message to a new lead who said yes to WhatsApp</span>
                                <Input aria-label="First WhatsApp message template" className="mt-1" placeholder="new_lead_hello" maxLength={512} value={draft.whatsapp_first ?? ""} onChange={(e) => set({ whatsapp_first: e.target.value.trim() || null })} />
                                <span className="block text-xs text-stone-500 mt-1">{"{{1}}"} is their first name, {"{{2}}"} your business. Only people who ticked yes or wrote to you get it: a form alone isn&apos;t a yes.</span>
                            </label>
                            <label className="block">
                                <span className="text-xs text-stone-500">Language</span>
                                <Input aria-label="First message language" className="mt-1" placeholder="en" maxLength={12} value={draft.whatsapp_language ?? "en"} onChange={(e) => set({ whatsapp_language: e.target.value.trim() })} />
                            </label>
                        </div>
                        <div className="grid sm:grid-cols-[1fr_120px] gap-3">
                            <label className="block">
                                <span className="text-xs text-stone-500">Alert to whoever gets the lead</span>
                                <Input aria-label="Lead alert template" className="mt-1" placeholder="lead_alert" maxLength={512} value={draft.alert_template ?? ""} onChange={(e) => set({ alert_template: e.target.value.trim() || null })} />
                                <span className="block text-xs text-stone-500 mt-1">{"{{1}}"} is the lead, {"{{2}}"} the link to it. It goes to the WhatsApp number on their Profile, and to the backup when it&apos;s late.</span>
                            </label>
                            <label className="block">
                                <span className="text-xs text-stone-500">Language</span>
                                <Input aria-label="Lead alert language" className="mt-1" placeholder="en" maxLength={12} value={draft.alert_language ?? "en"} onChange={(e) => set({ alert_language: e.target.value.trim() })} />
                            </label>
                        </div>
                    </div>
                )}
                {dirty && <Button variant="primary" disabled={saving} onClick={save}>Save</Button>}
            </div>
        </Card>
    );
}
