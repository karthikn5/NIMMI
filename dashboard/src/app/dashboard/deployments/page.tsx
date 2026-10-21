"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, ExternalLink, FileArchive, FolderUp, GitBranch, Globe, Plus, RotateCcw } from "lucide-react";
import AppHeader from "@/components/AppHeader";
import { Button, Card, Dialog, EmptyState, Input, Notice, Skeleton, Status, ToastProvider, cn, useToast } from "@/components/ui";
import { apiJson } from "@/lib/api";
import { formatBytes } from "@/lib/plan";
import { SOURCE_LABEL, hostOf, timeAgo, type Site, type SiteList } from "@/components/deployments/shared";

export default function DeploymentsPage() {
    return (
        <ToastProvider>
            <Deployments />
        </ToastProvider>
    );
}

function Deployments() {
    const toast = useToast();
    const [data, setData] = useState<SiteList | null>(null);
    const [error, setError] = useState(false);
    const [creating, setCreating] = useState(false);
    const [restoring, setRestoring] = useState<string | null>(null);

    const load = useCallback(async () => {
        try {
            setData(await apiJson<SiteList>("/api/sites"));
            setError(false);
        } catch {
            setError(true);
        }
    }, []);
    useEffect(() => { load(); }, [load]);

    // Keep "Deploying…" rows moving without a refresh.
    const building = data?.sites.some((s) => s.latest?.status === "building");
    useEffect(() => {
        if (!building) return;
        const t = setInterval(load, 2500);
        return () => clearInterval(t);
    }, [building, load]);

    const restore = async (s: Site) => {
        setRestoring(s.id);
        try {
            await apiJson(`/api/sites/${s.id}/restore`, { method: "POST" });
            await load();
            toast(`${s.name} is back online.`);
        } catch (e) {
            toast((e as Error).message);
        } finally {
            setRestoring(null);
        }
    };

    const atLimit = !!data && data.sites.length >= data.limits.sites;

    return (
        <div className="min-h-screen bg-paper text-ink">
            <AppHeader />
            <main className="max-w-6xl mx-auto px-4 sm:px-6 py-8 pb-24">
                <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
                    <div>
                        <h1 className="text-2xl font-semibold tracking-tight">Deployments</h1>
                        <p className="text-sm text-stone-500 mt-1">Publish your website and get a free web address. Connect your own domain on a paid plan.</p>
                    </div>
                    {data?.ready && (
                        <Button variant="primary" onClick={() => setCreating(true)} className="self-start sm:self-auto">
                            <Plus size={15} /> New deployment
                        </Button>
                    )}
                </div>

                {data && !data.ready && (
                    <Notice title="Publishing isn't switched on yet" className="mt-6 mb-0">
                        Websites can be published once the Nimmi team finishes setting up hosting on this server.
                    </Notice>
                )}

                {data && (
                    <Card className="mt-6 grid sm:grid-cols-3 [&>*]:border-line">
                        <div className="p-5">
                            <p className="text-[13px] text-stone-500">Websites</p>
                            <p className="text-[28px] leading-none font-semibold tracking-tight tabular-nums mt-3">
                                {data.sites.length} <span className="text-sm font-normal text-stone-500">of {data.limits.sites}</span>
                            </p>
                            <p className="text-xs text-stone-500 mt-2">{data.limits.paid ? "On your paid plan" : "Free plan"}</p>
                        </div>
                        <div className="p-5 border-t sm:border-t-0 sm:border-l">
                            <p className="text-[13px] text-stone-500">Each deployment</p>
                            <p className="text-[28px] leading-none font-semibold tracking-tight tabular-nums mt-3">{formatBytes(data.limits.deploy_bytes)}</p>
                            <p className="text-xs text-stone-500 mt-2">Up to {data.limits.deploy_files.toLocaleString("en-IN")} files, {formatBytes(data.limits.file_bytes)} each</p>
                        </div>
                        {data.custom_domains ? (
                            <div className="p-5 border-t sm:border-t-0 sm:border-l">
                                <p className="text-[13px] text-stone-500">Custom domains</p>
                                <p className="text-[15px] font-medium mt-3">Included</p>
                                <p className="text-xs text-stone-500 mt-2">Connect GoDaddy or any other domain from a site&apos;s page</p>
                            </div>
                        ) : (
                            <Link href="/dashboard/billing" className="group p-5 border-t sm:border-t-0 sm:border-l hover:bg-stone-50 transition-colors">
                                <p className="text-[13px] text-stone-500">Custom domains</p>
                                <p className="text-[15px] font-medium mt-3">Paid plans</p>
                                <p className="text-xs text-plum mt-2 inline-flex items-center gap-1">Use your own domain, like www.yourbusiness.in <ArrowRight size={12} className="group-hover:translate-x-0.5 transition-transform" /></p>
                            </Link>
                        )}
                    </Card>
                )}

                <section className="mt-10" aria-labelledby="sites-heading">
                    <h2 id="sites-heading" className="sr-only">Your websites</h2>
                    <Card>
                        {data === null && !error ? (
                            <div className="p-5 space-y-3">{[0, 1].map((i) => <Skeleton key={i} className="h-14" />)}</div>
                        ) : error && !data ? (
                            <EmptyState title="Couldn't load your websites" body="Check your connection and try again."
                                        action={<Button size="sm" onClick={load}>Try again</Button>} />
                        ) : data!.sites.length === 0 ? (
                            <FirstSite onStart={() => setCreating(true)} ready={data!.ready} />
                        ) : (
                            <ul>{data!.sites.map((s) => <SiteRow key={s.id} site={s} />)}</ul>
                        )}
                    </Card>
                </section>

                {!!data?.deleted.length && (
                    <section className="mt-6" aria-labelledby="deleted-sites">
                        <Card>
                            <div className="px-5 pt-4 pb-3">
                                <h2 id="deleted-sites" className="text-sm font-medium">Recently deleted</h2>
                                <p className="text-[13px] text-stone-500 mt-0.5">Bring a website back online with all its versions. Each is removed for good 30 days after it was deleted.</p>
                            </div>
                            <ul className="border-t border-line">
                                {data.deleted.map((s) => (
                                    <li key={s.id} className="flex items-center gap-4 px-5 py-3 border-t border-line first:border-t-0">
                                        <div className="min-w-0 flex-1">
                                            <p className="text-sm truncate">{s.name}</p>
                                            <p className="text-xs text-stone-500 mt-0.5">{hostOf(s.url)} · deleted {timeAgo(s.deleted_at)}</p>
                                        </div>
                                        <Button size="sm" onClick={() => restore(s)} disabled={restoring === s.id || atLimit}
                                                title={atLimit ? "You're at your plan's website limit" : undefined}>
                                            <RotateCcw size={13} /> {restoring === s.id ? "Restoring…" : "Restore"}
                                        </Button>
                                    </li>
                                ))}
                            </ul>
                        </Card>
                    </section>
                )}
            </main>

            {data && (
                <NewSiteDialog open={creating} onClose={() => setCreating(false)} domain={data.domain || ""}
                               atLimit={atLimit} paid={data.limits.paid} limit={data.limits.sites} />
            )}
        </div>
    );
}

function SiteRow({ site }: { site: Site }) {
    const latest = site.latest;
    const status = site.status === "blocked" ? <Status tone="bad">Taken down</Status>
        : latest?.status === "building" ? <Status tone="warn">Deploying…</Status>
        : latest?.status === "failed" && site.live ? <Status tone="bad">Last deploy failed</Status>
        : site.live ? <Status tone="good">Live</Status>
        : latest?.status === "failed" ? <Status tone="bad">Deploy failed</Status>
        : <Status tone="neutral">Not published yet</Status>;
    const address = site.domain?.status === "active" ? site.domain.url : site.url;
    return (
        <li className="relative flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-6 px-5 py-4 border-t border-line first:border-t-0 hover:bg-stone-50/70 transition-colors">
            <div className="flex items-center gap-3 min-w-0 sm:w-[38%]">
                <span className="h-9 w-9 shrink-0 rounded-md bg-plum-tint text-plum flex items-center justify-center text-sm font-semibold" aria-hidden>
                    {site.name.slice(0, 1).toUpperCase()}
                </span>
                <div className="min-w-0">
                    <Link href={`/dashboard/deployments/${site.id}`} className="block text-sm font-medium truncate after:absolute after:inset-0">{site.name}</Link>
                    <p className="text-xs text-stone-500 truncate">{hostOf(address)}</p>
                </div>
            </div>
            <div className="sm:w-[22%]">{status}</div>
            <p className="text-[13px] text-stone-500 sm:flex-1 truncate">
                {latest ? `${SOURCE_LABEL[latest.source]} · ${timeAgo(latest.created_at)}` : "Waiting for its first version"}
                {site.domain && site.domain.status !== "active" && " · domain being connected"}
            </p>
            {site.live && address && (
                <a href={address} target="_blank" rel="noopener noreferrer" aria-label={`Visit ${site.name}`}
                   className="relative z-10 self-start sm:self-auto inline-flex items-center gap-1.5 h-8 px-3 rounded-md border border-line-strong bg-white text-[13px] font-medium hover:bg-stone-50">
                    Visit <ExternalLink size={13} />
                </a>
            )}
        </li>
    );
}

function FirstSite({ onStart, ready }: { onStart: () => void; ready: boolean }) {
    const ways = [
        { icon: FolderUp, title: "Drop a folder", body: "The folder with your index.html, straight from your computer." },
        { icon: FileArchive, title: "Upload a .zip", body: "Your website zipped up, as a designer or template site gives it to you." },
        { icon: GitBranch, title: "Import from GitHub", body: "Publish a repository, and again on every push if you like." },
    ];
    return (
        <div className="px-6 py-12 text-center">
            <Globe size={26} className="mx-auto text-stone-400" aria-hidden />
            <p className="mt-3 text-sm font-medium">Publish your first website</p>
            <p className="text-[13px] text-stone-500 mt-1 max-w-md mx-auto">It goes live on a free address in seconds. Add your assistant to every page with one switch.</p>
            <div className="mt-8 grid sm:grid-cols-3 gap-3 max-w-3xl mx-auto text-left">
                {ways.map(({ icon: Icon, title, body }) => (
                    <div key={title} className="rounded-lg border border-line bg-white p-4">
                        <span className="h-8 w-8 rounded-md bg-plum-tint text-plum flex items-center justify-center" aria-hidden><Icon size={16} /></span>
                        <p className="mt-3 text-sm font-medium">{title}</p>
                        <p className="mt-1 text-[13px] text-stone-500 leading-relaxed">{body}</p>
                    </div>
                ))}
            </div>
            {ready && <Button variant="primary" className="mt-8" onClick={onStart}><Plus size={15} /> New deployment</Button>}
        </div>
    );
}

const slugify = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").replace(/-{2,}/g, "-").slice(0, 40).replace(/-+$/, "");

function NewSiteDialog({ open, onClose, domain, atLimit, paid, limit }: {
    open: boolean; onClose: () => void; domain: string; atLimit: boolean; paid: boolean; limit: number;
}) {
    const router = useRouter();
    const [name, setName] = useState("");
    const [slug, setSlug] = useState("");
    const [edited, setEdited] = useState(false);
    const [check, setCheck] = useState<{ slug: string; available: boolean; problem: string | null } | null>(null);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const seq = useRef(0);

    useEffect(() => { if (open) { setName(""); setSlug(""); setEdited(false); setCheck(null); setError(null); } }, [open]);
    useEffect(() => { if (!edited) setSlug(slugify(name)); }, [name, edited]);
    useEffect(() => {
        if (!slug) return setCheck(null);
        const mine = ++seq.current;
        const t = setTimeout(async () => {
            try {
                const res = await apiJson<{ slug: string; available: boolean; problem: string | null }>(`/api/sites/check?slug=${encodeURIComponent(slug)}`);
                if (mine === seq.current) setCheck(res);
            } catch { /* checked again on create */ }
        }, 300);
        return () => clearTimeout(t);
    }, [slug]);

    const create = async () => {
        if (!name.trim()) return setError("Give your website a name.");
        setBusy(true);
        setError(null);
        try {
            const site = await apiJson<Site>("/api/sites", { method: "POST", json: { name: name.trim(), slug: slug || undefined } });
            router.push(`/dashboard/deployments/${site.id}`);
        } catch (e) {
            setError((e as Error).message);
            setBusy(false);
        }
    };

    if (atLimit) {
        return (
            <Dialog open={open} onClose={onClose} title={paid ? "You're at your website limit" : "The free plan includes one website"}
                    description={paid ? `Your plan includes up to ${limit} websites. Delete one to publish another.`
                                       : "Choose a plan for one of your assistants to publish more websites and connect your own domains."}
                    footer={<>
                        <Button variant="ghost" onClick={onClose}>Close</Button>
                        {!paid && <Link href="/dashboard/billing"><Button variant="primary">Choose a plan</Button></Link>}
                    </>}>
                <span />
            </Dialog>
        );
    }

    const ok = check?.slug === slug && check.available;
    return (
        <Dialog open={open} onClose={onClose} title="New deployment" description="Name your website and choose its address. You'll upload it next."
                footer={<>
                    <Button variant="ghost" onClick={onClose}>Cancel</Button>
                    <Button variant="primary" onClick={create} disabled={busy || !name.trim() || (!!check && check.slug === slug && !check.available)}>
                        {busy ? "Creating…" : "Continue"}
                    </Button>
                </>}>
            <div className="space-y-4">
                <div>
                    <label htmlFor="site-name" className="block text-[13px] font-medium text-stone-700 mb-1.5">Website name</label>
                    <Input id="site-name" autoFocus value={name} maxLength={80} placeholder="e.g. Green Park Homes"
                           onChange={(e) => setName(e.target.value)} onKeyDown={(e) => e.key === "Enter" && create()} />
                </div>
                <div>
                    <label htmlFor="site-slug" className="block text-[13px] font-medium text-stone-700 mb-1.5">Address</label>
                    <div className={cn("flex items-center rounded-md border bg-white focus-within:border-plum",
                                       check && check.slug === slug && !check.available ? "border-signal" : "border-line-strong")}>
                        <span className="pl-3 text-[13px] text-stone-500 select-none">https://</span>
                        <input id="site-slug" value={slug} maxLength={40} spellCheck={false}
                               onChange={(e) => { setEdited(true); setSlug(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, "")); }}
                               className="min-w-0 flex-1 h-9 px-0.5 text-sm bg-transparent outline-none" placeholder="your-site" />
                        <span className="pr-3 text-[13px] text-stone-500 select-none truncate max-w-[45%]">.{domain}</span>
                    </div>
                    <p className={cn("mt-1.5 text-[12px]", ok ? "text-emerald-700" : check && check.slug === slug ? "text-signal" : "text-stone-500")}>
                        {!slug ? "Letters, numbers and hyphens." : check && check.slug === slug ? (check.available ? "Available" : check.problem) : "Checking…"}
                    </p>
                </div>
                {error && <p role="alert" className="text-[13px] text-signal">{error}</p>}
            </div>
        </Dialog>
    );
}
