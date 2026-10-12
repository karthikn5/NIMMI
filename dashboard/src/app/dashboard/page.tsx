"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, ExternalLink, Plus, Search, Trash2 } from "lucide-react";
import AppHeader from "@/components/AppHeader";
import {
    Button, Card, Dialog, EmptyState, Input, Segmented, Skeleton, Status, ToastProvider, cn, useToast,
} from "@/components/ui";
import { activeOwnerId, apiFetch, apiJson, currentUserId, getWorkspace } from "@/lib/api";
import { useWaitingCount } from "@/lib/liveChat";

type Bot = {
    id: string;
    name: string;
    status: "Active" | "Expired";
    plan: string;
    expiry: string;
    days_remaining: number;
};

type Filter = "all" | "active" | "unplanned";

export default function DashboardPage() {
    return (
        <ToastProvider>
            <Dashboard />
        </ToastProvider>
    );
}

function greeting() {
    const h = new Date().getHours();
    return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
}

const capitalise = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

/** Backend plan names vary ("1 Month", "6 Month Plan"); always end in one "plan". */
const planLabel = (plan: string) => (/plan$/i.test(plan.trim()) ? plan.trim() : `${plan.trim()} plan`);

function readCache<T>(key: string): T | null {
    try {
        const raw = localStorage.getItem(key);
        return raw ? (JSON.parse(raw) as T) : null;
    } catch {
        return null;
    }
}

function Dashboard() {
    const router = useRouter();
    const toast = useToast();
    const [userId, setUserId] = useState<string | null>(null);
    const [bots, setBots] = useState<Bot[] | null>(null);
    const [fullName, setFullName] = useState("");
    const [firstName, setFirstName] = useState("");
    const waiting = useWaitingCount();
    const [openQuestions, setOpenQuestions] = useState<number | null>(null);
    const [loadError, setLoadError] = useState(false);
    const [canManage, setCanManage] = useState(true);

    const [filter, setFilter] = useState<Filter>("all");
    const [query, setQuery] = useState("");
    const [creating, setCreating] = useState(false);
    const [deleting, setDeleting] = useState<Bot | null>(null);

    const fetchBots = useCallback(async (uid: string) => {
        try {
            const data = await apiJson<Bot[]>("/api/bots");
            setBots(data);
            setLoadError(false);
            try { localStorage.setItem(`bots_${uid}`, JSON.stringify(data)); } catch { /* ignore */ }
        } catch {
            setLoadError(true);
            setBots((prev) => prev ?? []);
        }
    }, []);

    useEffect(() => {
        const uid = currentUserId();
        if (!uid) {
            router.push("/auth/signup");
            return;
        }
        const owner = activeOwnerId() || uid;
        setUserId(owner);

        // Show cached data instantly, then refresh.
        const cached = readCache<Bot[]>(`bots_${owner}`);
        if (cached) setBots(cached);
        const cachedName = readCache<string>(`nimmi_user_first_name`);
        if (cachedName) setFirstName(cachedName);

        fetchBots(owner);
        apiJson<{ counts: { open: number } }>("/api/questions?status=open")
            .then((q) => setOpenQuestions(q.counts.open))
            .catch(() => setOpenQuestions(null));
        if (getWorkspace()) {
            apiJson<{ owner_id: string; role: string }[]>("/api/team/workspaces")
                .then((ws) => setCanManage(ws.find((w) => w.owner_id === owner)?.role !== "agent"))
                .catch(() => {});
        }
        apiJson<{ name: string }>("/api/auth/profile")
            .then((p) => {
                if (!p?.name) return;
                const first = capitalise(p.name.trim().split(" ")[0]);
                setFullName(p.name);
                setFirstName(first);
                try {
                    localStorage.setItem("nimmi_user_name", p.name);
                    localStorage.setItem("nimmi_user_first_name", JSON.stringify(first));
                } catch { /* ignore */ }
            })
            .catch(() => {});
    }, [router, fetchBots]);

    const counts = useMemo(() => {
        const list = bots ?? [];
        const active = list.filter((b) => b.status === "Active").length;
        return { all: list.length, active, unplanned: list.length - active };
    }, [bots]);

    const rows = useMemo(() => {
        const q = query.trim().toLowerCase();
        return (bots ?? []).filter((b) =>
            (filter === "all" || (filter === "active" ? b.status === "Active" : b.status !== "Active")) &&
            (!q || b.name.toLowerCase().includes(q) || b.id.startsWith(q)),
        );
    }, [bots, filter, query]);

    const nextRenewal = useMemo(() => {
        return (bots ?? [])
            .filter((b) => b.status === "Active")
            .sort((a, b) => a.days_remaining - b.days_remaining)[0] ?? null;
    }, [bots]);

    const removeBot = async (bot: Bot) => {
        try {
            const res = await apiFetch(`/api/bots/${bot.id}`, { method: "DELETE" });
            if (!res.ok) throw new Error();
            setBots((prev) => (prev ?? []).filter((b) => b.id !== bot.id));
            toast(`Deleted ${bot.name}`);
        } catch {
            toast("Couldn't delete the assistant. Try again.");
        }
        setDeleting(null);
    };

    return (
        <div className="min-h-screen bg-paper text-ink">
            <AppHeader userName={fullName} />

            <main className="max-w-6xl mx-auto px-4 sm:px-6 py-8 pb-24">
                <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
                    <div>
                        <h1 className="text-2xl font-semibold tracking-tight">Assistants</h1>
                        <p className="text-sm text-stone-500 mt-1">
                            {firstName ? `${greeting()}, ${firstName}. ` : ""}Build, train and publish the assistants on your website.
                        </p>
                    </div>
                    {canManage && (
                        <Button variant="primary" onClick={() => setCreating(true)} className="self-start sm:self-auto">
                            <Plus size={15} /> New assistant
                        </Button>
                    )}
                </div>

                {bots === null ? (
                    <Skeleton className="h-[108px] mt-6" />
                ) : (
                    <Card className="mt-6 grid sm:grid-cols-2 lg:grid-cols-4 [&>*]:border-line">
                        <div className="p-5">
                            <p className="text-[13px] text-stone-500">Assistants</p>
                            <p className="text-[28px] leading-none font-semibold tracking-tight tabular-nums mt-3">{counts.all}</p>
                            <p className="text-xs text-stone-500 mt-2">{counts.active} on an active plan</p>
                        </div>
                        <Link href="/dashboard/live-chat" className="group p-5 border-t sm:border-t-0 sm:border-l hover:bg-stone-50 transition-colors">
                            <p className="text-[13px] text-stone-500">Waiting for a person</p>
                            <p className="text-[28px] leading-none font-semibold tracking-tight tabular-nums mt-3 flex items-center gap-2.5">
                                {waiting}
                                {waiting > 0 && <span className="h-2 w-2 rounded-full bg-signal" aria-label="Needs attention" />}
                            </p>
                            <p className="text-xs text-plum mt-2 inline-flex items-center gap-1">{waiting > 0 ? "Reply in live chat" : "Open live chat"} <ArrowRight size={12} className="group-hover:translate-x-0.5 transition-transform" /></p>
                        </Link>
                        <Link href="/dashboard/questions" className="group p-5 border-t lg:border-t-0 lg:border-l hover:bg-stone-50 transition-colors">
                            <p className="text-[13px] text-stone-500">Questions to answer</p>
                            <p className="text-[28px] leading-none font-semibold tracking-tight tabular-nums mt-3">{openQuestions ?? "–"}</p>
                            <p className="text-xs text-plum mt-2 inline-flex items-center gap-1">
                                {openQuestions ? "Teach your assistants" : "See questions"} <ArrowRight size={12} className="group-hover:translate-x-0.5 transition-transform" />
                            </p>
                        </Link>
                        <Link href="/dashboard/billing" className="group p-5 border-t lg:border-t-0 sm:border-l hover:bg-stone-50 transition-colors">
                            <p className="text-[13px] text-stone-500">Next plan renewal</p>
                            {nextRenewal ? (
                                <>
                                    <p className="text-[28px] leading-none font-semibold tracking-tight tabular-nums mt-3">
                                        {nextRenewal.days_remaining} <span className="text-sm font-normal text-stone-500">days</span>
                                    </p>
                                    <p className="text-xs text-stone-500 mt-2 truncate">{nextRenewal.name} · {nextRenewal.expiry}</p>
                                </>
                            ) : (
                                <>
                                    <p className="text-[28px] leading-none font-semibold tracking-tight mt-3 text-stone-300">–</p>
                                    <p className="text-xs text-plum mt-2 inline-flex items-center gap-1">See plans <ArrowRight size={12} className="group-hover:translate-x-0.5 transition-transform" /></p>
                                </>
                            )}
                        </Link>
                    </Card>
                )}

                <section className="mt-10" aria-labelledby="assistants-heading">
                    <h2 id="assistants-heading" className="sr-only">Your assistants</h2>

                    {(bots?.length ?? 0) > 0 && (
                        <div className="flex flex-col sm:flex-row sm:items-center gap-3 mb-4">
                            <Segmented
                                label="Filter assistants"
                                value={filter}
                                onChange={setFilter}
                                options={[
                                    { value: "all", label: `All ${counts.all}` },
                                    { value: "active", label: `Active ${counts.active}` },
                                    { value: "unplanned", label: `No plan ${counts.unplanned}` },
                                ]}
                            />
                            {counts.all > 5 && (
                                <div className="relative sm:ml-auto sm:w-64">
                                    <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-stone-400" aria-hidden />
                                    <Input aria-label="Search assistants" placeholder="Search by name or ID" className="pl-8" value={query} onChange={(e) => setQuery(e.target.value)} />
                                </div>
                            )}
                        </div>
                    )}

                    <Card>
                        {bots === null ? (
                            <div className="p-5 space-y-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-12" />)}</div>
                        ) : loadError && bots.length === 0 ? (
                            <EmptyState
                                title="Couldn't load your assistants"
                                body="Check your connection and try again."
                                action={<Button size="sm" onClick={() => userId && fetchBots(userId)}>Try again</Button>}
                            />
                        ) : bots.length === 0 ? (
                            <EmptyState
                                title="Create your first assistant"
                                body="Give it a name, then train it on your website or documents. It can start answering visitors in minutes."
                                action={<Button variant="primary" onClick={() => setCreating(true)}><Plus size={15} /> New assistant</Button>}
                            />
                        ) : rows.length === 0 ? (
                            <EmptyState
                                title="No assistants match"
                                body="Try another filter or search."
                                action={<Button size="sm" onClick={() => { setFilter("all"); setQuery(""); }}>Show all</Button>}
                            />
                        ) : (
                            <ul>
                                {rows.map((b) => <BotRow key={b.id} bot={b} canManage={canManage} onDelete={() => setDeleting(b)} />)}
                            </ul>
                        )}
                    </Card>
                </section>

                <Card className="mt-6 flex flex-col sm:flex-row sm:items-center gap-3 px-5 py-4">
                    <div>
                        <p className="text-sm font-medium">Voice calls</p>
                        <p className="text-[13px] text-stone-500 mt-0.5">Let your assistants answer phone calls and call back people who ask, in English, Tamil, Hindi and more.</p>
                    </div>
                    <Link href="/dashboard/voice" className="sm:ml-auto shrink-0">
                        <Button size="sm">Set up voice</Button>
                    </Link>
                </Card>
            </main>

            <NewAssistantDialog open={creating} onClose={() => setCreating(false)} userId={userId} />

            <Dialog
                open={!!deleting}
                onClose={() => setDeleting(null)}
                title={`Delete ${deleting?.name ?? "assistant"}?`}
                description="Its settings, flow, knowledge and chat history are removed. This can't be undone."
                footer={<>
                    <Button variant="ghost" onClick={() => setDeleting(null)}>Cancel</Button>
                    <Button variant="danger" onClick={() => deleting && removeBot(deleting)}>Delete assistant</Button>
                </>}
            >
                {deleting?.status === "Active" ? (
                    <p className="text-[13px] text-amber-700">It has {deleting.days_remaining} days left on its {planLabel(deleting.plan)}. That time is lost when it&apos;s deleted.</p>
                ) : (
                    <p className="text-[13px] text-stone-600">The chat widget stops working on any site where it&apos;s installed.</p>
                )}
            </Dialog>
        </div>
    );
}

function BotRow({ bot, canManage, onDelete }: { bot: Bot; canManage: boolean; onDelete: () => void }) {
    const active = bot.status === "Active";
    const endingSoon = active && bot.days_remaining <= 7;

    return (
        <li className="group relative grid grid-cols-[minmax(0,1fr)_auto] md:grid-cols-[minmax(0,1.3fr)_9.5rem_minmax(0,1.2fr)_11.5rem] md:items-center gap-x-6 gap-y-1.5 px-5 py-3.5 border-t border-line first:border-t-0 hover:bg-stone-50 transition-colors">
            <div className="min-w-0">
                <Link
                    href={`/dashboard/builder/${bot.id}`}
                    className="text-sm font-medium truncate block after:absolute after:inset-0 focus-visible:outline-none focus-visible:after:outline-2 focus-visible:after:-outline-offset-2 focus-visible:after:outline-plum"
                >
                    {bot.name}
                </Link>
                <p className="text-xs text-stone-400 mt-0.5 font-mono">{bot.id.slice(0, 8)}</p>
            </div>

            <div className="row-start-2 md:row-start-auto">
                {active ? <Status tone="good">Active</Status> : <Status tone="neutral">No active plan</Status>}
            </div>

            <div className={cn("col-start-1 md:col-start-auto text-[13px] min-w-0", !active && "hidden md:block")}>
                {active ? (
                    <>
                        <p className="text-stone-700 truncate">{planLabel(bot.plan)}</p>
                        <p className={cn("text-xs mt-0.5", endingSoon ? "text-amber-700" : "text-stone-500")}>
                            Until {bot.expiry} · {bot.days_remaining} {bot.days_remaining === 1 ? "day" : "days"} left
                        </p>
                    </>
                ) : (
                    <p className="text-stone-500">Paused on your site until it has a plan</p>
                )}
            </div>

            {/* Actions sit above the row's stretched link. */}
            <div className="relative z-10 col-start-2 row-start-1 row-span-3 md:col-start-4 md:row-start-auto md:row-span-1 self-start md:self-center flex items-center justify-end gap-1">
                {!active && canManage && (
                    <Link href={`/dashboard/billing?bot=${bot.id}`} className="mr-1">
                        <Button size="sm">Choose plan</Button>
                    </Link>
                )}
                <a
                    href={`/demo/${bot.id}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    aria-label={`Preview ${bot.name} in a new tab`}
                    title="Preview"
                    className="p-2 rounded-md text-stone-400 hover:text-ink hover:bg-stone-100 focus-visible:outline-2 focus-visible:outline-plum"
                >
                    <ExternalLink size={15} />
                </a>
                {canManage && <button
                    onClick={onDelete}
                    aria-label={`Delete ${bot.name}`}
                    title="Delete"
                    className="p-2 rounded-md text-stone-400 hover:text-signal hover:bg-red-50 focus-visible:outline-2 focus-visible:outline-plum"
                >
                    <Trash2 size={15} />
                </button>}
            </div>
        </li>
    );
}

type Template = { id: string; name: string; summary: string; fields: string[]; goal: string };

function NewAssistantDialog({ open, onClose, userId }: { open: boolean; onClose: () => void; userId: string | null }) {
    const router = useRouter();
    const [name, setName] = useState("");
    const [template, setTemplate] = useState("");
    const [templates, setTemplates] = useState<Template[] | null>(null);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");

    useEffect(() => {
        if (!open) return;
        setName(""); setError(""); setTemplate("");
        if (!templates) apiJson<Template[]>("/api/bots/templates").then(setTemplates).catch(() => setTemplates([]));
    }, [open, templates]);

    const create = async () => {
        const clean = name.trim();
        if (!clean) return setError("Give your assistant a name.");
        if (!userId) return;
        setBusy(true);
        setError("");
        try {
            const data = await apiJson<{ id: string }>("/api/bots/create", { method: "POST", json: { name: clean, template: template || undefined } });
            router.push(`/dashboard/builder/${data.id}`);
        } catch (e) {
            setError((e as Error).message || "Couldn't create the assistant.");
            setBusy(false);
        }
    };

    const chosen = templates?.find((t) => t.id === template);
    const options = [{ id: "", name: "Start blank", summary: "Write its instructions and knowledge yourself." }, ...(templates ?? [])];

    return (
        <Dialog
            open={open}
            onClose={onClose}
            title="New assistant"
            description="Start from your industry to get instructions, a knowledge sheet to fill in, and what to ask callers."
            footer={<>
                <Button variant="ghost" onClick={onClose}>Cancel</Button>
                <Button variant="primary" onClick={create} disabled={busy}>{busy ? "Creating…" : "Create and open builder"}</Button>
            </>}
        >
            <label htmlFor="bot-name" className="text-sm font-medium">Name</label>
            <Input
                id="bot-name"
                autoFocus
                maxLength={60}
                placeholder="e.g. Admissions Desk"
                className="mt-1.5"
                value={name}
                onChange={(e) => setName(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && create()}
                aria-invalid={!!error}
                aria-describedby={error ? "bot-name-error" : undefined}
            />
            {error && <p id="bot-name-error" className="text-[13px] text-signal mt-2">{error}</p>}

            <p className="text-sm font-medium mt-4">Start from</p>
            {templates === null ? <Skeleton className="h-40 mt-1.5" /> : (
                <div role="radiogroup" aria-label="Start from" className="mt-1.5 max-h-64 overflow-y-auto rounded-md border border-line divide-y divide-line">
                    {options.map((t) => (
                        <button key={t.id || "blank"} type="button" role="radio" aria-checked={template === t.id} onClick={() => setTemplate(t.id)}
                                className={cn("w-full text-left px-3 py-2.5 transition-colors focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-plum",
                                              template === t.id ? "bg-plum-tint" : "hover:bg-stone-50")}>
                            <span className={cn("block text-[13px]", template === t.id ? "font-medium text-plum" : "text-ink")}>{t.name}</span>
                            <span className="block text-xs text-stone-500">{t.summary}</span>
                        </button>
                    ))}
                </div>
            )}
            {chosen && (
                <p className="text-xs text-stone-500 mt-2">
                    Collects {chosen.fields.slice(0, 4).join(", ")}{chosen.fields.length > 4 ? " and more" : ""}. You can change everything later.
                </p>
            )}
        </Dialog>
    );
}
