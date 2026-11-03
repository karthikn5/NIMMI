"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Plus, Trash2 } from "lucide-react";
import { Button, Card, EmptyState, Input, SaveBar, Segmented, Select, SettingRow, Skeleton, Switch, Textarea, useToast } from "@/components/ui";
import { apiJson } from "@/lib/api";
import { PAUSE_CHOICES, type IgAccount, type IgOverview, type IgSettings } from "@/lib/instagram";
import { useApi, useDraft } from "@/lib/useApi";

const WAITS = [0, 2, 4, 6, 8, 10];

/** How the assistant behaves on each Instagram account. */
export default function InstagramAssistantPage() {
    const overview = useApi<IgOverview>("/api/instagram");
    const [id, setId] = useState("");
    const list = overview.data?.accounts ?? [];
    useEffect(() => { if (!id && list.length) setId(list[0].id); }, [list, id]);

    if (overview.loading) return <div className="space-y-3 max-w-3xl">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-20" />)}</div>;
    if (overview.error) return <p className="text-sm text-signal">Couldn&apos;t load your account. {overview.error}</p>;
    if (!list.length) {
        return (
            <Card className="max-w-3xl">
                <EmptyState title="Connect your account first" body="Once your Instagram account is connected, choose here how the assistant answers its messages."
                            action={<Link href="/dashboard/instagram/settings" className="inline-flex items-center h-9 px-4 rounded-md bg-plum text-white text-sm font-medium hover:bg-plum-hover">Connect Instagram</Link>} />
            </Card>
        );
    }
    const account = list.find((a) => a.id === id) ?? list[0];
    return (
        <div className="max-w-3xl">
            {list.length > 1 && (
                <div className="mb-4">
                    <Select aria-label="Instagram account" className="w-auto" value={account.id} onChange={(e) => setId(e.target.value)}>
                        {list.map((a) => <option key={a.id} value={a.id}>@{a.username ?? a.ig_id}</option>)}
                    </Select>
                </div>
            )}
            <AccountSettings key={account.id} account={account}
                             onSaved={(a) => overview.setData({ ...overview.data!, accounts: list.map((x) => (x.id === a.id ? a : x)) })} />
        </div>
    );
}

function AccountSettings({ account, onSaved }: { account: IgAccount; onSaved: (a: IgAccount) => void }) {
    const toast = useToast();
    const bots = useApi<{ id: string; name: string }[]>("/api/bots");
    const [source, setSource] = useState<IgAccount | null>(account);
    const { draft, setDraft, dirty, saving, save, discard } = useDraft<IgAccount>(
        { data: source, setData: (a) => { setSource(a); onSaved(a); } }, `/api/instagram/accounts/${account.id}`, "PATCH");
    if (!draft) return null;
    const s = draft.settings;
    const set = <K extends keyof IgSettings>(k: K, v: IgSettings[K]) => setDraft({ ...draft, settings: { ...s, [k]: v } });

    return (
        <div className="space-y-6">
            <Card className="px-5 py-1">
                <SettingRow label="Answer with AI" hint="The assistant replies to every message, day and night, inside Instagram's 24 hours. Your team can step in on any chat.">
                    <Switch checked={draft.ai_enabled} onChange={(v) => setDraft({ ...draft, ai_enabled: v })} label="Answer Instagram messages with AI" />
                </SettingRow>
                <SettingRow label="Assistant" htmlFor="ig-bot" hint="It answers from this assistant's knowledge, with its rules and the details it collects.">
                    <Select id="ig-bot" value={draft.bot_id} onChange={(e) => setDraft({ ...draft, bot_id: e.target.value })}>
                        <option value="">Your first active assistant</option>
                        {(bots.data ?? []).map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
                    </Select>
                </SettingRow>
            </Card>

            <section>
                <h2 className="text-[15px] font-semibold">Like a person on your team</h2>
                <p className="text-[13px] text-stone-500 mt-0.5 mb-3">How the replies feel to the people who write.</p>
                <Card className="px-5 py-1">
                    <SettingRow label="Wait before answering" htmlFor="ig-wait"
                                hint="People often send a few short messages in a row. Waiting a moment means one answer to all of them. Kept short: Instagram expects an answer within 30 seconds.">
                        <Select id="ig-wait" value={String(s.wait_seconds)} onChange={(e) => set("wait_seconds", Number(e.target.value))}>
                            {WAITS.map((w) => <option key={w} value={w}>{w === 0 ? "Answer at once" : `${w} seconds`}</option>)}
                        </Select>
                    </SettingRow>
                    <SettingRow label="Show “typing…”" hint="Their message shows as seen and they see the assistant typing.">
                        <Switch checked={s.typing} onChange={(v) => set("typing", v)} label="Show typing" />
                    </SettingRow>
                    <SettingRow label="Short messages" hint="Up to three short messages instead of one long one, the way people write in DMs.">
                        <Switch checked={s.split} onChange={(v) => set("split", v)} label="Send short messages" />
                    </SettingRow>
                    <SettingRow label="Reply length" hint="Short keeps replies to a few lines unless they ask for details.">
                        <Segmented<IgSettings["length"]> label="Reply length" value={s.length} onChange={(v) => set("length", v)}
                                                         options={[{ value: "short", label: "Short" }, { value: "normal", label: "Normal" }]} />
                    </SettingRow>
                    <SettingRow label="Welcome message" htmlFor="ig-welcome" hint="Optional. Sent before the first answer to someone new.">
                        <Textarea id="ig-welcome" rows={2} maxLength={300} placeholder="Thanks for writing to Sunrise Homes. We're open 9 am to 7 pm, Monday to Saturday."
                                  value={s.welcome} onChange={(e) => set("welcome", e.target.value)} />
                    </SettingRow>
                </Card>
            </section>

            <section>
                <h2 className="text-[15px] font-semibold">What it can do</h2>
                <Card className="px-5 py-1 mt-3">
                    <SettingRow label="Understand voice messages, photos and PDFs" hint="Voice messages in Indian languages are written out; photos and PDFs are read. Your team sees them in the Inbox.">
                        <Switch checked={s.understand_media} onChange={(v) => set("understand_media", v)} label="Understand voice messages, photos and PDFs" />
                    </SettingRow>
                    <SettingRow label="Offer choices as quick replies" hint="When they have to pick, for example a site visit or a call, they can tap instead of typing. Instagram shows quick replies on phones.">
                        <Switch checked={s.buttons} onChange={(v) => set("buttons", v)} label="Offer choices as quick replies" />
                    </SettingRow>
                </Card>
            </section>

            <section>
                <h2 className="text-[15px] font-semibold">When your team steps in</h2>
                <Card className="px-5 py-1 mt-3">
                    <SettingRow label="Leave the chat to your team for" htmlFor="ig-pause"
                                hint="After someone on your team replies, from the Inbox or the Instagram app, the assistant stays quiet on that chat. They can hand it back sooner.">
                        <Select id="ig-pause" value={String(s.pause_hours)} onChange={(e) => set("pause_hours", Number(e.target.value))}>
                            {PAUSE_CHOICES.map((h) => <option key={h} value={h}>{h === 1 ? "1 hour" : `${h} hours`}</option>)}
                        </Select>
                    </SettingRow>
                    <p className="pb-4 text-[13px] text-stone-500">
                        People can ask for a person at any time, and upset people are handed over automatically. After 24 hours only your team can reply, for up to 7 days.
                    </p>
                </Card>
            </section>

            <ChatStarters account={account} onSaved={(a) => { setSource(a); onSaved(a); }} />

            <SaveBar visible={dirty} saving={saving} onDiscard={discard} onSave={async () => toast(await save())} />
        </div>
    );
}

type MenuItem = { title: string; url?: string };

/** Ice breakers and the chat menu live on Instagram, not here: saving sends them at once (the Assistant settings above save separately). */
function ChatStarters({ account, onSaved }: { account: IgAccount; onSaved: (a: IgAccount) => void }) {
    const toast = useToast();
    const saved = account.profile ?? { ice_breakers: [], menu: [] };
    const [questions, setQuestions] = useState<string[]>(saved.ice_breakers ?? []);
    const [menu, setMenu] = useState<MenuItem[]>(saved.menu ?? []);
    const [busy, setBusy] = useState(false);
    if (account.profile === undefined) return null;  // an older server: nothing to show yet
    const changed = JSON.stringify(questions) !== JSON.stringify(saved.ice_breakers ?? []) || JSON.stringify(menu) !== JSON.stringify(saved.menu ?? []);
    const badLink = menu.some((m) => (m.url ?? "").trim() !== "" && !(m.url ?? "").trim().startsWith("https://"));
    const connected = account.status === "connected";

    const send = async () => {
        setBusy(true);
        try {
            const a = await apiJson<IgAccount>(`/api/instagram/accounts/${account.id}/profile`, { method: "PUT", json: {
                ice_breakers: questions.map((q) => q.trim()).filter(Boolean),
                menu: menu.map((m) => ({ title: m.title.trim(), ...(m.url?.trim() ? { url: m.url.trim() } : {}) })).filter((m) => m.title) } });
            setQuestions(a.profile?.ice_breakers ?? []);
            setMenu(a.profile?.menu ?? []);
            onSaved(a);
            toast("Saved on Instagram");
        } catch (e) {
            toast((e as Error).message);
        } finally {
            setBusy(false);
        }
    };

    return (
        <section>
            <h2 className="text-[15px] font-semibold">Starting a chat</h2>
            <p className="text-[13px] text-stone-500 mt-0.5 mb-3">Shown by Instagram in the chat itself. A tap arrives as their message, and the assistant answers it.</p>
            <Card className="p-5 space-y-5">
                <div>
                    <p className="text-sm font-medium">Questions to tap</p>
                    <p className="text-[13px] text-stone-500 mt-0.5">Up to 4, shown to someone opening a chat with you for the first time. Links with a ref (Settings) need at least one.</p>
                    <div className="space-y-2 mt-2">
                        {questions.map((q, i) => (
                            <div key={i} className="flex gap-2">
                                <Input aria-label={`Question ${i + 1}`} maxLength={80} value={q} placeholder="What are your prices?"
                                       onChange={(e) => setQuestions(questions.map((x, j) => (j === i ? e.target.value : x)))} />
                                <button type="button" aria-label={`Remove question ${i + 1}`} onClick={() => setQuestions(questions.filter((_, j) => j !== i))}
                                        className="p-1.5 text-stone-400 hover:text-signal"><Trash2 size={15} /></button>
                            </div>
                        ))}
                        {questions.length < 4 && <Button size="sm" variant="ghost" onClick={() => setQuestions([...questions, ""])}><Plus size={13} /> Add a question</Button>}
                    </div>
                </div>
                <div>
                    <p className="text-sm font-medium">Menu</p>
                    <p className="text-[13px] text-stone-500 mt-0.5">Up to 5 items, always in the chat. With a link it opens the page; without one it&apos;s sent as their message.</p>
                    <div className="space-y-2 mt-2">
                        {menu.map((m, i) => (
                            <div key={i} className="flex flex-col sm:flex-row gap-2">
                                <Input aria-label={`Menu item ${i + 1}`} className="sm:w-48" maxLength={30} value={m.title} placeholder="Book a site visit"
                                       onChange={(e) => setMenu(menu.map((x, j) => (j === i ? { ...x, title: e.target.value } : x)))} />
                                <div className="flex flex-1 gap-2">
                                    <Input aria-label={`Menu link ${i + 1}`} value={m.url ?? ""} placeholder="https:// (optional)"
                                           onChange={(e) => setMenu(menu.map((x, j) => (j === i ? { ...x, url: e.target.value } : x)))} />
                                    <button type="button" aria-label={`Remove menu item ${i + 1}`} onClick={() => setMenu(menu.filter((_, j) => j !== i))}
                                            className="p-1.5 text-stone-400 hover:text-signal"><Trash2 size={15} /></button>
                                </div>
                            </div>
                        ))}
                        {menu.length < 5 && <Button size="sm" variant="ghost" onClick={() => setMenu([...menu, { title: "" }])}><Plus size={13} /> Add a menu item</Button>}
                        {badLink && <p className="text-xs text-signal">A link must start with https://</p>}
                    </div>
                </div>
                {saved.error && !changed && <p className="text-xs text-signal">Instagram didn&apos;t take the last change: {saved.error}</p>}
                <div className="flex items-center justify-end gap-3">
                    {!connected && <span className="text-[13px] text-stone-500">Connect the account again first (Settings).</span>}
                    <Button variant="primary" disabled={busy || !changed || badLink || !connected} onClick={send}>{busy ? "Saving..." : "Save on Instagram"}</Button>
                </div>
            </Card>
        </section>
    );
}
