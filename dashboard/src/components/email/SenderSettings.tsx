"use client";

import { useEffect, useState } from "react";
import { Button, Card, Input, Select, Skeleton, useToast } from "@/components/ui";
import { apiJson } from "@/lib/api";
import type { SenderFields, Senders, SendsAs } from "@/lib/email";
import { useApi } from "@/lib/useApi";

/** Who customer emails come from: the workspace's default, and each assistant's own (empty = the default's). */
export function SenderSettings({ reloadKey }: { reloadKey?: number }) {
    const senders = useApi<Senders>("/api/email/senders");
    const { reload } = senders;
    useEffect(() => { if (reloadKey) void reload(); }, [reloadKey, reload]);

    return (
        <Card>
            <div className="px-5 pt-4 pb-3">
                <h2 className="text-sm font-medium">Who emails come from</h2>
                <p className="text-[13px] text-stone-500 mt-0.5 max-w-2xl">
                    The name people see, the address it&apos;s sent from, and where their replies go. Each assistant can have its own; what it leaves
                    empty comes from &ldquo;All assistants&rdquo;.
                </p>
            </div>
            {senders.error ? <p className="px-5 pb-4 text-sm text-signal">{senders.error}</p> : !senders.data ? (
                <div className="px-5 pb-5 space-y-3"><Skeleton className="h-24" /><Skeleton className="h-24" /></div>
            ) : (
                <ul>
                    <SenderRow id="default" title="All assistants" fields={senders.data.default} sendsAs={senders.data.default.sends_as}
                               data={senders.data} onSaved={senders.setData} />
                    {senders.data.assistants.map((a) => (
                        <SenderRow key={a.bot_id} id={a.bot_id} title={a.bot_name} fields={a} sendsAs={a.sends_as}
                                   data={senders.data!} onSaved={senders.setData} />
                    ))}
                </ul>
            )}
        </Card>
    );
}

function SenderRow({ id, title, fields, sendsAs, data, onSaved }: {
    id: string; title: string; fields: SenderFields; sendsAs: SendsAs; data: Senders; onSaved: (s: Senders) => void;
}) {
    const toast = useToast();
    const pick = (f: SenderFields): SenderFields => ({ from_name: f.from_name, local_part: f.local_part, domain_id: f.domain_id, reply_to: f.reply_to });
    const [draft, setDraft] = useState<SenderFields>(pick(fields));
    const [saving, setSaving] = useState(false);
    useEffect(() => { setDraft(pick(fields)); }, [fields]);
    const dirty = JSON.stringify(draft) !== JSON.stringify(pick(fields));
    const isDefault = id === "default";
    const domain = data.domains.find((d) => d.id === draft.domain_id);
    const set = (k: keyof SenderFields, v: string) => setDraft({ ...draft, [k]: v });

    const save = async () => {
        setSaving(true);
        try {
            onSaved(await apiJson<Senders>(`/api/email/senders/${id}`, { method: "PUT", json: draft }));
            toast("Saved");
        } catch (e) {
            toast((e as Error).message);
        } finally {
            setSaving(false);
        }
    };

    return (
        <li className="border-t border-line px-5 py-4">
            <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 mb-3">
                <p className="text-sm font-medium">{title}</p>
                <p className="text-xs text-stone-500 min-w-0 break-all">
                    Sends as {sendsAs.name} &lt;{sendsAs.address}&gt;{sendsAs.reply_to ? `, replies to ${sendsAs.reply_to}` : ", replies: not set"}
                </p>
            </div>
            <div className="grid sm:grid-cols-2 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)_minmax(0,1fr)_auto] gap-3 items-end">
                <label className="block min-w-0">
                    <span className="text-xs text-stone-500">From name</span>
                    <Input className="mt-1" maxLength={60} value={draft.from_name} onChange={(e) => set("from_name", e.target.value)}
                           placeholder={isDefault ? "e.g. Sunrise Homes" : "Same as All assistants"} />
                </label>
                <div className="min-w-0">
                    <span className="text-xs text-stone-500">Address</span>
                    <div className="mt-1 flex items-center gap-1.5">
                        {/* Nimmi's own address can't be renamed; an assistant may name its own at the workspace's domain. */}
                        <Input aria-label={`${title}: the part before the @`} className="min-w-0" maxLength={64} value={draft.local_part}
                               disabled={isDefault && !draft.domain_id} onChange={(e) => set("local_part", e.target.value)}
                               placeholder={isDefault ? (draft.domain_id ? "hello" : data.nimmi_address.split("@")[0]) : "Same as All assistants"} />
                        <span className="text-stone-400" aria-hidden>@</span>
                        <Select aria-label={`${title}: the domain`} className="min-w-0" value={draft.domain_id} onChange={(e) => set("domain_id", e.target.value)}>
                            <option value="">{isDefault ? "Nimmi's address" : "Same as All assistants"}</option>
                            {data.domains.map((d) => <option key={d.id} value={d.id}>{d.name}{d.verified ? "" : " (not verified yet)"}</option>)}
                        </Select>
                    </div>
                    {domain && !domain.verified && <p className="text-[11px] text-amber-700 mt-1">Used once {domain.name} is verified; until then, Nimmi&apos;s address.</p>}
                </div>
                <label className="block min-w-0">
                    <span className="text-xs text-stone-500">Replies go to</span>
                    <Input className="mt-1" type="email" maxLength={200} value={draft.reply_to} onChange={(e) => set("reply_to", e.target.value)}
                           placeholder={isDefault ? "e.g. hello@sunrisehomes.in" : "Same as All assistants"} />
                </label>
                <Button onClick={save} disabled={!dirty || saving} variant={dirty ? "primary" : "secondary"}>{saving ? "Saving…" : "Save"}</Button>
            </div>
        </li>
    );
}
