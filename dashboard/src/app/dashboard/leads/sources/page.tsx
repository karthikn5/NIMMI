"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { Copy } from "lucide-react";
import { Button, Card, EmptyState, Notice, Select, Skeleton, Status, Switch, useToast } from "@/components/ui";
import { MetaLeads } from "@/components/leads/MetaLeads";
import { Routing } from "@/components/leads/Routing";
import { apiJson } from "@/lib/api";
import type { AssistantEmails, LeadSources, Senders } from "@/lib/email";
import { useApi } from "@/lib/useApi";
import { formatWhen } from "@/lib/voice/api";

const STATUS: Record<string, { tone: "good" | "warn" | "neutral" | "bad"; text: string }> = {
    done: { tone: "good", text: "Handled" }, new: { tone: "neutral", text: "Waiting" }, working: { tone: "neutral", text: "Being read" },
    ignored: { tone: "neutral", text: "Not a lead" }, failed: { tone: "bad", text: "Couldn't handle it" },
};

function Copyable({ value, label }: { value: string; label: string }) {
    const toast = useToast();
    return (
        <div className="flex items-center gap-2 mt-2">
            <code className="flex-1 min-w-0 truncate rounded-md border border-line bg-paper px-3 py-2 text-[13px]" aria-label={label}>{value}</code>
            <Button size="sm" onClick={() => navigator.clipboard.writeText(value).then(() => toast("Copied"))}><Copy size={13} aria-hidden /> Copy</Button>
        </div>
    );
}

export default function LeadSourcesPage() {
    const toast = useToast();
    const senders = useApi<Senders>("/api/email/senders");
    const [botId, setBotId] = useState("");
    const page = useApi<LeadSources>(botId ? `/api/email/leads/${botId}` : null);
    const [saving, setSaving] = useState(false);
    const assistants = senders.data?.assistants ?? [];
    useEffect(() => { if (!botId && assistants[0]) setBotId(assistants[0].bot_id); }, [botId, assistants]);

    const run = async (work: () => Promise<unknown>) => {
        setSaving(true);
        try {
            await work();
            await page.reload();
            toast("Saved");
        } catch (e) {
            toast((e as Error).message);
        } finally {
            setSaving(false);
        }
    };
    const setting = (kind: string, values: Record<string, unknown>) => run(() => apiJson<AssistantEmails>(`/api/email/setup/${botId}`, { method: "PUT", json: { settings: { [kind]: values } } }));

    if (senders.error) return <p className="text-sm text-signal">{senders.error}</p>;
    if (!senders.data) return <Skeleton className="h-64" />;
    if (assistants.length === 0) return <Card className="p-5 text-[13px] text-stone-600">Make an assistant first: leads come in to it.</Card>;
    const d = page.data;
    return (
        <div className="space-y-5">
            <Card>
                <div className="flex flex-wrap items-center gap-3 px-5 py-4">
                    <div className="flex-1 min-w-48">
                        <h3 className="text-sm font-medium">Leads from other places</h3>
                        <p className="text-[13px] text-stone-500 mt-0.5">Leads from IndiaMART, JustDial, property portals and your website forms become contacts, your team is told, and they hear from you.</p>
                    </div>
                    {assistants.length > 1 && (
                        <Select aria-label="Assistant" className="w-56" value={botId} onChange={(e) => setBotId(e.target.value)}>
                            {assistants.map((a) => <option key={a.bot_id} value={a.bot_id}>{a.bot_name}</option>)}
                        </Select>
                    )}
                    {d && <Switch checked={d.enabled} disabled={saving} onChange={(v) => run(() => apiJson(`/api/email/leads/${botId}`, { method: "PUT", json: { enabled: v } }))} label="Take leads from other places" />}
                </div>
            </Card>
            {botId && <Routing key={botId} botId={botId} />}
            {page.error ? <p className="text-sm text-signal">{page.error}</p> : !d ? <Skeleton className="h-64" /> : (
                <>
                    {!d.receiving && (
                        <Notice title="Forwarded emails aren't switched on for your account yet">IndiaMART and website forms work now. Emails forwarded to Nimmi need email receiving, which your administrator turns on.</Notice>
                    )}
                    <Card className="p-5">
                        <h3 className="text-sm font-medium">Emails from portals</h3>
                        <p className="text-[13px] text-stone-500 mt-0.5">Forward JustDial, 99acres, MagicBricks, Sulekha or website form emails here. The AI reads any format.</p>
                        {d.address ? <Copyable value={d.address} label="Your forwarding address" /> : <p className="text-[13px] text-stone-600 mt-2">Your address shows here once receiving is on.</p>}
                        <ol className="list-decimal pl-5 mt-3 space-y-1 text-[13px] text-stone-600">
                            <li>In Gmail, open Settings &gt; See all settings &gt; Forwarding and POP/IMAP &gt; Add a forwarding address, and paste this address.</li>
                            <li>Gmail sends a confirmation code to Nimmi. It shows here, for you to enter in Gmail.</li>
                            <li>In Settings &gt; Filters and Blocked Addresses, create a filter for the portal&apos;s emails, and choose Forward it to this address.</li>
                        </ol>
                        {d.forwarding?.code && (
                            <p className="mt-3 text-[13px]"><span className="text-stone-500">Gmail&apos;s confirmation code: </span><span className="font-medium">{d.forwarding.code}</span></p>
                        )}
                    </Card>
                    <Card className="p-5">
                        <h3 className="text-sm font-medium">IndiaMART</h3>
                        <p className="text-[13px] text-stone-500 mt-0.5">For paid IndiaMART sellers: each lead arrives the moment IndiaMART gets it.</p>
                        {d.indiamart_url && <Copyable value={d.indiamart_url} label="Your IndiaMART link" />}
                        <ol className="list-decimal pl-5 mt-3 space-y-1 text-[13px] text-stone-600">
                            <li>On seller.indiamart.com, open Lead Manager, the three dots menu, Import/Export Leads, then Push API.</li>
                            <li>For the CRM, choose Other, type Nimmi, and paste this link as the Webhook Listener URL.</li>
                            <li>Confirm with the OTP sent to your mobile.</li>
                        </ol>
                    </Card>
                    <Card className="p-5">
                        <h3 className="text-sm font-medium">Website forms</h3>
                        <p className="text-[13px] text-stone-500 mt-0.5">Point any form here, or give this link to whoever built your website. It needs a name and a phone number or email; other fields are understood by their names.</p>
                        {d.form_url && <Copyable value={d.form_url} label="Your form link" />}
                    </Card>
                    <Suspense fallback={<Skeleton className="h-32" />}><MetaLeads assistants={assistants} /></Suspense>
                    <Card className="p-5">
                        <h3 className="text-sm font-medium">Google lead forms</h3>
                        <p className="text-[13px] text-stone-500 mt-0.5">Leads from your Google Ads lead forms arrive here the moment someone sends the form. Take leads from other places must be on.</p>
                        {d.google_url && <Copyable value={d.google_url} label="Your Google webhook address" />}
                        {d.google_key && <Copyable value={d.google_key} label="Your Google key" />}
                        <ol className="list-decimal pl-5 mt-3 space-y-1 text-[13px] text-stone-600">
                            <li>In Google Ads, open your lead form assets, and press the pencil on your form to edit it.</li>
                            <li>Open Export leads from Google Ads, then Other data integration options. Paste the address above as the Webhook URL, and the key as the Key.</li>
                            <li>Press Send test data. It shows below as a test lead: nobody is told and nobody is contacted. Keys are case-sensitive, so use Copy.</li>
                        </ol>
                    </Card>
                    <Card className="p-5">
                        <h3 className="text-sm font-medium">Facebook and Instagram lead ads, through Zapier, Make or Pabbly</h3>
                        <p className="text-[13px] text-stone-500 mt-0.5">Works today with your own Zapier, Make or Pabbly account, with Take leads from other places on. Those services charge for their part, and if they stop, leads stop reaching Nimmi.</p>
                        {d.connect_url && <Copyable value={d.connect_url} label="Your connection link" />}
                        <ol className="list-decimal pl-5 mt-3 space-y-1 text-[13px] text-stone-600">
                            <li>Make a new Zap. The trigger is Facebook Lead Ads, New Lead, on your Page and form.</li>
                            <li>The action is Webhooks by Zapier, POST (in Make, HTTP then Make a request; in Pabbly, API by Pabbly). Paste this link as the URL, with the payload type json.</li>
                            <li>Under Data, send the form&apos;s answers with these names: full_name, phone_number, email, and the lead&apos;s ID as lead_id, so a repeat counts once. Add campaign_name, ad_name and form_name to see which ad brought them.</li>
                        </ol>
                    </Card>
                    <Card>
                        <h3 className="text-sm font-medium px-5 pt-4 pb-1">For each lead</h3>
                        <ul>
                            <li className="flex items-center gap-3 px-5 py-3">
                                <div className="flex-1 min-w-48">
                                    <p className="text-sm">An email at once</p>
                                    <p className="text-[13px] text-stone-500 mt-0.5">When they gave an address. Change it in <Link href="/dashboard/email/automations" className="text-plum hover:underline">Automations</Link>.</p>
                                </div>
                                <Switch checked={d.lead_email.enabled} disabled={saving} onChange={(v) => setting("lead_email", { enabled: v })} label="An email at once" />
                            </li>
                            <li className="flex flex-wrap items-center gap-3 px-5 py-3 border-t border-line">
                                <div className="flex-1 min-w-48">
                                    <p className="text-sm">A call from your assistant</p>
                                    <p className="text-[13px] text-stone-500 mt-0.5">With Pro, inside your calling hours, when call-backs are on in Voice &gt; Schedule.</p>
                                </div>
                                <Select aria-label="How soon to call" className="w-36" value={d.lead_call.minutes} disabled={saving} onChange={(e) => setting("lead_call", { minutes: Number(e.target.value) })}>
                                    {[2, 5, 10, 30].map((m) => <option key={m} value={m}>In {m} minutes</option>)}
                                </Select>
                                <Switch checked={d.lead_call.enabled} disabled={saving} onChange={(v) => setting("lead_call", { enabled: v })} label="A call from your assistant" />
                            </li>
                        </ul>
                    </Card>
                    <Card>
                        <h3 className="text-sm font-medium px-5 pt-4 pb-3">Latest leads</h3>
                        {d.recent.length === 0 ? <EmptyState title="None yet" body="Leads show here as they arrive." /> : (
                            <ul>
                                {d.recent.map((r) => {
                                    const s = STATUS[r.status] ?? STATUS.new;
                                    return (
                                        <li key={r.id} className="flex items-center gap-4 px-5 py-3 border-t border-line">
                                            <span className="min-w-0 flex-1">
                                                <span className="block text-sm truncate">{r.found.name || r.found.phone || r.found.email || r.subject || "A lead"}</span>
                                                <span className="block text-[13px] text-stone-500 truncate">
                                                    {r.source ?? r.channel}{r.created_at ? ` · ${formatWhen(r.created_at)}` : ""}{r.found.wants ? ` · ${r.found.wants}` : ""}
                                                </span>
                                                {r.note && <span className="block text-xs text-stone-500 truncate mt-0.5">{r.note}</span>}
                                            </span>
                                            {r.test ? <Status tone="neutral">Test</Status> : <Status tone={s.tone}>{s.text}</Status>}
                                        </li>
                                    );
                                })}
                            </ul>
                        )}
                    </Card>
                </>
            )}
        </div>
    );
}
