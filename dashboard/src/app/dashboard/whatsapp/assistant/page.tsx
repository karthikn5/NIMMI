"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Card, EmptyState, SaveBar, Segmented, Select, SettingRow, Skeleton, Switch, Textarea, useToast } from "@/components/ui";
import { useApi, useDraft } from "@/lib/useApi";
import { PAUSE_CHOICES, type WaNumber, type WaSettings } from "@/lib/whatsapp";

const WAITS = [0, 2, 4, 6, 8, 10, 15];

/** How the assistant behaves on each WhatsApp number. */
export default function WhatsAppAssistantPage() {
    const numbers = useApi<WaNumber[]>("/api/whatsapp/numbers");
    const [id, setId] = useState("");
    useEffect(() => { if (!id && numbers.data?.length) setId(numbers.data[0].id); }, [numbers.data, id]);

    if (numbers.loading) return <div className="space-y-3 max-w-3xl">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-20" />)}</div>;
    if (numbers.error) return <p className="text-sm text-signal">Couldn&apos;t load your numbers. {numbers.error}</p>;
    if (!numbers.data?.length) {
        return (
            <Card className="max-w-3xl">
                <EmptyState title="Connect a number first" body="Once your WhatsApp number is connected, choose here how the assistant answers on it."
                            action={<Link href="/dashboard/whatsapp/settings" className="inline-flex items-center h-9 px-4 rounded-md bg-plum text-white text-sm font-medium hover:bg-plum-hover">Connect a number</Link>} />
            </Card>
        );
    }
    const number = numbers.data.find((n) => n.id === id) ?? numbers.data[0];
    return (
        <div className="max-w-3xl">
            {numbers.data.length > 1 && (
                <div className="mb-4">
                    <Select aria-label="WhatsApp number" className="w-auto" value={number.id} onChange={(e) => setId(e.target.value)}>
                        {numbers.data.map((n) => <option key={n.id} value={n.id}>{n.display_number ?? n.phone_number_id}</option>)}
                    </Select>
                </div>
            )}
            <NumberSettings key={number.id} number={number} onSaved={(n) => numbers.setData(numbers.data!.map((x) => (x.id === n.id ? n : x)))} />
        </div>
    );
}

function NumberSettings({ number, onSaved }: { number: WaNumber; onSaved: (n: WaNumber) => void }) {
    const toast = useToast();
    const bots = useApi<{ id: string; name: string }[]>("/api/bots");
    const [source, setSource] = useState<WaNumber | null>(number);
    const { draft, setDraft, dirty, saving, save, discard } = useDraft<WaNumber>(
        { data: source, setData: (n) => { setSource(n); onSaved(n); } }, `/api/whatsapp/numbers/${number.id}`, "PATCH");
    if (!draft) return null;
    const s = draft.settings;
    const set = <K extends keyof WaSettings>(k: K, v: WaSettings[K]) => setDraft({ ...draft, settings: { ...s, [k]: v } });

    return (
        <div className="space-y-6">
            <Card className="px-5 py-1">
                <SettingRow label="Answer with AI" hint="The assistant replies to every message on this number, day and night. Your team can step in on any chat.">
                    <Switch checked={draft.ai_enabled} onChange={(v) => setDraft({ ...draft, ai_enabled: v })} label="Answer WhatsApp messages with AI" />
                </SettingRow>
                <SettingRow label="Assistant" htmlFor="wa-bot" hint="It answers from this assistant's knowledge, with its rules and the details it collects.">
                    <Select id="wa-bot" value={draft.bot_id} onChange={(e) => setDraft({ ...draft, bot_id: e.target.value })}>
                        <option value="">Your first active assistant</option>
                        {(bots.data ?? []).map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
                    </Select>
                </SettingRow>
            </Card>

            <section>
                <h2 className="text-[15px] font-semibold">Like a person on your team</h2>
                <p className="text-[13px] text-stone-500 mt-0.5 mb-3">How the replies feel to your customers.</p>
                <Card className="px-5 py-1">
                    <SettingRow label="Wait before answering" htmlFor="wa-wait"
                                hint="People often send a few short messages in a row. Waiting a moment means one answer to all of them.">
                        <Select id="wa-wait" value={String(s.wait_seconds)} onChange={(e) => set("wait_seconds", Number(e.target.value))}>
                            {WAITS.map((w) => <option key={w} value={w}>{w === 0 ? "Answer at once" : `${w} seconds`}</option>)}
                        </Select>
                    </SettingRow>
                    <SettingRow label="Show “typing…”" hint="Their message shows as read and they see the assistant typing, with a short pause that fits each reply.">
                        <Switch checked={s.typing} onChange={(v) => set("typing", v)} label="Show typing" />
                    </SettingRow>
                    <SettingRow label="Short messages" hint="Up to three short messages instead of one long one, the way people write on WhatsApp.">
                        <Switch checked={s.split} onChange={(v) => set("split", v)} label="Send short messages" />
                    </SettingRow>
                    <SettingRow label="Reply length" hint="Short keeps replies to a few lines unless the customer asks for details.">
                        <Segmented<WaSettings["length"]> label="Reply length" value={s.length} onChange={(v) => set("length", v)}
                                                         options={[{ value: "short", label: "Short" }, { value: "normal", label: "Normal" }]} />
                    </SettingRow>
                    <SettingRow label="Welcome message" htmlFor="wa-welcome"
                                hint="Optional. Sent before the first answer to someone new, for example your business name and hours.">
                        <Textarea id="wa-welcome" rows={2} maxLength={500} placeholder="Welcome to Sri Balaji Clinic. We're open 9 am to 8 pm, Monday to Saturday."
                                  value={s.welcome} onChange={(e) => set("welcome", e.target.value)} />
                    </SettingRow>
                </Card>
            </section>

            <section>
                <h2 className="text-[15px] font-semibold">What it can do</h2>
                <Card className="px-5 py-1 mt-3">
                    <SettingRow label="Understand voice notes, photos and PDFs" hint="Voice notes in Tamil, Hindi, English and other Indian languages are written out; photos and PDFs are read. Your team sees them in the Inbox.">
                        <Switch checked={s.understand_media} onChange={(v) => set("understand_media", v)} label="Understand voice notes, photos and PDFs" />
                    </SettingRow>
                    <SettingRow label="Send your files" hint={<>It sends a brochure, price list or photo from <Link href="/dashboard/whatsapp/files" className="text-plum hover:underline">Files</Link> when the conversation calls for it.</>}>
                        <Switch checked={s.send_files} onChange={(v) => set("send_files", v)} label="Send files" />
                    </SettingRow>
                    <SettingRow label="Offer choices as buttons" hint="When the customer has to pick, for example a time slot, they can tap a button instead of typing.">
                        <Switch checked={s.buttons} onChange={(v) => set("buttons", v)} label="Offer choices as buttons" />
                    </SettingRow>
                </Card>
            </section>

            <section>
                <h2 className="text-[15px] font-semibold">When your team steps in</h2>
                <Card className="px-5 py-1 mt-3">
                    <SettingRow label="Leave the chat to your team for" htmlFor="wa-pause"
                                hint="After someone on your team replies, from the Inbox or the WhatsApp app, the assistant stays quiet on that chat. They can hand it back sooner.">
                        <Select id="wa-pause" value={String(s.pause_hours)} onChange={(e) => set("pause_hours", Number(e.target.value))}>
                            {PAUSE_CHOICES.map((h) => <option key={h} value={h}>{h === 1 ? "1 hour" : `${h} hours`}</option>)}
                        </Select>
                    </SettingRow>
                    <p className="pb-4 text-[13px] text-stone-500">
                        Customers can ask for a person at any time, and upset customers are handed over automatically. Outside your business
                        hours they hear your away message: set both in <Link href="/dashboard/live-chat" className="text-plum hover:underline">Live chat</Link> &gt; Settings.
                    </p>
                </Card>
            </section>

            <SaveBar visible={dirty} saving={saving} onDiscard={discard} onSave={async () => toast(await save())} />
        </div>
    );
}
