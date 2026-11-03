"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { Button, Card, Dialog, EmptyState, Input, Notice, SectionHeader, Select, Skeleton, Status, Switch, useToast } from "@/components/ui";
import { apiJson } from "@/lib/api";
import { STATUS, igMeLink, type IgAccount, type IgOverview } from "@/lib/instagram";
import { useApi } from "@/lib/useApi";
import { formatDate } from "@/lib/voice/api";

export default function InstagramSettingsPage() {
    return <Suspense><Settings /></Suspense>;
}

/** Connecting an Instagram professional account (Instagram sends you back here to finish), and which assistant answers it. */
function Settings() {
    const toast = useToast();
    const router = useRouter();
    const pathname = usePathname();
    const params = useSearchParams();
    const overview = useApi<IgOverview>("/api/instagram");
    const bots = useApi<{ id: string; name: string }[]>("/api/bots");
    const [busy, setBusy] = useState(false);
    const [leaving, setLeaving] = useState<IgAccount | null>(null);
    const finishing = useRef(false);
    const { reload } = overview;

    useEffect(() => {  // back from Instagram: ?code=&state= to finish, or ?error= when they said no
        const code = params.get("code"), state = params.get("state"), error = params.get("error");
        if (finishing.current || (!code && !error)) return;
        finishing.current = true;
        if (error) {
            toast("Nothing was connected: Instagram's permission wasn't given.");
            router.replace(pathname);
            return;
        }
        setBusy(true);
        apiJson<IgAccount>("/api/instagram/connect/finish", { method: "POST", json: { code, state } })
            .then((a) => {
                toast(a.missing?.length ? `Connected @${a.username}, but messages weren't allowed. Connect again and allow everything.` : `Connected @${a.username}.`);
                return reload();
            })
            .catch((e) => toast((e as Error).message))
            .finally(() => { setBusy(false); router.replace(pathname); });
    }, [params, pathname, router, toast, reload]);

    const run = async (work: () => Promise<unknown>, done?: string) => {
        setBusy(true);
        try {
            await work();
            await reload();
            if (done) toast(done);
        } catch (e) {
            toast((e as Error).message);
        } finally {
            setBusy(false);
        }
    };
    const connect = () => run(async () => {
        const r = await apiJson<{ url: string }>("/api/instagram/connect", { method: "POST" });
        window.location.assign(r.url);
    });
    const change = (a: IgAccount, json: Record<string, unknown>, done = "Saved") => run(() => apiJson(`/api/instagram/accounts/${a.id}`, { method: "PATCH", json }), done);

    if (overview.error) return <p className="text-sm text-signal">{overview.error}</p>;
    if (!overview.data) return <Skeleton className="h-48" />;
    const o = overview.data;
    return (
        <>
            <SectionHeader title="Instagram account"
                           description="Your Instagram professional account, and the assistant that answers its messages."
                           action={o.available ? <Button size="sm" variant={o.accounts.length ? "secondary" : "primary"} disabled={busy} onClick={connect}>
                               Connect Instagram</Button> : undefined} />
            {!o.available && (
                <Notice title="Not available yet">
                    Instagram connects once Nimmi&apos;s Instagram app is approved by Meta. Nothing for you to do until then.
                </Notice>
            )}
            {o.accounts.length === 0 ? (
                <Card>
                    <EmptyState title="No account connected"
                                body="You'll sign in to Instagram and allow Nimmi to read and answer your messages. It needs a professional account (business or creator)." />
                </Card>
            ) : (
                <div className="space-y-4">
                    {o.accounts.map((a) => (
                        <Card key={a.id} className="p-5">
                            <div className="flex flex-wrap items-start justify-between gap-3">
                                <div className="min-w-0">
                                    <p className="text-sm font-medium">@{a.username ?? a.ig_id}</p>
                                    <p className="text-[13px] text-stone-500">{[a.name, a.created_at ? `connected ${formatDate(a.created_at)}` : null].filter(Boolean).join(" · ")}</p>
                                </div>
                                <Status tone={STATUS[a.status]?.tone ?? "neutral"}>{STATUS[a.status]?.text ?? a.status}</Status>
                            </div>
                            {a.status !== "connected" && (
                                <div className="flex flex-wrap items-center gap-3 mt-3">
                                    <p className="text-[13px] text-stone-600 flex-1 min-w-48">{a.status_detail}</p>
                                    {o.available && <Button size="sm" variant="primary" disabled={busy} onClick={connect}>Connect again</Button>}
                                </div>
                            )}
                            <div className="grid sm:grid-cols-2 gap-4 mt-4">
                                <label className="block">
                                    <span className="text-xs text-stone-500">Answered by</span>
                                    <Select className="mt-1" aria-label={`Assistant for @${a.username}`} value={a.bot_id} disabled={busy}
                                            onChange={(e) => change(a, { bot_id: e.target.value })}>
                                        <option value="">Your first assistant</option>
                                        {(bots.data ?? []).map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
                                    </Select>
                                </label>
                                <div className="flex items-center justify-between gap-4 sm:pt-5">
                                    <span className="text-sm">The assistant answers messages</span>
                                    <Switch label={`The assistant answers messages to @${a.username}`} checked={a.ai_enabled} disabled={busy}
                                            onChange={(v) => change(a, { ai_enabled: v }, v ? "The assistant answers new messages." : "Your team answers from the Inbox.")} />
                                </div>
                            </div>
                            {a.status === "connected" && a.comments_allowed === false && (
                                <p className="text-[13px] text-stone-600 mt-3">Replies to comments weren&apos;t allowed when this account was connected. To use comment rules, connect again and allow everything.</p>
                            )}
                            {a.status === "connected" && a.username && <ChatLink username={a.username} hasQuestions={!!a.profile?.ice_breakers?.length} />}
                            <div className="flex justify-end mt-4">
                                <Button size="sm" variant="ghost" disabled={busy} onClick={() => setLeaving(a)}>Disconnect</Button>
                            </div>
                        </Card>
                    ))}
                </div>
            )}
            <Dialog open={!!leaving} onClose={() => setLeaving(null)} title={`Disconnect @${leaving?.username ?? ""}?`}
                    description="The assistant stops answering, and Nimmi forgets this account's sign-in. Its chats stay in the Inbox and Leads."
                    footer={<>
                        <Button variant="ghost" onClick={() => setLeaving(null)}>Cancel</Button>
                        <Button variant="primary" disabled={busy} onClick={() => { const a = leaving; setLeaving(null); if (a) run(() => apiJson(`/api/instagram/accounts/${a.id}`, { method: "DELETE" }), "Disconnected"); }}>Disconnect</Button>
                    </>}>
                <p className="text-[13px] text-stone-600">To connect it again later, use Connect Instagram on this page.</p>
            </Dialog>
        </>
    );
}

/** An ig.me link that opens a chat with the account. The ref says where the person found it, and shows on their lead (Leads: where they came from). */
function ChatLink({ username, hasQuestions }: { username: string; hasQuestions: boolean }) {
    const toast = useToast();
    const [ref, setRef] = useState("");
    const link = igMeLink(username, ref);
    const copy = async () => {
        try {
            await navigator.clipboard.writeText(link);
            toast("Link copied");
        } catch {
            toast("Couldn't copy: select the link and copy it.");
        }
    };
    return (
        <div className="mt-4 pt-4 border-t border-line">
            <p className="text-sm font-medium">Link to a chat</p>
            <p className="text-[13px] text-stone-500 mt-0.5">
                For your bio, a QR code, a story or another website: it opens a chat with you. Name where you&apos;ll share it, and their lead shows where they came from.
            </p>
            <div className="flex flex-col sm:flex-row gap-2 mt-2">
                <Input aria-label="Where you'll share the link" className="sm:w-56" maxLength={40} placeholder="diwali-poster" value={ref}
                       onChange={(e) => setRef(e.target.value.replace(/[^A-Za-z0-9_=-]/g, ""))} />
                <div className="flex flex-1 gap-2 min-w-0">
                    <Input aria-label="Chat link" readOnly value={link} onFocus={(e) => e.target.select()} className="font-mono text-[13px]" />
                    <Button size="sm" onClick={copy}>Copy</Button>
                </div>
            </div>
            {ref && !hasQuestions && (
                <p className="text-xs text-stone-500 mt-1.5">
                    For someone who has never written to you, Instagram passes the name only when they tap one of your questions. Add questions on the{" "}
                    <Link href="/dashboard/instagram/assistant" className="text-plum hover:underline">Assistant tab</Link>.
                </p>
            )}
        </div>
    );
}
