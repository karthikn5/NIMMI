"use client";

import { useEffect, useRef, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Button, Card, Notice, Select, Skeleton, Status, Switch, useToast } from "@/components/ui";
import { apiJson } from "@/lib/api";
import { inline } from "@/lib/leads";
import { formatWhen } from "@/lib/voice/api";
import { useApi } from "@/lib/useApi";

interface MetaForm {
    form_id: string;
    name: string;
    status: string;
    bot_id: string | null;
    settings: { email: boolean; call: boolean; whatsapp_tick?: string | null };
    ticks?: string[];  // the tick boxes this form's leads came with (missing on an older backend)
    last_lead_at: string | null;
    checked_through: string | null;
    waiting: { waiting?: number; new?: number; failed?: number };
}

interface MetaPage {
    page_id: string;
    name: string;
    subscribed: boolean;
    status: "active" | "token" | "permission" | "gone";
    error: string | null;
    last_lead_at: string | null;
    forms: MetaForm[];
}

interface MetaOverview {
    available: boolean;
    connections: { id: string; name: string; status: string; error: string | null; missing: string[]; mine: boolean }[];
    pages: MetaPage[];
}

const STATE: Record<MetaPage["status"], { tone: "good" | "warn" | "bad"; text: string }> = {
    active: { tone: "good", text: "Connected" }, token: { tone: "bad", text: "Connect again" }, permission: { tone: "warn", text: "Needs a permission" },
    gone: { tone: "bad", text: "Not shared any more" },
};

/** Facebook and Instagram lead ads, connected directly: Facebook sends Nimmi each new lead (backend meta_leads). Facebook returns here to finish signing in. */
export function MetaLeads({ assistants }: { assistants: { bot_id: string; bot_name: string }[] }) {
    const toast = useToast();
    const router = useRouter();
    const pathname = usePathname();
    const params = useSearchParams();
    const meta = useApi<MetaOverview>("/api/meta");
    const [busy, setBusy] = useState(false);
    const finishing = useRef(false);
    const { reload } = meta;

    useEffect(() => {  // back from Facebook with ?code=&state=: finish, then take them out of the address
        const code = params.get("code"), state = params.get("state");
        if (!code || !state || finishing.current) return;
        finishing.current = true;
        setBusy(true);
        apiJson<{ pages: number; taken: string[]; missing: string[] }>("/api/meta/connect/finish", { method: "POST", json: { code, state } })
            .then((r) => {
                toast(r.taken.length ? `Connected. ${r.taken.join(", ")} is already connected to another Nimmi account.` : `Connected: ${r.pages} ${r.pages === 1 ? "Page" : "Pages"}.`);
                return reload();
            })
            .catch((e) => toast((e as Error).message))
            .finally(() => { setBusy(false); router.replace(pathname); });
    }, [params, pathname, router, toast, reload]);

    const run = async (work: () => Promise<unknown>, done?: string) => {
        setBusy(true);
        try {
            await work();
            await reload();
            if (done) toast(done);
        } catch (e) {
            toast((e as Error).message);
        } finally {
            setBusy(false);
        }
    };
    const connect = () => run(async () => {
        const r = await apiJson<{ url: string }>("/api/meta/connect", { method: "POST" });
        window.location.assign(r.url);
    });

    if (meta.error) return <p className="text-sm text-signal">{meta.error}</p>;
    if (!meta.data) return <Skeleton className="h-32" />;
    const d = meta.data;
    return (
        <Card className="p-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                    <h3 className="text-sm font-medium">Facebook and Instagram lead ads, connected directly</h3>
                    <p className="text-[13px] text-stone-500 mt-0.5">Facebook sends each new lead to Nimmi the moment someone sends your form. Nothing in between to pay for, and leads Facebook didn&apos;t send are found every 15 minutes.</p>
                </div>
                {d.available && <Button variant={d.pages.length ? "secondary" : "primary"} disabled={busy} onClick={connect}>{d.connections.length ? "Connect again" : "Connect Facebook"}</Button>}
            </div>
            {!d.available && (
                <p className="text-[13px] text-stone-600 mt-3">This comes once Nimmi&apos;s Facebook app is approved by Meta. Until then, the Zapier, Make or Pabbly link below brings the same leads.</p>
            )}
            {d.connections.filter((c) => c.status !== "active").map((c) => (
                <Notice key={c.id} title={`${c.name}: some permissions weren't given`}>{c.error} Connect again and keep every box ticked.</Notice>
            ))}
            {d.pages.map((p) => (
                <div key={p.page_id} className="mt-4 rounded-lg border border-line">
                    <div className="flex flex-wrap items-center gap-3 px-4 py-3">
                        <span className="min-w-0 flex-1">
                            <span className="block text-sm truncate">{p.name}</span>
                            <span className="block text-[13px] text-stone-500">{p.last_lead_at ? `Last lead ${inline(formatWhen(p.last_lead_at))}` : "No leads yet"}</span>
                        </span>
                        <Status tone={STATE[p.status]?.tone ?? "warn"}>{p.subscribed || p.status !== "active" ? STATE[p.status]?.text ?? p.status : "Not getting leads"}</Status>
                        {!p.subscribed && p.status === "active" && (
                            <Button size="sm" variant="primary" disabled={busy} onClick={() => run(() => apiJson(`/api/meta/pages/${p.page_id}/subscribe`, { method: "POST" }), "Leads from this Page come to Nimmi now.")}>Get its leads</Button>
                        )}
                        {p.subscribed && <Button size="sm" variant="ghost" disabled={busy} onClick={() => run(() => apiJson(`/api/meta/pages/${p.page_id}`, { method: "DELETE" }), "Nimmi stopped getting this Page's leads.")}>Stop</Button>}
                    </div>
                    {p.error && p.status !== "active" && <p className="px-4 pb-3 text-[13px] text-stone-600">{p.error}</p>}
                    {p.subscribed && (
                        <ul className="border-t border-line">
                            {p.forms.length === 0 && <li className="px-4 py-3 text-[13px] text-stone-500">No lead forms on this Page yet.</li>}
                            {p.forms.map((f) => {
                                const waits = (f.waiting.waiting ?? 0) + (f.waiting.new ?? 0);
                                return (
                                    <li key={f.form_id} className="flex flex-wrap items-center gap-3 px-4 py-3 border-t border-line first:border-t-0">
                                        <span className="min-w-44 flex-1">
                                            <span className="block text-sm truncate">{f.name}</span>
                                            <span className="block text-[13px] text-stone-500">
                                                {[f.status === "ARCHIVED" ? "Archived" : null, f.last_lead_at ? `Last lead ${inline(formatWhen(f.last_lead_at))}` : null, waits ? `${waits} waiting` : null, f.waiting.failed ? `${f.waiting.failed} couldn't be read` : null].filter(Boolean).join(" · ") || "No leads yet"}
                                            </span>
                                        </span>
                                        <Select aria-label={`Assistant for ${f.name}`} className="w-44" value={f.bot_id ?? ""} disabled={busy}
                                                onChange={(e) => run(() => apiJson(`/api/meta/forms/${f.form_id}`, { method: "PUT", json: { bot_id: e.target.value } }), "Saved")}>
                                            <option value="">Choose an assistant</option>
                                            {assistants.map((a) => <option key={a.bot_id} value={a.bot_id}>{a.bot_name}</option>)}
                                        </Select>
                                        <label className="flex items-center gap-2 text-[13px] text-stone-600">
                                            <Switch label={`Email each lead from ${f.name}`} checked={f.settings.email} disabled={busy || !f.bot_id}
                                                    onChange={(v) => run(() => apiJson(`/api/meta/forms/${f.form_id}`, { method: "PUT", json: { email: v } }), "Saved")} />
                                            Email
                                        </label>
                                        <label className="flex items-center gap-2 text-[13px] text-stone-600">
                                            <Switch label={`The assistant calls each lead from ${f.name}`} checked={f.settings.call} disabled={busy || !f.bot_id}
                                                    onChange={(v) => run(() => apiJson(`/api/meta/forms/${f.form_id}`, { method: "PUT", json: { call: v } }), "Saved")} />
                                            Call
                                        </label>
                                        {f.ticks && (f.ticks.length > 0 || f.settings.whatsapp_tick) && (
                                            <Select aria-label={`Tick box that says yes to WhatsApp on ${f.name}`} className="w-48" value={f.settings.whatsapp_tick ?? ""} disabled={busy || !f.bot_id}
                                                    onChange={(e) => run(() => apiJson(`/api/meta/forms/${f.form_id}`, { method: "PUT", json: { whatsapp_tick: e.target.value } }), "Saved")}>
                                                <option value="">No WhatsApp tick box</option>
                                                {[...new Set([...(f.ticks ?? []), ...(f.settings.whatsapp_tick ? [f.settings.whatsapp_tick] : [])])].map((t) => <option key={t} value={t}>WhatsApp yes: {t}</option>)}
                                            </Select>
                                        )}
                                        {f.bot_id && (
                                            <Button size="sm" variant="ghost" disabled={busy}
                                                    onClick={() => run(() => apiJson(`/api/meta/forms/${f.form_id}/import`, { method: "POST", json: { days: 90 } }), "Older leads are coming in. Nobody is contacted.")}>
                                                Bring in older leads
                                            </Button>
                                        )}
                                    </li>
                                );
                            })}
                        </ul>
                    )}
                </div>
            ))}
            {d.pages.length > 0 && (
                <p className="text-[13px] text-stone-500 mt-3">Each lead reaches your team and Leads. The email and the assistant&apos;s call are off for each form until you turn them on. If a form has a tick box asking to be contacted on WhatsApp, choose it: only people who tick it get WhatsApp messages. The boxes show after the form&apos;s first lead.</p>
            )}
        </Card>
    );
}
