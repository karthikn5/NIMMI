"use client";

import { useState } from "react";
import { Check, Copy } from "lucide-react";
import { Button, Card, Input, Notice, Segmented, Select, SettingRow, Status, Switch, useToast } from "@/components/ui";
import { useApi } from "@/lib/useApi";
import { PanelHeader, type PanelProps } from "./shared";

export function WhatsAppPanel({ draft, saved, set, test, testing }: PanelProps) {
    const [view, setView] = useState<"chat" | "confirmations">("chat");
    const connected = !!(saved?.whatsapp_chat_enabled && saved.whatsapp_has_token && saved.whatsapp_phone_number_id);

    return (
        <>
            <PanelHeader
                title="WhatsApp"
                description="Your assistant answers customers on your WhatsApp Business number, and can confirm call bookings there."
                action={<Status tone={connected ? "good" : "neutral"}>{connected ? `Connected · ID ${saved!.whatsapp_phone_number_id}` : "Not connected"}</Status>}
            />
            <div className="mb-5">
                <Segmented label="WhatsApp section" value={view} onChange={setView}
                           options={[{ value: "chat", label: "AI chat" }, { value: "confirmations", label: "Call confirmations" }]} />
            </div>
            {view === "chat" ? <ChatSetup draft={draft} saved={saved} set={set} test={test} testing={testing} /> : <Confirmations draft={draft} set={set} />}
        </>
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

function ChatSetup({ draft, saved, set, test, testing }: PanelProps) {
    const bots = useApi<{ id: string; name: string }[]>("/api/bots");
    const [phone, setPhone] = useState("+91");
    const canTest = !!(saved?.whatsapp_has_token && saved.whatsapp_phone_number_id);

    return (
        <div className="space-y-6">
            <Card className="px-5 py-1">
                <SettingRow label="Reply with AI" hint="Your assistant answers every WhatsApp message, day and night, from its knowledge. Customers can ask for a person at any time.">
                    <Switch checked={draft.whatsapp_chat_enabled} onChange={(v) => set("whatsapp_chat_enabled", v)} label="Reply to WhatsApp messages with AI" />
                </SettingRow>
                <SettingRow label="Assistant" htmlFor="wa-bot" hint="Answers in its own voice, from its own knowledge.">
                    <Select id="wa-bot" value={draft.whatsapp_bot_id} onChange={(e) => set("whatsapp_bot_id", e.target.value)}>
                        <option value="">Your first active assistant</option>
                        {(bots.data ?? []).map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
                    </Select>
                </SettingRow>
            </Card>

            <Card>
                <div className="px-5 pt-4">
                    <h3 className="text-sm font-medium">Connect your number</h3>
                    <p className="text-[13px] text-stone-500 mt-0.5">From Meta for Developers, in your app&apos;s WhatsApp section.</p>
                </div>
                <div className="px-5 py-1">
                    <SettingRow label="Phone number ID" htmlFor="wa-phone-id" hint="API Setup, under your number.">
                        <Input id="wa-phone-id" autoComplete="off" inputMode="numeric" placeholder="e.g. 100234567891234"
                               value={draft.whatsapp_phone_number_id} onChange={(e) => set("whatsapp_phone_number_id", e.target.value)} />
                    </SettingRow>
                    <SettingRow label="Access token" htmlFor="wa-token"
                                hint={draft.whatsapp_has_token ? "Saved. Paste a new one to replace it." : "A permanent System User token with WhatsApp messaging permission."}>
                        <Input id="wa-token" type="password" autoComplete="off" placeholder={draft.whatsapp_has_token ? "Saved" : "EAA…"}
                               value={draft.whatsapp_access_token ?? ""} onChange={(e) => set("whatsapp_access_token", e.target.value)} />
                    </SettingRow>
                    <SettingRow label="Callback URL" htmlFor="wa-hook" hint="Configuration, Webhook. Then subscribe to the messages field.">
                        <CopyField id="wa-hook" label="Callback URL" value={draft.whatsapp_webhook_url} />
                    </SettingRow>
                    <SettingRow label="Verify token" htmlFor="wa-verify" hint="Paste it next to the callback URL.">
                        {draft.whatsapp_verify_token
                            ? <CopyField id="wa-verify" label="Verify token" value={draft.whatsapp_verify_token} />
                            : <p className="text-[13px] text-stone-500 pt-2">Created when you turn on AI replies and save.</p>}
                    </SettingRow>
                </div>
            </Card>

            <Card className="px-5 py-1">
                <SettingRow label="Send a test" htmlFor="wa-test" hint="Uses your saved number and token.">
                    <div className="flex gap-2">
                        <Input id="wa-test" type="tel" placeholder="+91 98765 43210" value={phone} onChange={(e) => setPhone(e.target.value)} />
                        <Button onClick={() => test("whatsapp", undefined, phone)} disabled={!canTest || testing === "whatsapp"}>
                            {testing === "whatsapp" ? "Sending…" : "Send test"}
                        </Button>
                    </div>
                    <p className="text-xs text-stone-500 mt-1.5">
                        WhatsApp only delivers free-form messages to people who messaged your number in the last 24 hours.
                    </p>
                </SettingRow>
            </Card>
        </div>
    );
}

const LANGS = [["en", "English"], ["hi", "Hindi"], ["ta", "Tamil"], ["te", "Telugu"], ["kn", "Kannada"], ["ml", "Malayalam"], ["mr", "Marathi"], ["bn", "Bengali"]];

function Confirmations({ draft, set }: Pick<PanelProps, "draft" | "set">) {
    const ready = draft.server.whatsapp || (draft.whatsapp_has_token && draft.whatsapp_phone_number_id);
    return (
        <>
            {!ready && <Notice title="Connect a WhatsApp number first">Confirmations use the number in AI chat, or the server&apos;s default number.</Notice>}
            <Card className="px-5 py-1">
                <SettingRow label="Confirm after calls" hint="When a call captures a lead, the caller gets your approved template. Never sent to numbers on the do-not-call list.">
                    <Switch checked={draft.whatsapp_enabled} onChange={(v) => set("whatsapp_enabled", v)} label="Send WhatsApp confirmations after calls" />
                </SettingRow>
                <SettingRow label="Template" htmlFor="tpl"
                            hint="Approved in WhatsApp Manager. Its three body variables become the caller's name, your assistant's name and the call summary.">
                    <div className="grid sm:grid-cols-[minmax(0,1fr)_140px] gap-2">
                        <Input id="tpl" placeholder="e.g. visit_confirmation" value={draft.whatsapp_template} onChange={(e) => set("whatsapp_template", e.target.value)} />
                        <Select aria-label="Template language" value={draft.whatsapp_language} onChange={(e) => set("whatsapp_language", e.target.value)}>
                            {LANGS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                        </Select>
                    </div>
                </SettingRow>
            </Card>
        </>
    );
}
