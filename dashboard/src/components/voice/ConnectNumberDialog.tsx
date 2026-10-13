"use client";

import { useEffect, useState } from "react";
import { Check, Copy } from "lucide-react";
import { Button, Dialog, Input, Select, Skeleton, cn, useToast } from "@/components/ui";
import { apiJson } from "@/lib/api";
import { apiSave } from "@/lib/useApi";
import type { AccountNumber, PhoneAccount, PhoneNumber, VoiceAgentSummary } from "@/lib/voice/types";

type Provider = "twilio" | "exotel";
const REGIONS = [{ value: "api.exotel.com", label: "Singapore (most accounts)" }, { value: "api.in.exotel.com", label: "Mumbai" }];

/**
 * Bring your own number: connect a Twilio or Exotel account, then choose which of its numbers
 * the assistant answers and calls from. `account` opens straight at an existing account's numbers.
 */
export function ConnectNumberDialog({ open, onClose, agents, account, onDone }: {
    open: boolean; onClose: () => void; agents: VoiceAgentSummary[];
    account?: PhoneAccount | null;
    onDone: (added: PhoneNumber[], account: PhoneAccount) => void;
}) {
    const [provider, setProvider] = useState<Provider | null>(null);
    const [connected, setConnected] = useState<PhoneAccount | null>(null);

    useEffect(() => {
        if (!open) return;
        setConnected(account ?? null);
        setProvider(account?.provider ?? null);
    }, [open, account]);

    const close = () => { setProvider(null); setConnected(null); onClose(); };
    const title = connected ? (connected.provider === "twilio" ? "Choose your numbers" : "Finish Exotel setup")
        : provider ? `Connect ${provider === "twilio" ? "Twilio" : "Exotel"}` : "Use a number you already have";

    return (
        <Dialog open={open} onClose={close} title={title} footer={null}
                description={!provider ? "Calls run on your own phone account. You keep paying your provider for the number and call charges." : undefined}>
            {!provider ? (
                <ProviderChoice onPick={setProvider} onCancel={close} />
            ) : !connected ? (
                <Keys provider={provider} onBack={() => setProvider(null)} onConnected={setConnected} />
            ) : connected.provider === "twilio" ? (
                <TwilioNumbers account={connected} agents={agents} onCancel={close} onAdded={(added) => { onDone(added, connected); close(); }} />
            ) : (
                <ExotelSetup account={connected} agents={agents} onCancel={close} onAdded={(added, acc) => { onDone(added, acc); close(); }} />
            )}
        </Dialog>
    );
}

function Footer({ children }: { children: React.ReactNode }) {
    return <div className="flex justify-end gap-2 -mx-5 -mb-4 mt-5 px-5 py-3 border-t border-line bg-stone-50/60 rounded-b-lg">{children}</div>;
}

function ProviderChoice({ onPick, onCancel }: { onPick: (p: Provider) => void; onCancel: () => void }) {
    const options: { id: Provider; name: string; text: string }[] = [
        { id: "exotel", name: "Exotel", text: "Indian numbers (ExoPhones). You add Nimmi to a flow in Exotel once; we give you the exact links." },
        { id: "twilio", name: "Twilio", text: "Numbers in the US, UK, Canada, Australia and more. Nimmi sets up incoming calls for you." },
    ];
    return (
        <>
            <div className="space-y-2">
                {options.map((o) => (
                    <button key={o.id} type="button" onClick={() => onPick(o.id)}
                            className="w-full text-left rounded-md border border-line-strong px-4 py-3 hover:border-plum hover:bg-plum-tint/40 transition-colors">
                        <span className="block text-sm font-medium">{o.name}</span>
                        <span className="block text-[13px] text-stone-500 mt-0.5">{o.text}</span>
                    </button>
                ))}
            </div>
            <Footer><Button variant="ghost" onClick={onCancel}>Cancel</Button></Footer>
        </>
    );
}

function Keys({ provider, onBack, onConnected }: { provider: Provider; onBack: () => void; onConnected: (a: PhoneAccount) => void }) {
    const toast = useToast();
    const [f, setF] = useState({ account_sid: "", auth_token: "", api_key: "", api_token: "", subdomain: "api.exotel.com" });
    const [busy, setBusy] = useState(false);
    const set = (k: keyof typeof f, v: string) => setF({ ...f, [k]: v });
    const ready = provider === "twilio" ? f.account_sid.trim() && f.auth_token.trim() : f.account_sid.trim() && f.api_key.trim() && f.api_token.trim();

    const connect = async () => {
        setBusy(true);
        const res = await apiSave("/api/voice/phone-accounts", "POST", { provider, ...f });
        setBusy(false);
        if (!res.ok) return toast(res.message);
        onConnected(res.data as PhoneAccount);
    };

    return (
        <>
            <div className="space-y-3">
                {provider === "twilio" ? (
                    <>
                        <Field label="Account SID" id="sid" hint="Twilio console, under Account info. It starts with AC.">
                            <Input id="sid" autoComplete="off" spellCheck={false} value={f.account_sid} onChange={(e) => set("account_sid", e.target.value)} placeholder="AC…" />
                        </Field>
                        <Field label="Auth token" id="token">
                            <Input id="token" type="password" autoComplete="off" value={f.auth_token} onChange={(e) => set("auth_token", e.target.value)} />
                        </Field>
                    </>
                ) : (
                    <>
                        <Field label="Region" id="region" hint="Shown in Exotel under API settings, next to your API keys.">
                            <Select id="region" value={f.subdomain} onChange={(e) => set("subdomain", e.target.value)}>
                                {REGIONS.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
                            </Select>
                        </Field>
                        <Field label="Account SID" id="sid">
                            <Input id="sid" autoComplete="off" spellCheck={false} value={f.account_sid} onChange={(e) => set("account_sid", e.target.value)} />
                        </Field>
                        <div className="grid grid-cols-2 gap-2">
                            <Field label="API key" id="key"><Input id="key" autoComplete="off" value={f.api_key} onChange={(e) => set("api_key", e.target.value)} /></Field>
                            <Field label="API token" id="tok"><Input id="tok" type="password" autoComplete="off" value={f.api_token} onChange={(e) => set("api_token", e.target.value)} /></Field>
                        </div>
                    </>
                )}
                <p className="text-[12px] text-stone-500">We check these with {provider === "twilio" ? "Twilio" : "Exotel"} right away and store them encrypted. Only calls for your assistants use them.</p>
            </div>
            <Footer>
                <Button variant="ghost" onClick={onBack}>Back</Button>
                <Button variant="primary" onClick={connect} disabled={!ready || busy}>{busy ? "Checking…" : "Connect"}</Button>
            </Footer>
        </>
    );
}

function Field({ label, id, hint, children }: { label: string; id: string; hint?: string; children: React.ReactNode }) {
    return (
        <div>
            <label htmlFor={id} className="text-sm font-medium">{label}</label>
            <div className="mt-1.5">{children}</div>
            {hint && <p className="text-[12px] text-stone-500 mt-1">{hint}</p>}
        </div>
    );
}

function AgentPicker({ agents, value, onChange }: { agents: VoiceAgentSummary[]; value: string; onChange: (v: string) => void }) {
    return (
        <Field label="Answered by" id="agent">
            <Select id="agent" value={value} onChange={(e) => onChange(e.target.value)}>
                <option value="">Choose later</option>
                {agents.map((a) => <option key={a.bot_id} value={a.bot_id}>{a.bot_name}</option>)}
            </Select>
        </Field>
    );
}

function TwilioNumbers({ account, agents, onCancel, onAdded }: {
    account: PhoneAccount; agents: VoiceAgentSummary[]; onCancel: () => void; onAdded: (n: PhoneNumber[]) => void;
}) {
    const toast = useToast();
    const [list, setList] = useState<AccountNumber[] | null>(null);
    const [error, setError] = useState("");
    const [picked, setPicked] = useState<string[]>([]);
    const [botId, setBotId] = useState(agents[0]?.bot_id ?? "");
    const [busy, setBusy] = useState(false);

    useEffect(() => {
        apiJson<{ numbers: AccountNumber[] }>(`/api/voice/phone-accounts/${account.id}/numbers`)
            .then((d) => setList(d.numbers))
            .catch((e: Error) => setError(e.message));
    }, [account.id]);

    const toggle = (p: string) => setPicked(picked.includes(p) ? picked.filter((x) => x !== p) : [...picked, p]);
    const add = async () => {
        setBusy(true);
        const res = await apiSave(`/api/voice/phone-accounts/${account.id}/numbers`, "POST", { phone_numbers: picked, bot_id: botId || null });
        setBusy(false);
        if (!res.ok) return toast(res.message);
        const added = (res.data as { numbers: PhoneNumber[] }).numbers;
        toast(`${added.length === 1 ? added[0].number : `${added.length} numbers`} now answered by your assistant`);
        onAdded(added);
    };
    const takingOver = (list ?? []).some((n) => picked.includes(n.phone_number) && n.has_other_webhook);

    return (
        <>
            <p className="text-[13px] text-stone-600">Connected to <span className="font-medium text-ink">{account.label}</span>. Pick the numbers your assistant should answer and call from.</p>
            <div className="mt-3">
                {error ? <p className="text-[13px] text-signal">{error}</p>
                    : !list ? <div className="space-y-2"><Skeleton className="h-11" /><Skeleton className="h-11" /></div>
                    : !list.length ? <p className="text-[13px] text-stone-500">This Twilio account has no voice numbers yet. Buy one in Twilio, or get one from Nimmi instead.</p>
                    : (
                        <ul className="max-h-60 overflow-y-auto rounded-md border border-line divide-y divide-line">
                            {list.map((n) => {
                                const locked = n.connected || n.in_use;
                                const on = picked.includes(n.phone_number);
                                return (
                                    <li key={n.phone_number}>
                                        <label className={cn("flex items-center gap-3 px-3 py-2.5", locked ? "opacity-60" : "cursor-pointer hover:bg-stone-50", on && "bg-plum-tint")}>
                                            <input type="checkbox" className="accent-plum" checked={on || n.connected} disabled={locked} onChange={() => toggle(n.phone_number)} />
                                            <span className="text-sm tabular-nums">{n.display}</span>
                                            <span className="ml-auto text-xs text-stone-500 truncate">
                                                {n.connected ? "Already added" : n.in_use ? "Used in another workspace" : n.name}
                                            </span>
                                        </label>
                                    </li>
                                );
                            })}
                        </ul>
                    )}
            </div>
            {picked.length > 0 && (
                <div className="mt-4 space-y-3">
                    <AgentPicker agents={agents} value={botId} onChange={setBotId} />
                    {takingOver && (
                        <p className="text-[12px] text-amber-800 bg-amber-50 border border-amber-200 rounded-md px-3 py-2">
                            Calls to a selected number currently go somewhere else. Nimmi will answer them instead; if you remove the number later, we put its old setting back.
                        </p>
                    )}
                </div>
            )}
            <Footer>
                <Button variant="ghost" onClick={onCancel}>{picked.length ? "Cancel" : "Done"}</Button>
                <Button variant="primary" onClick={add} disabled={!picked.length || busy}>
                    {busy ? "Adding…" : picked.length > 1 ? `Add ${picked.length} numbers` : "Add number"}
                </Button>
            </Footer>
        </>
    );
}

function CopyField({ label, value }: { label: string; value: string }) {
    const [copied, setCopied] = useState(false);
    return (
        <div className="mt-1.5 flex items-center gap-2">
            <code className="flex-1 min-w-0 truncate rounded-md border border-line bg-stone-50 px-2.5 py-1.5 text-[12px] text-stone-700" title={value}>{value}</code>
            <button type="button" aria-label={`Copy ${label}`}
                    onClick={async () => { await navigator.clipboard.writeText(value); setCopied(true); setTimeout(() => setCopied(false), 1500); }}
                    className="p-1.5 rounded text-stone-500 hover:text-ink hover:bg-stone-100">
                {copied ? <Check size={14} className="text-emerald-600" /> : <Copy size={14} />}
            </button>
        </div>
    );
}

function ExotelSetup({ account, agents, onCancel, onAdded }: {
    account: PhoneAccount; agents: VoiceAgentSummary[]; onCancel: () => void; onAdded: (n: PhoneNumber[], a: PhoneAccount) => void;
}) {
    const toast = useToast();
    const [appId, setAppId] = useState(account.app_id ?? "");
    const [numbers, setNumbers] = useState("");
    const [botId, setBotId] = useState(agents[0]?.bot_id ?? "");
    const [busy, setBusy] = useState(false);
    const s = account.setup!;

    const finish = async () => {
        setBusy(true);
        let acc = account;
        if (appId.trim() !== (account.app_id ?? "")) {
            const res = await apiSave(`/api/voice/phone-accounts/${account.id}`, "PATCH", { app_id: appId.trim() });
            if (!res.ok) { setBusy(false); return toast(res.message); }
            acc = res.data as PhoneAccount;
        }
        const list = numbers.split(/[,\n]/).map((x) => x.trim()).filter(Boolean);
        let added: PhoneNumber[] = [];
        if (list.length) {
            const res = await apiSave(`/api/voice/phone-accounts/${account.id}/numbers`, "POST", { phone_numbers: list, bot_id: botId || null });
            if (!res.ok) { setBusy(false); return toast(res.message); }
            added = (res.data as { numbers: PhoneNumber[] }).numbers;
        }
        setBusy(false);
        toast(added.length ? `${added.length === 1 ? added[0].number : `${added.length} numbers`} added` : "Saved");
        onAdded(added, acc);
    };

    return (
        <>
            <ol className="space-y-3 text-[13px] text-stone-700 list-decimal pl-4">
                <li>In Exotel, open <span className="font-medium">App Bazaar</span> and create a new flow.</li>
                <li>Add a <span className="font-medium">Voicebot</span> applet with this address:<CopyField label="voicebot address" value={s.voicebot} /></li>
                <li>
                    After it, add a <span className="font-medium">Passthru</span> applet with this address. For the &ldquo;200 OK&rdquo; branch add a <span className="font-medium">Connect</span> applet that dials the number from the second address; otherwise <span className="font-medium">Hangup</span>. This lets the assistant transfer calls to your team.
                    <CopyField label="passthru address" value={s.after_bot} />
                    <CopyField label="transfer address" value={s.transfer_target} />
                </li>
                <li>Save the flow and attach your ExoPhone to it, so incoming calls reach the assistant.</li>
            </ol>
            <div className="mt-4 space-y-3">
                <Field label="Flow ID" id="app" hint="The number at the end of the flow's address in Exotel. Needed for call-backs and campaigns.">
                    <Input id="app" inputMode="numeric" value={appId} onChange={(e) => setAppId(e.target.value.replace(/\D/g, ""))} placeholder="e.g. 548231" />
                </Field>
                <Field label="Your ExoPhone numbers" id="nums" hint="Separate several with commas.">
                    <Input id="nums" value={numbers} onChange={(e) => setNumbers(e.target.value)} placeholder="e.g. 044 4567 8900" />
                </Field>
                {numbers.trim() && <AgentPicker agents={agents} value={botId} onChange={setBotId} />}
            </div>
            <Footer>
                <Button variant="ghost" onClick={onCancel}>Later</Button>
                <Button variant="primary" onClick={finish} disabled={busy || (!numbers.trim() && appId === (account.app_id ?? ""))}>{busy ? "Saving…" : "Save"}</Button>
            </Footer>
        </>
    );
}
