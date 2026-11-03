"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Plus, Trash2 } from "lucide-react";
import { Button, Card, Dialog, EmptyState, Input, Notice, PhraseInput, SectionHeader, Skeleton, Status, Switch, Textarea, cn, useToast } from "@/components/ui";
import { apiJson } from "@/lib/api";
import type { IgAccount, IgComment, IgMedia, IgOverview, IgRule } from "@/lib/instagram";
import { rupees } from "@/lib/leads";
import { useApi } from "@/lib/useApi";
import { formatWhen } from "@/lib/voice/api";

/** What the rules route takes (never the report or the dates). */
function ruleBody(r: IgRule, change: Partial<IgRule> = {}) {
    const x = { ...r, ...change };
    return { account_id: x.account_id, name: x.name, media_ids: x.media_ids, keywords: x.keywords, private_reply: x.private_reply, public_replies: x.public_replies, enabled: x.enabled };
}

/** Instagram counts a message in bytes: a Tamil or Hindi letter takes three. */
const LIMIT = 1000;
const bytes = (text: string) => new TextEncoder().encode(text).length;

const STATE: Record<IgComment["status"], { tone: "good" | "warn" | "bad" | "neutral"; text: string }> = {
    replied: { tone: "good", text: "Replied" }, new: { tone: "warn", text: "Waiting" }, working: { tone: "warn", text: "Replying" },
    skipped: { tone: "neutral", text: "Skipped" }, failed: { tone: "bad", text: "Not sent" },
};

/** Comment rules: someone who comments with your words gets one private message, and a short public reply if you like. Nobody else gets anything. */
export default function CommentsPage() {
    const toast = useToast();
    const overview = useApi<IgOverview>("/api/instagram");
    const rules = useApi<IgRule[]>("/api/instagram/rules");
    const recent = useApi<IgComment[]>("/api/instagram/comments");
    const [editing, setEditing] = useState<IgRule | "new" | null>(null);
    const [deleting, setDeleting] = useState<IgRule | null>(null);
    const [busy, setBusy] = useState(false);

    if (overview.loading || rules.loading) return <div className="space-y-3">{[0, 1].map((i) => <Skeleton key={i} className="h-32" />)}</div>;
    if (overview.error || rules.error) return <p className="text-sm text-signal">{overview.error ?? rules.error}</p>;
    const account = overview.data?.accounts[0];
    if (!account) {
        return (
            <Card>
                <EmptyState title="Connect your account first" body="Once your Instagram account is connected, set here what happens when people comment on your posts and reels."
                            action={<Link href="/dashboard/instagram/settings" className="text-sm font-medium text-plum hover:underline">Connect Instagram</Link>} />
            </Card>
        );
    }
    const reload = async () => { await Promise.all([rules.reload(), recent.reload()]); };
    const toggle = async (r: IgRule, on: boolean) => {
        setBusy(true);
        try {
            await apiJson(`/api/instagram/rules/${r.id}`, { method: "PUT", json: ruleBody(r, { enabled: on }) });
            await reload();
            toast(on ? "On: comments with its words get a reply." : "Off.");
        } catch (e) {
            toast((e as Error).message);
        } finally {
            setBusy(false);
        }
    };
    const remove = async (r: IgRule) => {
        setBusy(true);
        try {
            await apiJson(`/api/instagram/rules/${r.id}`, { method: "DELETE" });
            await reload();
        } catch (e) {
            toast((e as Error).message);
        } finally {
            setBusy(false);
        }
    };
    const names = Object.fromEntries((rules.data ?? []).map((r) => [r.id, r.name]));

    return (
        <>
            {account.comments_allowed === false && (
                <Notice title="Comments weren't allowed"
                        action={<Link href="/dashboard/instagram/settings" className="text-[13px] font-medium text-plum hover:underline">Open settings</Link>}>
                    When this account was connected, Instagram wasn&apos;t asked for comments. Connect it again and allow everything, then rules start working.
                </Notice>
            )}
            <SectionHeader title="Comment rules"
                           description="When someone comments with your words, they get one private message from you, and if you like a short public reply under their comment. Instagram allows the private message within 7 days of the comment. Only people who comment get anything."
                           action={<Button size="sm" variant="primary" onClick={() => setEditing("new")}><Plus size={14} /> New rule</Button>} />
            {(rules.data ?? []).length === 0 ? (
                <Card>
                    <EmptyState title="No rules yet" body="For example: anyone who comments “price” on your new post gets the price list in a private message, and a public “Sent you a DM!”." />
                </Card>
            ) : (
                <div className="space-y-4">
                    {rules.data!.map((r) => (
                        <Card key={r.id} className="p-5">
                            <div className="flex flex-wrap items-start justify-between gap-3">
                                <div className="min-w-0 flex-1">
                                    <p className="text-sm font-medium">{r.name}</p>
                                    <p className="text-[13px] text-stone-500 mt-0.5">
                                        {r.media_ids.length ? `${r.media_ids.length} ${r.media_ids.length === 1 ? "post" : "posts"}` : "Every post and reel"} · {r.keywords.length ? `words: ${r.keywords.join(", ")}` : "every comment"}
                                    </p>
                                </div>
                                <div className="flex items-center gap-2">
                                    <Switch label={`Rule ${r.name} on`} checked={r.enabled} disabled={busy} onChange={(v) => toggle(r, v)} />
                                    <Button size="sm" variant="ghost" onClick={() => setEditing(r)}>Edit</Button>
                                    <button type="button" aria-label={`Delete rule ${r.name}`} disabled={busy} onClick={() => setDeleting(r)} className="p-1.5 text-stone-400 hover:text-signal"><Trash2 size={15} /></button>
                                </div>
                            </div>
                            <p className="text-[13px] text-stone-700 mt-3 whitespace-pre-wrap border-l-2 border-line pl-3">{r.private_reply}</p>
                            {!!r.public_replies.length && (
                                <p className="text-xs text-stone-500 mt-1.5">
                                    {r.public_replies.length === 1 ? `Public reply: “${r.public_replies[0]}”` : `Public reply: one of ${r.public_replies.length}, such as “${r.public_replies[0]}”`}
                                </p>
                            )}
                            <dl className="grid grid-cols-3 sm:grid-cols-6 gap-3 mt-4 text-center">
                                {([["Comments", r.report.comments], ["Private replies", r.report.private_replies], ["Public replies", r.report.public_replies],
                                    ["Conversations", r.report.conversations], ["Leads", r.report.leads], ["Sales", r.report.sales]] as [string, number][]).map(([label, n]) => (
                                    <div key={label} className="rounded-md bg-stone-50 py-2">
                                        <dd className="text-lg font-semibold tabular-nums">{n}</dd>
                                        <dt className="text-[11px] text-stone-500">{label}</dt>
                                    </div>
                                ))}
                            </dl>
                            {r.report.value > 0 && <p className="text-xs text-stone-500 mt-2 text-right">Won: {rupees(r.report.value)}</p>}
                            {r.last_error && <p className="text-xs text-signal mt-2">{r.last_error}</p>}
                        </Card>
                    ))}
                </div>
            )}

            <section className="mt-8">
                <h2 className="text-[15px] font-semibold">Latest comments</h2>
                <p className="text-[13px] text-stone-500 mt-0.5 mb-3">What happened to each, newest first.</p>
                <Card>
                    {(recent.data ?? []).length === 0 ? (
                        <p className="px-5 py-4 text-[13px] text-stone-500">No comments yet.</p>
                    ) : (
                        <ul>
                            {recent.data!.map((c) => (
                                <li key={c.id} className="flex flex-wrap items-start gap-3 px-5 py-3 border-t border-line first:border-t-0">
                                    <span className="min-w-0 flex-1">
                                        <span className="block text-sm"><span className="font-medium">@{c.username ?? "someone"}</span> <span className="text-stone-600">{c.text}</span></span>
                                        <span className="block text-xs text-stone-500 mt-0.5">
                                            {[c.at ? formatWhen(c.at) : null, c.rule_id ? names[c.rule_id] : null, c.status !== "replied" ? c.why : c.public ? "with a public reply" : null].filter(Boolean).join(" · ")}
                                        </span>
                                    </span>
                                    <Status tone={STATE[c.status]?.tone ?? "neutral"}>{STATE[c.status]?.text ?? c.status}</Status>
                                </li>
                            ))}
                        </ul>
                    )}
                </Card>
            </section>

            <Dialog open={!!deleting} onClose={() => setDeleting(null)} title={`Delete “${deleting?.name ?? ""}”?`}
                    description="Comments stop getting its replies. The comments already handled stay in the list below."
                    footer={<>
                        <Button variant="ghost" onClick={() => setDeleting(null)}>Cancel</Button>
                        <Button variant="danger" disabled={busy} onClick={() => { const r = deleting; setDeleting(null); if (r) void remove(r); }}>Delete</Button>
                    </>}>
                <p className="text-[13px] text-stone-600">To pause it instead and keep its numbers, switch it off.</p>
            </Dialog>

            {editing && <RuleEditor account={account} rule={editing === "new" ? null : editing} onClose={() => setEditing(null)}
                                    onSaved={async () => { setEditing(null); await reload(); toast("Saved"); }} />}
        </>
    );
}

function RuleEditor({ account, rule, onClose, onSaved }: { account: IgAccount; rule: IgRule | null; onClose: () => void; onSaved: () => void }) {
    const toast = useToast();
    const [name, setName] = useState(rule?.name ?? "");
    const [mode, setMode] = useState<"all" | "some">(rule?.media_ids.length ? "some" : "all");
    const [picked, setPicked] = useState<string[]>(rule?.media_ids ?? []);
    const [keywords, setKeywords] = useState<string[]>(rule?.keywords ?? []);
    const [privateReply, setPrivateReply] = useState(rule?.private_reply ?? "");
    const [publics, setPublics] = useState<string[]>(rule?.public_replies ?? []);
    const [enabled, setEnabled] = useState(rule?.enabled ?? true);
    const [media, setMedia] = useState<IgMedia[] | null>(null);
    const [saving, setSaving] = useState(false);
    const room = LIMIT - bytes(privateReply.trim());
    const everything = mode === "all" && keywords.length === 0;

    useEffect(() => {
        if (mode !== "some" || media !== null) return;
        apiJson<IgMedia[]>(`/api/instagram/accounts/${account.id}/media`).then(setMedia).catch((e) => { toast((e as Error).message); setMedia([]); });
    }, [mode, media, account.id, toast]);

    const save = async () => {
        setSaving(true);
        try {
            const json = { account_id: account.id, name: name.trim(), media_ids: mode === "some" ? picked : [], keywords, private_reply: privateReply.trim(),
                           public_replies: publics.map((p) => p.trim()).filter(Boolean), enabled };
            if (bytes(json.private_reply) > LIMIT) throw new Error("The private message is too long for Instagram. Make it shorter.");
            await apiJson(rule ? `/api/instagram/rules/${rule.id}` : "/api/instagram/rules", { method: rule ? "PUT" : "POST", json });
            onSaved();
        } catch (e) {
            toast((e as Error).message);
        } finally {
            setSaving(false);
        }
    };

    return (
        <Dialog open onClose={onClose} title={rule ? "Edit rule" : "New comment rule"}
                description="One private message per comment, within Instagram's 7 days. Write it as you would yourself."
                footer={<>
                    <Button variant="ghost" onClick={onClose}>Cancel</Button>
                    <Button variant="primary" disabled={saving || !name.trim() || !privateReply.trim() || room < 0 || (mode === "some" && !picked.length)} onClick={save}>Save</Button>
                </>}>
            <div className="space-y-4 max-h-[60vh] overflow-y-auto pr-1">
                <label className="block">
                    <span className="text-xs text-stone-500">Name</span>
                    <Input className="mt-1" aria-label="Rule name" maxLength={120} placeholder="Price list on the new 2BHK post" value={name} onChange={(e) => setName(e.target.value)} />
                </label>
                <fieldset>
                    <legend className="text-xs text-stone-500">Which posts and reels</legend>
                    <div className="flex gap-4 mt-1.5 text-sm">
                        <label className="flex items-center gap-2"><input type="radio" className="accent-plum" checked={mode === "all"} onChange={() => setMode("all")} /> Every one</label>
                        <label className="flex items-center gap-2"><input type="radio" className="accent-plum" checked={mode === "some"} onChange={() => setMode("some")} /> Choose</label>
                    </div>
                    {mode === "some" && (
                        <div className="mt-2 grid grid-cols-2 sm:grid-cols-3 gap-2">
                            {media === null && [0, 1, 2].map((i) => <Skeleton key={i} className="h-24" />)}
                            {media?.length === 0 && <p className="col-span-full text-[13px] text-stone-500">No posts found on this account.</p>}
                            {media?.map((m) => {
                                const on = picked.includes(m.id);
                                return (
                                    <button key={m.id} type="button" aria-pressed={on} onClick={() => setPicked(on ? picked.filter((x) => x !== m.id) : [...picked, m.id])}
                                            className={cn("text-left rounded-md border p-1.5 transition-colors", on ? "border-plum bg-plum-tint" : "border-line hover:border-line-strong")}>
                                        {/* eslint-disable-next-line @next/next/no-img-element */}
                                        {m.picture ? <img src={m.picture} alt="" referrerPolicy="no-referrer" className="h-20 w-full object-cover rounded" /> : <div className="h-20 rounded bg-stone-100" />}
                                        <span className="block text-[11px] text-stone-600 mt-1 line-clamp-2">{m.caption || (m.at ? formatWhen(m.at) : m.id)}</span>
                                    </button>
                                );
                            })}
                        </div>
                    )}
                </fieldset>
                <div>
                    <span className="text-xs text-stone-500">Words to reply to, in any language. None: every comment.</span>
                    <div className="mt-1"><PhraseInput keepCase value={keywords} onChange={setKeywords} label="Words" placeholder="price, விலை, cost" /></div>
                    {everything && <p className="text-xs text-amber-700 mt-1.5">With no words and every post, everyone who comments anywhere gets the private message.</p>}
                </div>
                <label className="block">
                    <span className="text-xs text-stone-500">The private message. {"{{username}}"} becomes their @name.</span>
                    <Textarea className="mt-1" aria-label="Private message" rows={3} value={privateReply} onChange={(e) => setPrivateReply(e.target.value)}
                              placeholder="Hi {{username}}, thanks for asking! Our 2BHK starts at 45 lakh. Would you like to visit this weekend?" />
                    <span className={cn("block text-[11px] mt-1 text-right", room < 0 ? "text-signal" : "text-stone-400")}>
                        {room < 0 ? `${-room} over Instagram's limit` : `${room} left`} (Tamil and Hindi letters take three)
                    </span>
                </label>
                <div>
                    <span className="text-xs text-stone-500">Public reply under their comment (optional). Add a few: each comment gets one of them, so they don&apos;t look copied.</span>
                    <div className="space-y-2 mt-1">
                        {publics.map((p, i) => (
                            <div key={i} className="flex gap-2">
                                <Input aria-label={`Public reply ${i + 1}`} maxLength={300} value={p} onChange={(e) => setPublics(publics.map((x, j) => (j === i ? e.target.value : x)))} />
                                <button type="button" aria-label={`Remove public reply ${i + 1}`} onClick={() => setPublics(publics.filter((_, j) => j !== i))} className="p-1.5 text-stone-400 hover:text-signal"><Trash2 size={15} /></button>
                            </div>
                        ))}
                        {publics.length < 5 && <Button size="sm" variant="ghost" onClick={() => setPublics([...publics, ""])}><Plus size={13} /> Add a public reply</Button>}
                    </div>
                </div>
                <div className="flex items-center justify-between gap-4">
                    <span className="text-sm">On</span>
                    <Switch label="Rule on" checked={enabled} onChange={setEnabled} />
                </div>
            </div>
        </Dialog>
    );
}
