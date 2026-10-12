"use client";

import { useMemo, useState } from "react";
import { Copy } from "lucide-react";
import { Button, Card, EmptyState, Input, Segmented, SettingRow, Skeleton, Status, Switch, useToast } from "@/components/ui";
import { LOG_KIND, type LogRow } from "@/lib/integrations";
import { formatWhen } from "@/lib/voice/api";
import { PanelHeader, type PanelProps } from "./shared";

export function WebhookPanel({ draft, saved, set, test, testing }: PanelProps) {
    const toast = useToast();
    return (
        <>
            <PanelHeader title="Webhook" description="Send every lead and call to your own system, or to Zapier, Make or Zoho Flow." />
            <Card className="px-5 py-1">
                <SettingRow label="Endpoint URL" htmlFor="hook" hint="We POST JSON with an event name: lead.captured or call.completed. Leave empty to turn off.">
                    <div className="flex gap-2">
                        <Input id="hook" type="url" placeholder="https://hooks.example.com/nimmi" value={draft.webhook_url} onChange={(e) => set("webhook_url", e.target.value)} />
                        <Button onClick={() => test("webhook")} disabled={!saved?.webhook_url || testing === "webhook"}>{testing === "webhook" ? "Sending…" : "Send test"}</Button>
                    </div>
                </SettingRow>
                {saved?.webhook_secret && (
                    <SettingRow label="Signing secret" hint="Each request has an X-Nimmi-Signature header: the HMAC-SHA256 of the body with this secret.">
                        <div className="flex gap-2">
                            <Input readOnly value={saved.webhook_secret} className="font-mono text-xs" aria-label="Signing secret" />
                            <Button aria-label="Copy secret" onClick={() => navigator.clipboard.writeText(saved.webhook_secret).then(() => toast("Copied"))}><Copy size={14} /></Button>
                        </div>
                    </SettingRow>
                )}
                <SettingRow label="What's sent" hint="Calls also include the goal result, the caller's mood and the campaign.">
                    <pre className="text-[11px] leading-relaxed bg-stone-50 border border-line rounded-md p-3 overflow-x-auto">{`{
  "event": "lead.captured",
  "name": "Priya", "phone": "+919876543210", "email": "priya@example.com",
  "bot": "Front desk", "fields": { "Budget": "45" }, "source": "chat"
}`}</pre>
                </SettingRow>
            </Card>
        </>
    );
}

export function LeadSquaredPanel({ draft, set, test, testing }: PanelProps) {
    return (
        <>
            <PanelHeader title="LeadSquared" description="Create or update leads in LeadSquared automatically, matched on phone and email." />
            <Card className="px-5 py-1">
                <SettingRow label="Push leads">
                    <Switch checked={draft.leadsquared_enabled} onChange={(v) => set("leadsquared_enabled", v)} label="Push leads to LeadSquared" />
                </SettingRow>
                <SettingRow label="API host" htmlFor="lsq-host" hint="Settings, API and Webhooks in LeadSquared, e.g. api-in21.leadsquared.com">
                    <Input id="lsq-host" value={draft.leadsquared_host} onChange={(e) => set("leadsquared_host", e.target.value)} />
                </SettingRow>
                <SettingRow label="Access key" htmlFor="lsq-key">
                    <Input id="lsq-key" value={draft.leadsquared_access_key} onChange={(e) => set("leadsquared_access_key", e.target.value)} />
                </SettingRow>
                <SettingRow label="Secret key" htmlFor="lsq-secret" hint={draft.leadsquared_has_secret ? "Saved. Enter a new one to replace it." : undefined}>
                    <div className="flex gap-2">
                        <Input id="lsq-secret" type="password" autoComplete="off" placeholder={draft.leadsquared_has_secret ? "Saved" : ""}
                               value={draft.leadsquared_secret_key ?? ""} onChange={(e) => set("leadsquared_secret_key", e.target.value)} />
                        <Button onClick={() => test("leadsquared")} disabled={testing === "leadsquared"}>{testing === "leadsquared" ? "Sending…" : "Send test"}</Button>
                    </div>
                </SettingRow>
            </Card>
        </>
    );
}

type Filter = "all" | "email" | "whatsapp" | "webhook" | "crm";

export function ActivityPanel({ log, onRefresh }: { log: LogRow[] | null; onRefresh: () => void }) {
    const [filter, setFilter] = useState<Filter>("all");
    const rows = useMemo(() => (log ?? []).filter((r) => filter === "all" || LOG_KIND[r.kind]?.channel === filter), [log, filter]);

    return (
        <>
            <PanelHeader title="Activity" description="The last 50 alerts, emails, messages and webhooks: what went out, and why anything didn't."
                         action={<Button size="sm" variant="ghost" onClick={onRefresh}>Refresh</Button>} />
            <div className="mb-4 overflow-x-auto">
                <Segmented label="Filter activity" value={filter} onChange={setFilter} options={[
                    { value: "all", label: "All" }, { value: "email", label: "Email" }, { value: "whatsapp", label: "WhatsApp" },
                    { value: "webhook", label: "Webhook" }, { value: "crm", label: "CRM" },
                ]} />
            </div>
            <Card>
                {!log ? <div className="p-5"><Skeleton className="h-10" /></div> : rows.length === 0 ? (
                    <EmptyState title="Nothing here yet" body="Alerts, emails, confirmations and webhooks appear here as leads and calls come in." />
                ) : (
                    <ul>
                        {rows.map((r) => (
                            <li key={r.id} className="grid grid-cols-[minmax(0,1fr)_auto] sm:grid-cols-[minmax(0,1fr)_6.5rem_minmax(0,1.3fr)_7.5rem] gap-x-4 gap-y-1 px-5 py-3 border-t border-line first:border-t-0 text-[13px]">
                                <span>{LOG_KIND[r.kind]?.label ?? r.kind}</span>
                                <Status tone={r.status === "sent" ? "good" : r.status === "failed" ? "bad" : "neutral"}>
                                    {r.status === "sent" ? "Sent" : r.status === "failed" ? "Failed" : r.status === "skipped" ? "Skipped" : "Sending"}
                                </Status>
                                <span className="text-xs text-stone-500 truncate col-span-2 sm:col-span-1" title={r.error ?? ""}>{r.error ?? ""}</span>
                                <span className="hidden sm:block text-xs text-stone-400 text-right">{r.created_at ? formatWhen(r.created_at) : ""}</span>
                            </li>
                        ))}
                    </ul>
                )}
            </Card>
        </>
    );
}
