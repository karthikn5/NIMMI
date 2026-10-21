"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ArrowRight, Check, Copy, Download, ExternalLink, Lock, X } from "lucide-react";
import { apiBase, apiFetch } from "@/lib/api";
import { Button, Select, Skeleton, cn } from "@/components/ui";
import { GROUPS, PLATFORMS, type Block, type Ctx, type Platform } from "@/components/install/platforms";

type Access = { state: "checking" } | { state: "open"; botName: string; plan: string } | { state: "locked"; message: string } | { state: "error" };

/**
 * "Add to website": install code for websites, WordPress and phone apps.
 * Code is only put on the page once the server confirms the assistant has an active plan.
 */
export default function ExportModal({ botId, botName = "your assistant", onClose }: { botId: string; botName?: string; onClose: () => void }) {
    const [access, setAccess] = useState<Access>({ state: "checking" });
    const [active, setActive] = useState<Platform>(PLATFORMS[0]);

    const check = async () => {
        setAccess({ state: "checking" });
        try {
            const res = await apiFetch(`/api/bots/${botId}/install`);
            const body = await res.json().catch(() => ({}));
            if (res.ok) setAccess({ state: "open", botName: body.bot_name || botName, plan: body.plan });
            else if (res.status === 402) setAccess({ state: "locked", message: body.detail });
            else setAccess({ state: "error" });
        } catch {
            setAccess({ state: "error" });
        }
    };
    useEffect(() => { check(); }, [botId]); // eslint-disable-line react-hooks/exhaustive-deps

    useEffect(() => {
        const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
        document.addEventListener("keydown", onKey);
        const overflow = document.body.style.overflow;
        document.body.style.overflow = "hidden";
        return () => { document.removeEventListener("keydown", onKey); document.body.style.overflow = overflow; };
    }, [onClose]);

    const name = access.state === "open" ? access.botName : botName;
    const ctx: Ctx | null = useMemo(() => (access.state === "open" && typeof window !== "undefined"
        ? { botId, botName: name, api: apiBase(), dashboard: window.location.origin } : null), [access.state, botId, name]);

    return (
        <div className="fixed inset-0 z-[100] flex items-end sm:items-center justify-center sm:p-4">
            <div className="absolute inset-0 bg-ink/40" onClick={onClose} aria-hidden />
            <div role="dialog" aria-modal="true" aria-labelledby="install-title"
                 className="relative w-full max-w-5xl h-[92vh] sm:h-[min(780px,90vh)] bg-white sm:rounded-xl rounded-t-xl border border-line shadow-[0_24px_64px_-16px_rgba(28,23,25,0.35)] flex flex-col overflow-hidden text-ink">
                <header className="flex items-start justify-between gap-4 px-5 sm:px-6 py-4 border-b border-line">
                    <div className="min-w-0">
                        <h2 id="install-title" className="text-[17px] font-semibold tracking-tight truncate">Add {name} to your website or app</h2>
                        <p className="text-[13px] text-stone-500 mt-0.5">Choose where your customers will chat with it. Every option uses the same assistant, knowledge and design.</p>
                    </div>
                    <button type="button" onClick={onClose} aria-label="Close" className="p-1.5 -mr-1.5 rounded-md text-stone-400 hover:text-ink hover:bg-stone-100">
                        <X size={18} />
                    </button>
                </header>

                <div className="flex-1 min-h-0 flex flex-col md:flex-row">
                    {/* Platforms: a list beside the content, a menu on small screens. */}
                    <nav aria-label="Where to add it" className="hidden md:block w-60 shrink-0 border-r border-line bg-stone-50/70 overflow-y-auto py-3">
                        {GROUPS.map((group) => (
                            <div key={group} className="mb-3">
                                <p className="px-5 pt-2 pb-1.5 text-[11px] font-medium uppercase tracking-wide text-stone-400">{group}</p>
                                <ul>
                                    {PLATFORMS.filter((p) => p.group === group).map((p) => (
                                        <li key={p.id}>
                                            <button type="button" onClick={() => setActive(p)} aria-current={active.id === p.id ? "true" : undefined}
                                                    className={cn("w-full flex items-center justify-between gap-2 px-5 py-2 text-left text-[13px] transition-colors border-l-2",
                                                                  active.id === p.id ? "border-plum bg-white text-ink font-medium" : "border-transparent text-stone-600 hover:text-ink hover:bg-white/70")}>
                                                <span className="truncate">{p.label}</span>
                                                {p.tag && <span className="text-[11px] text-stone-400 shrink-0">{p.tag}</span>}
                                            </button>
                                        </li>
                                    ))}
                                </ul>
                            </div>
                        ))}
                    </nav>
                    <div className="md:hidden px-5 pt-4">
                        <Select aria-label="Where to add it" className="w-full" value={active.id}
                                onChange={(e) => setActive(PLATFORMS.find((p) => p.id === e.target.value) || PLATFORMS[0])}>
                            {GROUPS.map((group) => (
                                <optgroup key={group} label={group}>
                                    {PLATFORMS.filter((p) => p.group === group).map((p) => (
                                        <option key={p.id} value={p.id}>{p.label}</option>
                                    ))}
                                </optgroup>
                            ))}
                        </Select>
                    </div>

                    <section className="flex-1 min-w-0 overflow-y-auto px-5 sm:px-8 py-6">
                        <h3 className="text-[19px] font-semibold tracking-tight">{active.title}</h3>
                        <p className="text-[14px] text-stone-600 mt-1 max-w-2xl leading-relaxed">{active.summary}</p>

                        {active.needsPlan && access.state === "checking" ? (
                            <div className="mt-6 space-y-3"><Skeleton className="h-5 w-2/3" /><Skeleton className="h-5 w-1/2" /><Skeleton className="h-40" /></div>
                        ) : active.needsPlan && access.state === "locked" ? (
                            <Locked botId={botId} name={name} />
                        ) : active.needsPlan && access.state === "error" ? (
                            <div className="mt-6 rounded-lg border border-line px-4 py-3 flex items-center gap-3">
                                <p className="text-[13px] text-stone-600">We couldn&apos;t check this assistant&apos;s plan.</p>
                                <Button size="sm" onClick={check} className="ml-auto">Try again</Button>
                            </div>
                        ) : (
                            <Guide platform={active} ctx={ctx} botId={botId} />
                        )}
                    </section>
                </div>

                <footer className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 px-5 sm:px-6 py-3.5 border-t border-line bg-stone-50/70">
                    <div className="text-[12px] text-stone-500 flex flex-wrap items-center gap-x-4 gap-y-1">
                        {access.state === "open" && <span>Plan: {access.plan}</span>}
                        <Link href={`/demo/${botId}`} target="_blank" className="inline-flex items-center gap-1 text-plum hover:underline">
                            Try it on a test page <ExternalLink size={12} />
                        </Link>
                    </div>
                    <Button onClick={onClose} className="self-end sm:self-auto">Done</Button>
                </footer>
            </div>
        </div>
    );
}

function Guide({ platform, ctx, botId }: { platform: Platform; ctx: Ctx | null; botId: string }) {
    const blocks: Block[] = ctx ? platform.blocks(ctx) : [];
    return (
        <div className="mt-6 space-y-6">
            {platform.download === "wordpress" && ctx && <WordPressDownload botId={botId} ctx={ctx} />}
            <ol className="space-y-3 max-w-2xl">
                {platform.steps.map((step, i) => (
                    <li key={i} className="flex gap-3 text-[14px] leading-relaxed text-stone-700">
                        <span className="mt-0.5 h-6 w-6 shrink-0 rounded-full bg-plum-tint text-plum text-[12px] font-semibold flex items-center justify-center">{i + 1}</span>
                        <span>{step}</span>
                    </li>
                ))}
            </ol>
            {blocks.map((b) => <CodeBlock key={b.label} block={b} />)}
            {platform.link && (
                <Link href={platform.link.href} className="inline-flex items-center gap-1.5 h-9 px-4 rounded-md bg-plum text-white text-sm font-medium hover:bg-plum-hover">
                    {platform.link.label} <ArrowRight size={15} />
                </Link>
            )}
        </div>
    );
}

function CodeBlock({ block }: { block: Block }) {
    const [copied, setCopied] = useState(false);
    const copy = async () => {
        try {
            await navigator.clipboard.writeText(block.code);
            setCopied(true);
            setTimeout(() => setCopied(false), 1800);
        } catch { /* the code stays selectable */ }
    };
    return (
        <div className="rounded-lg border border-line overflow-hidden">
            <div className="flex items-center justify-between gap-3 px-4 py-2 bg-stone-50 border-b border-line">
                <span className="text-[12px] font-medium text-stone-600 truncate">{block.label}</span>
                <button type="button" onClick={copy} className={cn("inline-flex items-center gap-1.5 h-7 px-2.5 rounded-md text-[12px] font-medium border transition-colors shrink-0",
                                                                    copied ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-line-strong bg-white text-ink hover:bg-stone-50")}>
                    {copied ? <><Check size={13} /> Copied</> : <><Copy size={13} /> Copy</>}
                </button>
            </div>
            <pre className="px-4 py-3.5 bg-[#1c1719] text-[#f3eef4] text-[12.5px] leading-relaxed font-mono overflow-x-auto max-h-[420px]"><code>{block.code}</code></pre>
        </div>
    );
}

function WordPressDownload({ botId, ctx }: { botId: string; ctx: Ctx }) {
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const download = async () => {
        setBusy(true);
        setError(null);
        try {
            const res = await apiFetch(`/api/bots/${botId}/wordpress-plugin?api=${encodeURIComponent(ctx.api)}&dashboard=${encodeURIComponent(ctx.dashboard)}`);
            if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || "The download didn't work. Try again.");
            const url = URL.createObjectURL(await res.blob());
            const a = document.createElement("a");
            a.href = url;
            a.download = "nimmi-ai-chat.zip";
            document.body.appendChild(a);
            a.click();
            a.remove();
            setTimeout(() => URL.revokeObjectURL(url), 2000);
        } catch (e) {
            setError((e as Error).message);
        } finally {
            setBusy(false);
        }
    };
    return (
        <div className="rounded-lg border border-line bg-stone-50/60 px-4 py-4 flex flex-col sm:flex-row sm:items-center gap-3">
            <div>
                <p className="text-sm font-medium">Nimmi AI Chat for WordPress</p>
                <p className="text-[12px] text-stone-500 mt-0.5">Version 1.0.0 · WordPress 5.2 or later · already connected to {ctx.botName}</p>
                {error && <p role="alert" className="text-[12px] text-signal mt-1">{error}</p>}
            </div>
            <Button variant="primary" onClick={download} disabled={busy} className="sm:ml-auto shrink-0">
                <Download size={15} /> {busy ? "Preparing…" : "Download plugin (.zip)"}
            </Button>
        </div>
    );
}

function Locked({ botId, name }: { botId: string; name: string }) {
    return (
        <div className="mt-6 rounded-lg border border-line overflow-hidden">
            <div className="px-6 py-8 text-center">
                <span className="mx-auto h-11 w-11 rounded-full bg-plum-tint text-plum flex items-center justify-center" aria-hidden><Lock size={19} /></span>
                <p className="mt-4 text-[15px] font-semibold">Choose a plan to put {name} live</p>
                <p className="mt-1.5 text-[13px] text-stone-600 max-w-md mx-auto leading-relaxed">
                    Building and testing are free. Adding the assistant to a website or app needs an active plan; the code and the
                    WordPress plugin appear here right after you pay.
                </p>
                <div className="mt-5 flex flex-wrap justify-center gap-2">
                    <Link href={`/dashboard/billing?bot=${botId}`} className="inline-flex items-center h-9 px-4 rounded-md bg-plum text-white text-sm font-medium hover:bg-plum-hover">
                        Choose a plan
                    </Link>
                    <Link href={`/demo/${botId}`} target="_blank" className="inline-flex items-center gap-1.5 h-9 px-4 rounded-md border border-line-strong bg-white text-sm font-medium hover:bg-stone-50">
                        Test it first <ExternalLink size={13} />
                    </Link>
                </div>
            </div>
            {/* A hint of what's waiting, never the code itself. */}
            <div className="px-5 py-4 bg-[#1c1719] space-y-2" aria-hidden>
                {[72, 54, 88, 40, 64].map((w, i) => <div key={i} className="h-2.5 rounded bg-white/10" style={{ width: `${w}%` }} />)}
            </div>
        </div>
    );
}
