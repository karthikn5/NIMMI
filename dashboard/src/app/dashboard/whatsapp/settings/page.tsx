"use client";

import { useEffect, useState } from "react";
import { Check, Copy } from "lucide-react";
import { Button, Card, Dialog, EmptyState, Input, Notice, Select, SettingRow, Skeleton, Status, Switch, useToast } from "@/components/ui";
import { apiJson } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { formatWhen } from "@/lib/voice/api";
import type { WaNumber } from "@/lib/whatsapp";

const LANGS = [["en", "English"], ["hi", "Hindi"], ["ta", "Tamil"], ["te", "Telugu"], ["kn", "Kannada"], ["ml", "Malayalam"], ["mr", "Marathi"], ["bn", "Bengali"]];

export default function WhatsAppSettingsPage() {
    const numbers = useApi<WaNumber[]>("/api/whatsapp/numbers");
    const [connecting, setConnecting] = useState(false);
    // ?connect=1 (Nimmi's guide links here): open the form straight away.
    useEffect(() => { if (new URLSearchParams(window.location.search).get("connect")) setConnecting(true); }, []);

    return (
        <div className="max-w-3xl space-y-8">
            <section>
                <div className="flex items-end justify-between gap-3 mb-3">
                    <div>
                        <h2 className="text-[15px] font-semibold">Your WhatsApp numbers</h2>
                        <p className="text-[13px] text-stone-500 mt-0.5">The numbers your assistant answers on.</p>
                    </div>
                    {!!numbers.data?.length && <Button data-agent="whatsapp.connect" onClick={() => setConnecting(true)}>Connect another number</Button>}
                </div>
                {numbers.loading ? <Skeleton className="h-40" /> : numbers.error ? (
                    <p className="text-sm text-signal">Couldn&apos;t load your numbers. {numbers.error}</p>
                ) : !numbers.data?.length ? (
                    <Card>
                        <EmptyState title="No number connected" body="Connect your WhatsApp Business number and your assistant starts answering customers there."
                                    action={<Button variant="primary" data-agent="whatsapp.connect" onClick={() => setConnecting(true)}>Connect a number</Button>} />
                    </Card>
                ) : (
                    <div className="space-y-4">
                        {numbers.data.map((n) => (
                            <NumberCard key={n.id} n={n} onChanged={(x) => numbers.setData(numbers.data!.map((y) => (y.id === x.id ? x : y)))}
                                        onRemoved={() => numbers.setData(numbers.data!.filter((y) => y.id !== n.id))} />
                        ))}
                    </div>
                )}
            </section>

            <Confirmations />

            {connecting && <ConnectDialog onClose={() => setConnecting(false)} onConnected={(n) => { setConnecting(false); numbers.setData([...(numbers.data ?? []), n]); }} />}
        </div>
    );
}

function CopyField({ id, label, value }: { id: string; label: string; value: string }) {
    const toast = useToast();
    const [copied, setCopied] = useState(false);
    return (
        <div className="flex gap-2">
            <Input id={id} readOnly value={value} className="font-mono text-xs" aria-label={label} />
            <Button aria-label={`Copy ${label}`} onClick={() => navigator.clipboard.writeText(value).then(() => {
                setCopied(true);
                toast(`${label} copied`);
                setTimeout(() => setCopied(false), 1500);
            })}>
                {copied ? <Check size={14} /> : <Copy size={14} />}
            </Button>
        </div>
    );
}

function NumberCard({ n, onChanged, onRemoved }: { n: WaNumber; onChanged: (n: WaNumber) => void; onRemoved: () => void }) {
    const toast = useToast();
    const [dialog, setDialog] = useState<"test" | "keys" | "remove" | null>(null);
    const [busy, setBusy] = useState(false);
    const [to, setTo] = useState("+91");
    const [keys, setKeys] = useState({ access_token: "", app_secret: "" });

    const run = async (fn: () => Promise<unknown>, done?: string) => {
        setBusy(true);
        try {
            await fn();
            if (done) toast(done);
            setDialog(null);
        } catch (e) {
            toast((e as Error).message);
        } finally {
            setBusy(false);
        }
    };
    const refresh = () => run(async () => onChanged(await apiJson<WaNumber>(`/api/whatsapp/numbers/${n.id}/refresh`, { method: "POST" })), "Checked with Meta");
    const test = () => run(() => apiJson(`/api/whatsapp/numbers/${n.id}/test`, { method: "POST", json: { to } }), "Test message sent");
    const saveKeys = () => run(async () => {
        const body = Object.fromEntries(Object.entries(keys).filter(([, v]) => v.trim()));
        onChanged(await apiJson<WaNumber>(`/api/whatsapp/numbers/${n.id}`, { method: "PATCH", json: body }));
        setKeys({ access_token: "", app_secret: "" });
    }, "Saved");
    const remove = () => run(async () => { await apiJson(`/api/whatsapp/numbers/${n.id}`, { method: "DELETE" }); onRemoved(); }, "Disconnected");

    return (
        <Card>
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 px-5 pt-4">
                <span className="text-sm font-medium tabular-nums">{n.display_number ?? "Number"}</span>
                {n.verified_name && <span className="text-[13px] text-stone-500">{n.verified_name}</span>}
                <span className="ml-auto"><Status tone={n.status === "connected" ? "good" : "bad"}>{n.status === "connected" ? "Connected" : "Needs attention"}</Status></span>
            </div>
            {n.status_detail && <p className="px-5 mt-2 text-[13px] text-signal">{n.status_detail}</p>}
            {n.connection === "manual" && !n.has_app_secret && (
                <Notice className="mx-5 mt-3 mb-0" title="Add your app secret">
                    Without it, Nimmi can&apos;t check that messages really come from Meta, so it can&apos;t accept them. Find it in your Meta app under App settings &gt; Basic.
                </Notice>
            )}
            <div className="px-5 py-1 mt-1">
                <SettingRow label="Callback URL" htmlFor={`hook-${n.id}`} hint="In your Meta app: WhatsApp > Configuration > Webhook > Edit.">
                    <CopyField id={`hook-${n.id}`} label="Callback URL" value={n.webhook_url ?? ""} />
                </SettingRow>
                <SettingRow label="Verify token" htmlFor={`verify-${n.id}`} hint="Paste it under the callback URL, then Verify and save. Under Webhook fields, subscribe to messages.">
                    <CopyField id={`verify-${n.id}`} label="Verify token" value={n.verify_token ?? ""} />
                </SettingRow>
                <dl className="grid sm:grid-cols-2 gap-x-6 gap-y-1.5 py-4 text-[13px]">
                    <div className="flex justify-between gap-3"><dt className="text-stone-500">Phone number ID</dt><dd className="font-mono text-xs pt-0.5">{n.phone_number_id}</dd></div>
                    <div className="flex justify-between gap-3"><dt className="text-stone-500">WhatsApp account ID</dt><dd className="font-mono text-xs pt-0.5">{n.waba_id || "Not given"}</dd></div>
                    <div className="flex justify-between gap-3"><dt className="text-stone-500">App secret</dt><dd>{n.has_app_secret ? "Saved" : "Missing"}</dd></div>
                    <div className="flex justify-between gap-3"><dt className="text-stone-500">Last message received</dt><dd>{n.last_inbound_at ? formatWhen(n.last_inbound_at) : "None yet"}</dd></div>
                </dl>
            </div>
            <div className="flex flex-wrap gap-2 px-5 py-3 border-t border-line">
                <Button size="sm" onClick={() => setDialog("test")}>Send a test message</Button>
                <Button size="sm" onClick={refresh} disabled={busy}>Check with Meta</Button>
                <Button size="sm" onClick={() => setDialog("keys")}>Replace token or secret</Button>
                <Button size="sm" variant="ghost" className="sm:ml-auto" onClick={() => setDialog("remove")}>Disconnect</Button>
            </div>

            <Dialog open={dialog === "test"} onClose={() => setDialog(null)} title="Send a test message"
                    description="WhatsApp delivers it only to someone who messaged this number in the last 24 hours, or to a test recipient added in your Meta app."
                    footer={<><Button variant="ghost" onClick={() => setDialog(null)}>Cancel</Button><Button variant="primary" onClick={test} disabled={busy}>{busy ? "Sending…" : "Send"}</Button></>}>
                <label htmlFor={`to-${n.id}`} className="text-[13px] text-stone-600">Send to</label>
                <Input id={`to-${n.id}`} className="mt-1" type="tel" value={to} onChange={(e) => setTo(e.target.value)} placeholder="+91 98765 43210" />
            </Dialog>
            <Dialog open={dialog === "keys"} onClose={() => setDialog(null)} title="Replace token or secret" description="Leave a field empty to keep what's saved."
                    footer={<><Button variant="ghost" onClick={() => setDialog(null)}>Cancel</Button><Button variant="primary" onClick={saveKeys} disabled={busy || !(keys.access_token || keys.app_secret)}>Save</Button></>}>
                <div className="space-y-3">
                    <div>
                        <label htmlFor={`tok-${n.id}`} className="text-[13px] text-stone-600">Access token</label>
                        <Input id={`tok-${n.id}`} className="mt-1" type="password" autoComplete="off" placeholder="EAA…" value={keys.access_token} onChange={(e) => setKeys({ ...keys, access_token: e.target.value })} />
                    </div>
                    <div>
                        <label htmlFor={`sec-${n.id}`} className="text-[13px] text-stone-600">App secret</label>
                        <Input id={`sec-${n.id}`} className="mt-1" type="password" autoComplete="off" value={keys.app_secret} onChange={(e) => setKeys({ ...keys, app_secret: e.target.value })} />
                    </div>
                </div>
            </Dialog>
            <Dialog open={dialog === "remove"} onClose={() => setDialog(null)} title="Disconnect this number?"
                    description="The assistant stops answering on it and its keys are forgotten. Its chats stay in the Inbox."
                    footer={<><Button variant="ghost" onClick={() => setDialog(null)}>Cancel</Button><Button variant="primary" onClick={remove} disabled={busy}>Disconnect</Button></>}>
                <p className="text-[13px] text-stone-600">{n.display_number}</p>
            </Dialog>
        </Card>
    );
}

function ConnectDialog({ onClose, onConnected }: { onClose: () => void; onConnected: (n: WaNumber) => void }) {
    const toast = useToast();
    const bots = useApi<{ id: string; name: string }[]>("/api/bots");
    const [form, setForm] = useState({ phone_number_id: "", waba_id: "", access_token: "", app_secret: "", bot_id: "" });
    const [busy, setBusy] = useState(false);
    const ready = form.phone_number_id.trim() && form.access_token.trim() && form.app_secret.trim();

    const connect = async () => {
        setBusy(true);
        try {
            const n = await apiJson<WaNumber>("/api/whatsapp/numbers", { method: "POST", json: form });
            toast("Connected. Now add the callback URL and verify token in your Meta app.");
            onConnected(n);
        } catch (e) {
            toast((e as Error).message);
        } finally {
            setBusy(false);
        }
    };
    const field = (key: keyof typeof form, label: string, hint: string, secret = false) => (
        <div>
            <label htmlFor={`c-${key}`} className="text-[13px] text-stone-600">{label}</label>
            <Input id={`c-${key}`} className="mt-1" autoComplete="off" type={secret ? "password" : "text"} inputMode={secret ? undefined : "numeric"}
                   value={form[key]} onChange={(e) => setForm({ ...form, [key]: e.target.value })} />
            <p className="text-xs text-stone-500 mt-1">{hint}</p>
        </div>
    );

    return (
        <Dialog open onClose={onClose} title="Connect a WhatsApp number"
                description="One-click connect through Facebook is coming once Meta approves Nimmi. For now, connect a number from your own Meta app."
                footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button variant="primary" onClick={connect} disabled={busy || !ready}>{busy ? "Checking with Meta…" : "Connect"}</Button></>}>
            <div className="space-y-4">
                {field("phone_number_id", "Phone number ID", "developers.facebook.com > My Apps > your app > WhatsApp > API Setup, under your number.")}
                {field("waba_id", "WhatsApp Business Account ID", "On the same page, above the phone number. Lets Nimmi subscribe your app to its messages.")}
                {field("access_token", "Permanent access token",
                    "business.facebook.com > Settings > Users > System users > Add, give it your app and WhatsApp account, then Generate new token with whatsapp_business_messaging and whatsapp_business_management, set to never expire.", true)}
                {field("app_secret", "App secret", "developers.facebook.com > your app > App settings > Basic > App secret > Show.", true)}
                <div>
                    <label htmlFor="c-bot" className="text-[13px] text-stone-600">Assistant that answers</label>
                    <Select id="c-bot" className="mt-1" value={form.bot_id} onChange={(e) => setForm({ ...form, bot_id: e.target.value })}>
                        <option value="">Your first active assistant</option>
                        {(bots.data ?? []).map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
                    </Select>
                </div>
            </div>
        </Dialog>
    );
}

type Confirm = { enabled: boolean; template: string; language: string };

/** A WhatsApp template sent to callers after a phone call that captured a lead (moved here from Integrations). */
function Confirmations() {
    const toast = useToast();
    const saved = useApi<Confirm>("/api/whatsapp/confirmations");
    const [draft, setDraft] = useState<Confirm | null>(null);
    const c = draft ?? saved.data;
    if (!c) return null;
    const dirty = !!draft && JSON.stringify(draft) !== JSON.stringify(saved.data);
    const save = async () => {
        try {
            saved.setData(await apiJson<Confirm>("/api/whatsapp/confirmations", { method: "PUT", json: c }));
            setDraft(null);
            toast("Saved");
        } catch (e) {
            toast((e as Error).message);
        }
    };
    return (
        <section>
            <h2 className="text-[15px] font-semibold">After phone calls</h2>
            <p className="text-[13px] text-stone-500 mt-0.5 mb-3">Send callers a confirmation on WhatsApp when a call captures their details.</p>
            <Card className="px-5 py-1">
                <SettingRow label="Confirm after calls" hint="The caller gets your approved template. Never sent to numbers on the do-not-call list.">
                    <Switch checked={c.enabled} onChange={(v) => setDraft({ ...c, enabled: v })} label="Send WhatsApp confirmations after calls" />
                </SettingRow>
                <SettingRow label="Template" htmlFor="tpl" hint="Approved in WhatsApp Manager. Its three body variables become the caller's name, your assistant's name and the call summary.">
                    <div className="grid sm:grid-cols-[minmax(0,1fr)_140px] gap-2">
                        <Input id="tpl" placeholder="e.g. visit_confirmation" value={c.template} onChange={(e) => setDraft({ ...c, template: e.target.value })} />
                        <Select aria-label="Template language" value={c.language} onChange={(e) => setDraft({ ...c, language: e.target.value })}>
                            {LANGS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                        </Select>
                    </div>
                </SettingRow>
                {dirty && (
                    <div className="flex justify-end gap-2 pb-4">
                        <Button variant="ghost" onClick={() => setDraft(null)}>Discard</Button>
                        <Button variant="primary" onClick={save}>Save</Button>
                    </div>
                )}
            </Card>
        </section>
    );
}
