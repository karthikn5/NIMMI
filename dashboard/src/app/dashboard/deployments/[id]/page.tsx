"use client";

import { use, useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, Check, Copy, ExternalLink, GitBranch, RefreshCw, Trash2, Upload } from "lucide-react";
import AppHeader from "@/components/AppHeader";
import { Button, Card, Dialog, Input, Segmented, Select, Skeleton, Status, ToastProvider, cn, useToast } from "@/components/ui";
import { apiJson } from "@/lib/api";
import { formatBytes, useLimits } from "@/lib/plan";
import Uploader from "@/components/deployments/Uploader";
import { SOURCE_LABEL, hostOf, timeAgo, type Deploy, type Site, type SiteList } from "@/components/deployments/shared";

type Bot = { id: string; name: string };

export default function SitePage({ params }: { params: Promise<{ id: string }> }) {
    const { id } = use(params);
    return (
        <ToastProvider>
            <SiteScreen id={id} />
        </ToastProvider>
    );
}

function SiteScreen({ id }: { id: string }) {
    const toast = useToast();
    const limits = useLimits();
    const [site, setSite] = useState<Site | null>(null);
    const [meta, setMeta] = useState<Pick<SiteList, "custom_domains" | "custom_domains_available"> | null>(null);
    const [missing, setMissing] = useState(false);
    const [method, setMethod] = useState<"upload" | "git">("upload");

    const load = useCallback(async () => {
        try {
            setSite(await apiJson<Site>(`/api/sites/${id}`));
        } catch {
            setMissing(true);
        }
    }, [id]);
    useEffect(() => {
        load();
        apiJson<SiteList>("/api/sites").then((l) => setMeta({ custom_domains: l.custom_domains, custom_domains_available: l.custom_domains_available })).catch(() => {});
    }, [load]);
    const opened = useRef(false);
    useEffect(() => { // a site published from Git opens on Git
        if (site && !opened.current) { opened.current = true; if (site.git) setMethod("git"); }
    }, [site]);

    const building = site?.deploys?.some((d) => d.status === "building");
    const [wasBuilding, setWasBuilding] = useState(false);
    useEffect(() => {
        if (!building) return;
        setWasBuilding(true);
        const t = setInterval(load, 2000);
        return () => clearInterval(t);
    }, [building, load]);
    useEffect(() => { // say how the deploy ended
        if (building || !wasBuilding || !site?.latest) return;
        setWasBuilding(false);
        toast(site.latest.status === "ready" ? "Published. Your site is live." : site.latest.error || "The deploy failed.");
    }, [building, wasBuilding, site?.latest, toast]);

    const update = (s: Site) => setSite(s);

    if (missing) {
        return (
            <Shell>
                <Card className="p-8 text-center">
                    <p className="text-sm font-medium">This website doesn&apos;t exist</p>
                    <p className="text-[13px] text-stone-500 mt-1">It may have been deleted.</p>
                    <Link href="/dashboard/deployments" className="inline-block mt-5"><Button size="sm">Back to Deployments</Button></Link>
                </Card>
            </Shell>
        );
    }
    if (!site) {
        return <Shell><Skeleton className="h-8 w-64" /><Skeleton className="h-64 mt-6" /></Shell>;
    }

    const live = site.live;
    const address = site.domain?.status === "active" && site.domain.url ? site.domain.url : site.url;
    const uploadLimits = limits ?? { deploy_bytes: 25 * 1024 * 1024, deploy_files: 1000, file_bytes: 10 * 1024 * 1024 };

    return (
        <Shell>
            <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
                <div className="min-w-0">
                    <h1 className="text-2xl font-semibold tracking-tight truncate">{site.name}</h1>
                    <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1">
                        {site.status === "blocked" ? <Status tone="bad">Taken down</Status>
                            : building ? <Status tone="warn">Deploying…</Status>
                            : live ? <Status tone="good">Live</Status> : <Status tone="neutral">Not published yet</Status>}
                        {address && <CopyText text={address} label={hostOf(address)} />}
                    </div>
                </div>
                {live && address && (
                    <a href={address} target="_blank" rel="noopener noreferrer"
                       className="self-start sm:self-auto inline-flex items-center gap-1.5 h-9 px-4 rounded-md bg-plum text-white text-sm font-medium hover:bg-plum-hover">
                        Visit site <ExternalLink size={14} />
                    </a>
                )}
            </div>

            {site.status === "blocked" && (
                <Card className="mt-6 px-5 py-4 border-red-200 bg-red-50/40">
                    <p className="text-sm font-medium text-signal">This site was taken down</p>
                    <p className="text-[13px] text-stone-600 mt-0.5">It broke our terms of use. Write to support.nimmi@gmail.com if you think this is a mistake.</p>
                </Card>
            )}

            <div className="mt-6 grid lg:grid-cols-[minmax(0,1fr)_320px] gap-6 items-start">
                <div className="space-y-6 min-w-0">
                    {live && site.url && <Production site={site} live={live} />}

                    <Card>
                        <div className="px-5 pt-4 pb-3 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                            <div>
                                <h2 className="text-[15px] font-semibold">{live ? "Publish a new version" : "Publish your website"}</h2>
                                <p className="text-[13px] text-stone-500 mt-0.5">The current version stays live until the new one is ready.</p>
                            </div>
                            <Segmented label="How to publish" value={method} onChange={setMethod}
                                       options={[{ value: "upload", label: "Upload", icon: <Upload size={14} /> },
                                                 { value: "git", label: "From Git", icon: <GitBranch size={14} /> }]} />
                        </div>
                        <div className="px-5 pb-5">
                            {method === "upload"
                                ? <Uploader siteId={site.id} limits={uploadLimits} disabled={!!building} onStarted={() => load()} />
                                : <GitPanel site={site} disabled={!!building} onStarted={load} onChange={update} />}
                        </div>
                    </Card>

                    <DomainCard site={site} paid={meta?.custom_domains ?? false} available={meta?.custom_domains_available ?? true} onChange={update} />

                    <History site={site} onChange={update} />
                </div>

                <div className="space-y-6">
                    <AssistantCard site={site} onChange={update} />
                    <SettingsCard site={site} onChange={update} />
                    <DeleteCard site={site} />
                </div>
            </div>
        </Shell>
    );
}

function Shell({ children }: { children: ReactNode }) {
    return (
        <div className="min-h-screen bg-paper text-ink">
            <AppHeader />
            <main className="max-w-6xl mx-auto px-4 sm:px-6 py-8 pb-24">
                <Link href="/dashboard/deployments" className="inline-flex items-center gap-1.5 text-[13px] text-stone-500 hover:text-ink mb-4">
                    <ArrowLeft size={14} /> Deployments
                </Link>
                {children}
            </main>
        </div>
    );
}

function CopyText({ text, label, className }: { text: string; label?: string; className?: string }) {
    const [done, setDone] = useState(false);
    return (
        <button type="button" onClick={async () => { try { await navigator.clipboard.writeText(text); setDone(true); setTimeout(() => setDone(false), 1500); } catch { /* selectable anyway */ } }}
                className={cn("inline-flex items-center gap-1.5 max-w-full text-[13px] text-stone-600 hover:text-ink", className)} title="Copy">
            <span className="truncate font-mono text-[12.5px]">{label ?? text}</span>
            {done ? <Check size={13} className="text-emerald-700 shrink-0" /> : <Copy size={13} className="text-stone-400 shrink-0" />}
        </button>
    );
}

/* ---------- the live version ---------- */
function Production({ site, live }: { site: Site; live: Deploy }) {
    return (
        <Card className="overflow-hidden">
            <div className="grid md:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
                {/* A scaled-down, non-interactive look at the live site. */}
                <div className="relative aspect-[16/10] bg-stone-100 border-b md:border-b-0 md:border-r border-line overflow-hidden">
                    <iframe src={site.url!} title={`${site.name} preview`} loading="lazy" tabIndex={-1} aria-hidden
                            sandbox="allow-scripts allow-same-origin"
                            className="absolute top-0 left-0 w-[250%] h-[250%] origin-top-left scale-[0.4] pointer-events-none border-0 bg-white" />
                </div>
                <dl className="p-5 grid grid-cols-2 gap-x-4 gap-y-4 content-start text-[13px]">
                    <div className="col-span-2">
                        <dt className="text-stone-500">Live version</dt>
                        <dd className="mt-0.5 font-medium">{live.commit_message || (live.source === "upload" ? "Uploaded files" : "From your repository")}</dd>
                    </div>
                    <div><dt className="text-stone-500">Published</dt><dd className="mt-0.5">{timeAgo(live.finished_at || live.created_at)}</dd></div>
                    <div><dt className="text-stone-500">Source</dt><dd className="mt-0.5">{SOURCE_LABEL[live.source]}{live.commit_sha ? ` · ${live.commit_sha.slice(0, 7)}` : ""}</dd></div>
                    <div><dt className="text-stone-500">Files</dt><dd className="mt-0.5 tabular-nums">{live.file_count.toLocaleString("en-IN")}</dd></div>
                    <div><dt className="text-stone-500">Size</dt><dd className="mt-0.5 tabular-nums">{formatBytes(live.total_bytes)}</dd></div>
                </dl>
            </div>
        </Card>
    );
}

/* ---------- Git ---------- */
function GitPanel({ site, disabled, onStarted, onChange }: { site: Site; disabled: boolean; onStarted: () => void; onChange: (s: Site) => void }) {
    const toast = useToast();
    const [repo, setRepo] = useState(site.git?.url ?? "");
    const [branch, setBranch] = useState(site.git?.branch ?? "");
    const [folder, setFolder] = useState(site.git?.folder ?? "");
    const [token, setToken] = useState("");
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [hook, setHook] = useState<string | null>(null);

    const publish = async () => {
        setBusy(true);
        setError(null);
        try {
            await apiJson(`/api/sites/${site.id}/deploys/git`, { method: "POST", json: { repo_url: repo.trim(), branch: branch.trim() || null, folder: folder.trim() || null, token: token.trim() || null } });
            setToken("");
            onStarted();
        } catch (e) {
            setError((e as Error).message);
        } finally {
            setBusy(false);
        }
    };
    const makeHook = async () => {
        try {
            setHook((await apiJson<{ url: string }>(`/api/sites/${site.id}/hook`, { method: "POST" })).url);
            onChange({ ...site, git: site.git ? { ...site.git, hook: true } : site.git });
        } catch (e) { toast((e as Error).message); }
    };
    const removeHook = async () => {
        try {
            await apiJson(`/api/sites/${site.id}/hook`, { method: "DELETE" });
            setHook(null);
            onChange({ ...site, git: site.git ? { ...site.git, hook: false } : site.git });
            toast("Automatic publishing is off.");
        } catch (e) { toast((e as Error).message); }
    };

    return (
        <div className="space-y-4">
            <div className="grid sm:grid-cols-[minmax(0,1fr)_160px] gap-3">
                <Field label="Repository" htmlFor="repo">
                    <Input id="repo" value={repo} onChange={(e) => setRepo(e.target.value)} placeholder="https://github.com/you/your-site" spellCheck={false} />
                </Field>
                <Field label="Branch" htmlFor="branch" hint="Empty: the main branch">
                    <Input id="branch" value={branch} onChange={(e) => setBranch(e.target.value)} placeholder="main" spellCheck={false} />
                </Field>
            </div>
            <div className="grid sm:grid-cols-2 gap-3">
                <Field label="Folder to publish" htmlFor="folder" hint="Empty: found for you (the root, dist, build, docs…)">
                    <Input id="folder" value={folder} onChange={(e) => setFolder(e.target.value)} placeholder="e.g. dist" spellCheck={false} />
                </Field>
                <Field label="Access token" htmlFor="token" hint={site.git?.has_token ? "A token is saved. Enter a new one to replace it." : "Only for private repositories (read-only)"}>
                    <Input id="token" type="password" autoComplete="off" value={token} onChange={(e) => setToken(e.target.value)}
                           placeholder={site.git?.has_token ? "Saved" : "Optional"} />
                </Field>
            </div>
            <p className="text-[12px] text-stone-500">
                Nimmi publishes the files in your repository as they are; it doesn&apos;t run build commands. For React, Vue or Vite
                sites, commit the built folder (such as dist) or upload it.
            </p>
            {error && <p role="alert" className="text-[13px] text-signal">{error}</p>}
            <Button variant="primary" onClick={publish} disabled={busy || disabled || !repo.trim()}>
                <GitBranch size={15} /> {busy ? "Starting…" : site.git ? "Publish latest commit" : "Publish from repository"}
            </Button>

            {site.git && (
                <div className="rounded-md border border-line px-4 py-3">
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                        <div>
                            <p className="text-[13px] font-medium">Publish on every push</p>
                            <p className="text-[12px] text-stone-500 mt-0.5">A secret link GitHub or GitLab calls when you push to {site.git.branch || "the main branch"}.</p>
                        </div>
                        {site.git.hook && !hook ? (
                            <div className="flex gap-2 shrink-0">
                                <Button size="sm" onClick={makeHook}>New link</Button>
                                <Button size="sm" variant="ghost" onClick={removeHook}>Turn off</Button>
                            </div>
                        ) : !hook && <Button size="sm" onClick={makeHook} className="shrink-0">Turn on</Button>}
                    </div>
                    {hook && (
                        <div className="mt-3 space-y-2">
                            <div className="rounded-md bg-stone-50 border border-line px-3 py-2"><CopyText text={hook} /></div>
                            <p className="text-[12px] text-stone-600 leading-relaxed">
                                Copy it now; it isn&apos;t shown again. In GitHub: your repository, Settings, Webhooks, Add webhook. Paste it as the
                                Payload URL, choose application/json, and keep &ldquo;Just the push event&rdquo;. In GitLab: Settings, Webhooks, Push events.
                            </p>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}

function Field({ label, htmlFor, hint, children }: { label: string; htmlFor: string; hint?: string; children: ReactNode }) {
    return (
        <div>
            <label htmlFor={htmlFor} className="block text-[13px] font-medium text-stone-700 mb-1.5">{label}</label>
            {children}
            {hint && <p className="mt-1 text-[12px] text-stone-500">{hint}</p>}
        </div>
    );
}

/* ---------- custom domain ---------- */
const DOMAIN_STATUS = {
    pending: { tone: "warn", label: "Waiting for DNS records" },
    issuing: { tone: "warn", label: "Setting up HTTPS" },
    active: { tone: "good", label: "Connected" },
    failed: { tone: "bad", label: "Couldn't connect" },
} as const;

function DomainCard({ site, paid, available, onChange }: { site: Site; paid: boolean; available: boolean; onChange: (s: Site) => void }) {
    const toast = useToast();
    const [value, setValue] = useState("");
    const [busy, setBusy] = useState<"add" | "check" | "remove" | null>(null);
    const [error, setError] = useState<string | null>(null);
    const d = site.domain;

    const call = async (kind: "add" | "check" | "remove", path: string, init: Parameters<typeof apiJson>[1]) => {
        setBusy(kind);
        setError(null);
        try {
            const next = await apiJson<Site>(path, init);
            onChange(next);
            if (kind === "check" && next.domain?.status === "active") toast(`${next.domain.name} is connected.`);
            if (kind === "add") setValue("");
        } catch (e) {
            setError((e as Error).message);
        } finally {
            setBusy(null);
        }
    };

    return (
        <Card>
            <div className="px-5 pt-4 pb-3">
                <h2 className="text-[15px] font-semibold">Custom domain</h2>
                <p className="text-[13px] text-stone-500 mt-0.5">Show your site on your own domain, like www.yourbusiness.in, with HTTPS included.</p>
            </div>
            <div className="px-5 pb-5">
                {!paid ? (
                    <div className="flex flex-col sm:flex-row sm:items-center gap-3 rounded-md border border-line bg-stone-50/60 px-4 py-3">
                        <p className="text-[13px] text-stone-600">Custom domains come with a paid plan. Your site stays on its free address meanwhile.</p>
                        <Link href="/dashboard/billing" className="sm:ml-auto shrink-0"><Button size="sm" variant="primary">Choose a plan</Button></Link>
                    </div>
                ) : !available ? (
                    <p className="text-[13px] text-stone-600">Custom domains are being switched on for this server. Check back soon.</p>
                ) : !d ? (
                    <>
                        <div className="flex gap-2">
                            <Input value={value} onChange={(e) => setValue(e.target.value)} placeholder="www.yourbusiness.in" spellCheck={false}
                                   aria-label="Your domain" onKeyDown={(e) => e.key === "Enter" && value.trim() && call("add", `/api/sites/${site.id}/domain`, { method: "PUT", json: { domain: value } })} />
                            <Button variant="primary" disabled={!value.trim() || busy === "add"}
                                    onClick={() => call("add", `/api/sites/${site.id}/domain`, { method: "PUT", json: { domain: value } })}>
                                {busy === "add" ? "Adding…" : "Connect"}
                            </Button>
                        </div>
                        <p className="mt-1.5 text-[12px] text-stone-500">Use the www address. We&apos;ll show you the two records to add at GoDaddy or wherever you bought the domain.</p>
                    </>
                ) : (
                    <div className="space-y-4">
                        <div className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4">
                            <div className="min-w-0">
                                <p className="text-sm font-medium truncate">{d.name}</p>
                                <div className="mt-0.5"><Status tone={DOMAIN_STATUS[d.status].tone}>{DOMAIN_STATUS[d.status].label}</Status></div>
                            </div>
                            <div className="sm:ml-auto flex gap-2">
                                {d.status !== "active" && (
                                    <Button size="sm" onClick={() => call("check", `/api/sites/${site.id}/domain/check`, { method: "POST" })} disabled={!!busy}>
                                        <RefreshCw size={13} className={busy === "check" ? "animate-spin" : ""} /> Check now
                                    </Button>
                                )}
                                <Button size="sm" variant="ghost" onClick={() => call("remove", `/api/sites/${site.id}/domain`, { method: "DELETE" })} disabled={!!busy}>
                                    Remove
                                </Button>
                            </div>
                        </div>
                        {d.status !== "active" && d.error && <p className="text-[13px] text-stone-600">{d.error}{d.checked_at ? ` Checked ${timeAgo(d.checked_at)}.` : ""}</p>}
                        {d.status !== "active" && (
                            <>
                                <div className="rounded-md border border-line overflow-x-auto">
                                    <table className="w-full text-[13px]">
                                        <thead className="bg-stone-50 text-stone-500">
                                            <tr><th className="text-left font-medium px-3 py-2">Type</th><th className="text-left font-medium px-3 py-2">Name (Host)</th><th className="text-left font-medium px-3 py-2">Value</th></tr>
                                        </thead>
                                        <tbody>
                                            {d.records.map((r) => (
                                                <tr key={r.type} className="border-t border-line align-top">
                                                    <td className="px-3 py-2.5 font-medium">{r.type}</td>
                                                    <td className="px-3 py-2.5"><CopyText text={r.host} /></td>
                                                    <td className="px-3 py-2.5"><CopyText text={r.value} /></td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                                <details className="rounded-md border border-line px-4 py-3 group">
                                    <summary className="text-[13px] font-medium cursor-pointer select-none">How to add these at GoDaddy</summary>
                                    <ol className="mt-3 space-y-2 text-[13px] text-stone-600 list-decimal pl-5 leading-relaxed">
                                        <li>Sign in to GoDaddy, open <b>My Products</b>, and choose <b>DNS</b> next to {d.apex}.</li>
                                        <li>Choose <b>Add New Record</b>. Type <b>CNAME</b>, Name <b>{d.records[0].host}</b>, Value <b>{d.records[0].value}</b>, TTL 1 hour. If a {d.records[0].host} record already exists, edit it instead (a name can have only one).</li>
                                        <li>Add another record. Type <b>TXT</b>, Name <b>{d.records[1].host}</b>, Value <b>{d.records[1].value}</b>.</li>
                                        <li>Save, come back here and choose <b>Check now</b>. Records usually show up within minutes, sometimes up to a few hours. We also check every few minutes.</li>
                                    </ol>
                                    <p className="mt-3 text-[13px] text-stone-600 leading-relaxed">
                                        To send people who type {d.apex} to your site as well: in GoDaddy&apos;s DNS page, open <b>Forwarding</b>, add a
                                        domain forward to <b>https://{d.name}</b>, and choose <b>Permanent (301)</b>.
                                    </p>
                                </details>
                            </>
                        )}
                        {d.status === "active" && d.url && (
                            <p className="text-[13px] text-stone-600">
                                Live at <a href={d.url} target="_blank" rel="noopener noreferrer" className="text-plum hover:underline">{d.name}</a>, with HTTPS renewed for you.
                                Forward {d.apex} to it at your registrar so both addresses work.
                            </p>
                        )}
                    </div>
                )}
                {error && <p role="alert" className="mt-2 text-[13px] text-signal">{error}</p>}
            </div>
        </Card>
    );
}

/* ---------- history ---------- */
function History({ site, onChange }: { site: Site; onChange: (s: Site) => void }) {
    const toast = useToast();
    const [promoting, setPromoting] = useState<string | null>(null);
    const deploys = site.deploys ?? [];
    const promote = async (d: Deploy) => {
        setPromoting(d.id);
        try {
            onChange(await apiJson<Site>(`/api/sites/${site.id}/deploys/${d.id}/promote`, { method: "POST" }));
            toast("That version is live now.");
        } catch (e) {
            toast((e as Error).message);
        } finally {
            setPromoting(null);
        }
    };
    return (
        <Card>
            <div className="px-5 pt-4 pb-3">
                <h2 className="text-[15px] font-semibold">Versions</h2>
                <p className="text-[13px] text-stone-500 mt-0.5">Every version keeps its own address. Put any of them back live in one click.</p>
            </div>
            {deploys.length === 0 ? (
                <p className="px-5 pb-5 text-[13px] text-stone-500">Nothing published yet.</p>
            ) : (
                <ul className="border-t border-line">
                    {deploys.map((d) => (
                        <li key={d.id} className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4 px-5 py-3 border-t border-line first:border-t-0">
                            <div className="min-w-0 flex-1">
                                <div className="flex items-center gap-2 flex-wrap">
                                    {d.status === "building" ? <Status tone="warn">Deploying…</Status>
                                        : d.status === "failed" ? <Status tone="bad">Failed</Status> : <Status tone="good">Ready</Status>}
                                    {d.live && <span className="inline-flex items-center h-5 px-1.5 rounded bg-plum-tint text-[11px] font-medium text-plum">Live</span>}
                                    <span className="text-[12px] text-stone-500">{SOURCE_LABEL[d.source]} · {timeAgo(d.created_at)}</span>
                                </div>
                                <p className={cn("text-[13px] mt-1 break-words", d.status === "failed" ? "text-signal" : "text-stone-600")}>
                                    {d.status === "failed" ? d.error
                                        : d.status === "building" ? "Getting your files ready…"
                                        : [d.commit_message, `${d.file_count.toLocaleString("en-IN")} files, ${formatBytes(d.total_bytes)}`, d.note].filter(Boolean).join(" · ")}
                                </p>
                            </div>
                            {d.status === "ready" && (
                                <div className="flex gap-2 shrink-0">
                                    {d.preview_url && (
                                        <a href={d.preview_url} target="_blank" rel="noopener noreferrer"
                                           className="inline-flex items-center gap-1 h-8 px-3 rounded-md border border-line-strong bg-white text-[13px] font-medium hover:bg-stone-50">
                                            View <ExternalLink size={12} />
                                        </a>
                                    )}
                                    {!d.live && <Button size="sm" onClick={() => promote(d)} disabled={promoting === d.id}>{promoting === d.id ? "Switching…" : "Make live"}</Button>}
                                </div>
                            )}
                        </li>
                    ))}
                </ul>
            )}
        </Card>
    );
}

/* ---------- side: assistant, settings, delete ---------- */
function AssistantCard({ site, onChange }: { site: Site; onChange: (s: Site) => void }) {
    const toast = useToast();
    const [bots, setBots] = useState<Bot[] | null>(null);
    useEffect(() => { apiJson<Bot[]>("/api/bots").then(setBots).catch(() => setBots([])); }, []);
    const save = async (botId: string) => {
        try {
            onChange(await apiJson<Site>(`/api/sites/${site.id}`, { method: "PATCH", json: { bot_id: botId } }));
            toast(botId ? "Your assistant now appears on every page." : "The assistant was removed from the site.");
        } catch (e) { toast((e as Error).message); }
    };
    return (
        <Card className="p-5">
            <h2 className="text-[15px] font-semibold">Assistant on this site</h2>
            <p className="text-[13px] text-stone-500 mt-0.5">Adds your assistant&apos;s chat button to every page. No code needed.</p>
            {bots === null ? <Skeleton className="h-9 mt-3" /> : bots.length === 0 ? (
                <p className="text-[13px] text-stone-600 mt-3">Create an assistant first, from <Link href="/dashboard" className="text-plum hover:underline">Assistants</Link>.</p>
            ) : (
                <Select className="mt-3 w-full" value={site.bot_id ?? ""} onChange={(e) => save(e.target.value)} aria-label="Assistant on this site">
                    <option value="">No assistant</option>
                    {bots.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
                </Select>
            )}
        </Card>
    );
}

function SettingsCard({ site, onChange }: { site: Site; onChange: (s: Site) => void }) {
    const toast = useToast();
    const [name, setName] = useState(site.name);
    const [slug, setSlug] = useState(site.slug);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);
    useEffect(() => { setName(site.name); setSlug(site.slug); }, [site.name, site.slug]);
    const dirty = name.trim() !== site.name || slug !== site.slug;
    const patch = async (body: object, message: string) => {
        setBusy(true);
        setError(null);
        try {
            onChange(await apiJson<Site>(`/api/sites/${site.id}`, { method: "PATCH", json: body }));
            toast(message);
        } catch (e) {
            setError((e as Error).message);
        } finally {
            setBusy(false);
        }
    };
    const domain = hostOf(site.url).replace(/^[^.]+\./, "");
    return (
        <Card className="p-5 space-y-4">
            <h2 className="text-[15px] font-semibold">Settings</h2>
            <Field label="Name" htmlFor="set-name">
                <Input id="set-name" value={name} maxLength={80} onChange={(e) => setName(e.target.value)} />
            </Field>
            <Field label="Free address" htmlFor="set-slug" hint={slug !== site.slug ? "The old address stops working when you save." : `${slug}.${domain}`}>
                <Input id="set-slug" value={slug} maxLength={40} spellCheck={false} onChange={(e) => setSlug(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ""))} />
            </Field>
            {error && <p role="alert" className="text-[13px] text-signal">{error}</p>}
            <Button size="sm" onClick={() => patch({ name: name.trim(), slug }, "Saved.")} disabled={!dirty || busy || !name.trim()}>Save</Button>
            <div className="pt-4 border-t border-line">
                <Field label="Pages that don't exist" htmlFor="set-spa"
                       hint="For single-page apps (React, Vue) that handle their own addresses, show the home page instead of a 404.">
                    <Select id="set-spa" className="w-full" value={site.spa} onChange={(e) => patch({ spa: e.target.value }, "Saved.")}>
                        <option value="auto">Decide for me</option>
                        <option value="on">Show the home page (single-page app)</option>
                        <option value="off">Show a &ldquo;not found&rdquo; page</option>
                    </Select>
                </Field>
            </div>
        </Card>
    );
}

function DeleteCard({ site }: { site: Site }) {
    const router = useRouter();
    const toast = useToast();
    const [open, setOpen] = useState(false);
    const [busy, setBusy] = useState(false);
    const remove = async () => {
        setBusy(true);
        try {
            await apiJson(`/api/sites/${site.id}`, { method: "DELETE" });
            router.push("/dashboard/deployments");
        } catch (e) {
            toast((e as Error).message);
            setBusy(false);
        }
    };
    return (
        <Card className="p-5">
            <h2 className="text-[15px] font-semibold">Delete website</h2>
            <p className="text-[13px] text-stone-500 mt-0.5">Takes it offline now. You can restore it for 30 days.</p>
            <Button size="sm" variant="danger" className="mt-3" onClick={() => setOpen(true)}><Trash2 size={13} /> Delete</Button>
            <Dialog open={open} onClose={() => setOpen(false)} title={`Delete ${site.name}?`}
                    description={`${hostOf(site.url)}${site.domain ? ` and ${site.domain.name}` : ""} will stop working right away. You can restore the site from Deployments for 30 days; the custom domain would need to be connected again.`}
                    footer={<>
                        <Button variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
                        <Button variant="danger" onClick={remove} disabled={busy}>{busy ? "Deleting…" : "Delete website"}</Button>
                    </>}>
                <span />
            </Dialog>
        </Card>
    );
}
