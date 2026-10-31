"use client";

import { useState } from "react";
import { Check, ChevronDown, Copy, RefreshCw } from "lucide-react";
import { Button, Card, Dialog, Input, Skeleton, Status, cn, useToast } from "@/components/ui";
import { apiJson } from "@/lib/api";
import type { DnsRecord, SendingDomain } from "@/lib/email";
import { useApi } from "@/lib/useApi";
import { formatWhen } from "@/lib/voice/api";

const tone = (d: SendingDomain) =>
    d.verified ? "good" : d.status === "failed" || d.status === "temporary_failure" ? "bad" : "warn";

/** Send from the business's own domain: add it, add the DNS records Resend gives, and Nimmi checks them. */
export function DomainSetup({ onChanged }: { onChanged?: () => void }) {
    const toast = useToast();
    const list = useApi<SendingDomain[]>("/api/email/domains");
    const [name, setName] = useState("");
    const [adding, setAdding] = useState(false);

    const add = async () => {
        if (!name.trim()) return;
        setAdding(true);
        try {
            const d = await apiJson<SendingDomain>("/api/email/domains", { method: "POST", json: { name } });
            list.setData([...(list.data ?? []).filter((x) => x.id !== d.id), d]);
            setName("");
            toast(`${d.name} added. Now add its DNS records.`);
            onChanged?.();
        } catch (e) {
            toast((e as Error).message);
        } finally {
            setAdding(false);
        }
    };

    const replace = (d: SendingDomain) => {
        const before = list.data?.find((x) => x.id === d.id);
        list.setData((list.data ?? []).map((x) => (x.id === d.id ? d : x)));
        if (before && before.verified !== d.verified) onChanged?.();
    };
    const removed = (id: string) => { list.setData((list.data ?? []).filter((x) => x.id !== id)); onChanged?.(); };

    return (
        <Card>
            <div className="px-5 pt-4 pb-3">
                <h2 className="text-sm font-medium">Send from your own domain</h2>
                <p className="text-[13px] text-stone-500 mt-0.5 max-w-2xl">
                    Emails then come from an address like hello@yourbusiness.in instead of Nimmi&apos;s sending address. People trust them more,
                    and Gmail and Outlook are more likely to show them in the inbox. It takes three DNS records at the company where you bought the domain.
                </p>
            </div>
            {list.error ? <p className="px-5 pb-4 text-sm text-signal">{list.error}</p> : !list.data ? (
                <div className="px-5 pb-5"><Skeleton className="h-20" /></div>
            ) : (
                <ul>
                    {list.data.map((d) => <DomainRow key={d.id} domain={d} onChanged={replace} onRemoved={removed} />)}
                </ul>
            )}
            <form className="flex flex-col sm:flex-row gap-2 px-5 py-4 border-t border-line" onSubmit={(e) => { e.preventDefault(); void add(); }}>
                <label htmlFor="new-domain" className="sr-only">Your domain</label>
                <Input id="new-domain" placeholder="yourbusiness.in" value={name} onChange={(e) => setName(e.target.value)}
                       autoCapitalize="none" autoCorrect="off" spellCheck={false} className="sm:max-w-sm" />
                <Button type="submit" variant={list.data?.length ? "secondary" : "primary"} disabled={adding || !name.trim()}>
                    {adding ? "Adding…" : "Add domain"}
                </Button>
            </form>
        </Card>
    );
}

function DomainRow({ domain: d, onChanged, onRemoved }: {
    domain: SendingDomain; onChanged: (d: SendingDomain) => void; onRemoved: (id: string) => void;
}) {
    const toast = useToast();
    const [open, setOpen] = useState(!d.verified);
    const [checking, setChecking] = useState(false);
    const [removing, setRemoving] = useState(false);
    const [confirm, setConfirm] = useState(false);

    const check = async () => {
        setChecking(true);
        try {
            const next = await apiJson<SendingDomain>(`/api/email/domains/${d.id}/verify`, { method: "POST" });
            onChanged(next);
            toast(next.verified ? `${next.name} is verified` : "Not found yet. DNS changes can take up to a few hours to show.");
        } catch (e) {
            toast((e as Error).message);
        } finally {
            setChecking(false);
        }
    };

    const remove = async () => {
        setRemoving(true);
        try {
            await apiJson(`/api/email/domains/${d.id}`, { method: "DELETE" });
            toast(`${d.name} removed. Emails go from Nimmi's sending address again.`);
            onRemoved(d.id);
        } catch (e) {
            toast((e as Error).message);
            setRemoving(false);
        }
    };

    return (
        <li className="border-t border-line">
            <div className="flex flex-wrap items-center gap-3 px-5 py-3">
                <button type="button" onClick={() => setOpen(!open)} aria-expanded={open}
                        className="flex items-center gap-2 text-left min-w-0 rounded focus-visible:outline-2 focus-visible:outline-plum">
                    <ChevronDown size={15} className={cn("text-stone-400 shrink-0 transition-transform", open && "rotate-180")} aria-hidden />
                    <span className="text-sm font-medium truncate">{d.name}</span>
                </button>
                <Status tone={tone(d)}>{d.status_label}</Status>
                <div className="ml-auto flex items-center gap-2">
                    {!d.verified && (
                        <Button size="sm" onClick={check} disabled={checking}>
                            <RefreshCw size={13} className={checking ? "animate-spin" : undefined} aria-hidden /> {checking ? "Checking…" : "Check now"}
                        </Button>
                    )}
                    <Button size="sm" variant="ghost" onClick={() => setConfirm(true)}>Remove</Button>
                </div>
            </div>
            {open && (
                <div className="px-5 pb-5">
                    {d.verified ? (
                        <p className="text-[13px] text-stone-600">
                            Verified{d.verified_at ? ` ${formatWhen(d.verified_at).toLowerCase()}` : ""}. Choose it below, under who emails come from.
                            {d.bulk_today !== null && ` It's new, so mail services are still learning to trust it: bulk email from it is limited to ${d.bulk_today.toLocaleString("en-IN")} today, about twice as many each day this week.`}
                        </p>
                    ) : (
                        <>
                            <p className="text-[13px] text-stone-600 mb-3">
                                Add these records where your domain&apos;s DNS is managed. They go on parts of the domain your email doesn&apos;t use, so your
                                existing email keeps working. Nimmi checks for them every few minutes for 3 days{d.checked_at ? `; last checked ${formatWhen(d.checked_at).toLowerCase()}` : ""}.
                            </p>
                            <Records records={d.records} />
                            <HowTo />
                        </>
                    )}
                </div>
            )}
            <Dialog open={confirm} onClose={() => setConfirm(false)} title={`Remove ${d.name}?`}
                    description="Emails will come from Nimmi's sending address under your business's name again. You can add the domain back later."
                    footer={<>
                        <Button variant="ghost" onClick={() => setConfirm(false)}>Cancel</Button>
                        <Button variant="danger" onClick={remove} disabled={removing}>{removing ? "Removing…" : "Remove"}</Button>
                    </>}>
                <p className="text-[13px] text-stone-600">The DNS records you added can stay or go; they don&apos;t affect your other email.</p>
            </Dialog>
        </li>
    );
}

function Records({ records }: { records: DnsRecord[] }) {
    return (
        <div className="rounded-md border border-line overflow-hidden">
            <div className="hidden md:grid grid-cols-[4.5rem_minmax(0,1fr)_minmax(0,2fr)_4.5rem_6.5rem] gap-x-3 px-3 py-2 bg-paper text-xs text-stone-500">
                <span>Type</span><span>Name</span><span>Value</span><span>Priority</span><span>Status</span>
            </div>
            <ul>
                {records.map((r, i) => (
                    <li key={`${r.type}-${r.host}-${i}`} className="grid grid-cols-1 md:grid-cols-[4.5rem_minmax(0,1fr)_minmax(0,2fr)_4.5rem_6.5rem] gap-x-3 gap-y-1.5 px-3 py-2.5 border-t border-line first:border-t-0 md:first:border-t text-[13px]">
                        <span className="font-medium">{r.type}<span className="md:hidden text-stone-500 font-normal"> · {r.purpose}</span></span>
                        <CopyField label="Name" value={r.host} />
                        <CopyField label="Value" value={r.value} />
                        <span className="text-stone-600"><span className="md:hidden text-stone-500">Priority </span>{r.priority ?? "–"}</span>
                        <span><Status tone={r.status === "verified" ? "good" : r.status === "failed" ? "bad" : "neutral"}>
                            {r.status === "verified" ? "Found" : r.status === "failed" ? "Not found" : "Waiting"}
                        </Status></span>
                    </li>
                ))}
            </ul>
        </div>
    );
}

function CopyField({ label, value }: { label: string; value: string }) {
    const [copied, setCopied] = useState(false);
    const copy = async () => {
        try {
            await navigator.clipboard.writeText(value);
            setCopied(true);
            setTimeout(() => setCopied(false), 1500);
        } catch { /* clipboard blocked: the value is selectable */ }
    };
    return (
        <span className="flex items-start gap-1.5 min-w-0">
            <code className="font-mono text-[12px] break-all select-all text-stone-800">{value}</code>
            <button type="button" onClick={copy} aria-label={`Copy ${label.toLowerCase()}: ${value.slice(0, 40)}`}
                    className="shrink-0 mt-0.5 text-stone-400 hover:text-ink rounded focus-visible:outline-2 focus-visible:outline-plum">
                {copied ? <Check size={13} className="text-emerald-600" /> : <Copy size={13} />}
            </button>
        </span>
    );
}

function HowTo() {
    const [open, setOpen] = useState(false);
    return (
        <div className="mt-3">
            <button type="button" onClick={() => setOpen(!open)} aria-expanded={open}
                    className="inline-flex items-center gap-1.5 text-[13px] text-plum hover:underline rounded focus-visible:outline-2 focus-visible:outline-plum">
                <ChevronDown size={14} className={cn("transition-transform", open && "rotate-180")} aria-hidden /> How to add DNS records
            </button>
            {open && (
                <div className="mt-2 text-[13px] text-stone-600 space-y-2 max-w-3xl">
                    <p><span className="font-medium text-ink">GoDaddy:</span> Domain Portfolio (or My Products) &gt; your domain &gt; DNS &gt; Add New Record. Pick the type, put the Name in &ldquo;Name&rdquo; (GoDaddy adds your domain by itself), paste the Value, and for MX the Priority. Save.</p>
                    <p><span className="font-medium text-ink">Cloudflare:</span> your domain &gt; DNS &gt; Records &gt; Add record. Pick the type, enter the Name and paste the Value into &ldquo;Content&rdquo; (&ldquo;Mail server&rdquo; for MX, with the Priority). Save.</p>
                    <p><span className="font-medium text-ink">Hostinger:</span> Domains &gt; your domain &gt; DNS / Nameservers &gt; DNS records. Add each record with its type, name and value.</p>
                    <p><span className="font-medium text-ink">Others:</span> look for &ldquo;DNS settings&rdquo;, &ldquo;DNS management&rdquo; or &ldquo;Zone editor&rdquo; where you bought the domain. Enter the Name exactly as shown, without your domain after it.</p>
                    <p>Changes usually show within an hour, sometimes a few hours. Press Check now any time.</p>
                </div>
            )}
        </div>
    );
}
