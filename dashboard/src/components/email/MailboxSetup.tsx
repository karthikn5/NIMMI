"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Button, Card, Dialog, Status, useToast } from "@/components/ui";
import { apiJson } from "@/lib/api";
import type { MailConnection, MailConnections } from "@/lib/email";
import { useApi } from "@/lib/useApi";

const PROVIDER = { google: { mail: "Gmail", calendar: "Google Calendar" }, microsoft: { mail: "Outlook", calendar: "Outlook calendar" } };

function Row({ c, limit, busy, onConnect, onRemove }: { c: MailConnection; limit: number; busy: boolean; onConnect: () => void; onRemove: () => void }) {
    const does = [c.can_send && "Sends one-to-one emails", c.has_calendar && "Calendar for meetings"].filter(Boolean).join(" · ");
    return (
        <li className="flex flex-wrap items-center gap-3 px-5 py-3.5 border-t border-line first:border-t-0">
            <span className="flex-1 min-w-52">
                <span className="block text-sm break-all">{c.address}</span>
                <span className="block text-[13px] text-stone-500">
                    {does}{c.person && !c.mine ? ` · connected by ${c.person}` : ""}{c.can_send ? ` · ${c.sent_today} of ${limit} today` : ""}
                </span>
                {c.status === "reconnect" && <span className="block text-[13px] text-stone-700 mt-0.5">{(c.error || "It needs connecting again").replace(/\.?$/, ".")} Until then, emails go from your usual address.</span>}
            </span>
            <Status tone={c.status === "connected" ? "good" : "warn"}>{c.status === "connected" ? "Connected" : "Needs connecting again"}</Status>
            {c.status === "reconnect" && c.mine && <Button size="sm" disabled={busy} onClick={onConnect}>Connect again</Button>}
            <Button size="sm" variant="ghost" disabled={busy} onClick={onRemove}>Disconnect</Button>
        </li>
    );
}

/** Someone's own Gmail or Outlook, and calendar. Not shown until Nimmi has an app at Google or Microsoft. Their permission page comes back here, with a code this page finishes with the signed-in person. */
export function MailboxSetup({ onChanged }: { onChanged?: () => void }) {
    const toast = useToast();
    const router = useRouter();
    const params = useSearchParams();
    const list = useApi<MailConnections>("/api/email/connections");
    const [busy, setBusy] = useState(false);
    const [removing, setRemoving] = useState<MailConnection | null>(null);
    const finished = useRef(false);
    const { reload } = list;
    const code = params.get("code"), state = params.get("state"), denied = params.get("error");

    useEffect(() => {
        if (finished.current || (!code && !denied)) return;
        finished.current = true;
        router.replace("/dashboard/email/settings", { scroll: false });  // the code leaves the address bar at once
        if (!code || !state) {
            toast("Nothing was connected: the permission wasn't given");
            return;
        }
        setBusy(true);
        apiJson<MailConnection>("/api/email/connections/finish", { method: "POST", json: { code, state } })
            .then(async (made) => { toast(`${made.address} is connected`); await reload(); onChanged?.(); })
            .catch((e) => toast((e as Error).message))
            .finally(() => setBusy(false));
    }, [code, state, denied, router, toast, reload, onChanged]);

    const connect = async (provider: "google" | "microsoft", purpose: "mail" | "calendar") => {
        setBusy(true);
        try {
            const { url } = await apiJson<{ url: string }>(`/api/email/connections/${provider}/start`, { method: "POST", json: { purpose } });
            window.location.assign(url);
        } catch (e) {
            toast((e as Error).message);
            setBusy(false);
        }
    };
    const remove = async () => {
        if (!removing) return;
        setBusy(true);
        try {
            await apiJson(`/api/email/connections/${removing.id}`, { method: "DELETE" });
            toast(`${removing.address} is disconnected`);
            setRemoving(null);
            await reload();
            onChanged?.();
        } catch (e) {
            toast((e as Error).message);
        } finally {
            setBusy(false);
        }
    };

    const data = list.data;
    if (!data || (!data.available.google && !data.available.microsoft && !data.items.length)) return null;
    return (
        <Card>
            <div className="px-5 pt-4 pb-3">
                <h2 className="text-sm font-medium">Mailboxes and calendars</h2>
                <p className="text-[13px] text-stone-500 mt-0.5 max-w-2xl">
                    Follow-ups and answers can go from a real person&apos;s mailbox, and meetings can land in their calendar. Nimmi can only send: it never reads your email.
                    Replies still come back here. Bulk email never goes from a mailbox.
                </p>
            </div>
            {!!data.items.length && (
                <ul className="border-t border-line">
                    {data.items.map((c) => <Row key={c.id} c={c} limit={data.daily_limit} busy={busy} onRemove={() => setRemoving(c)}
                                                onConnect={() => connect(c.provider, c.can_send ? "mail" : "calendar")} />)}
                </ul>
            )}
            <div className="flex flex-wrap gap-2 px-5 py-4 border-t border-line">
                {(["google", "microsoft"] as const).filter((p) => data.available[p]).flatMap((p) => (["mail", "calendar"] as const).map((purpose) => (
                    <Button key={`${p}-${purpose}`} size="sm" disabled={busy} onClick={() => connect(p, purpose)}>Connect {PROVIDER[p][purpose]}</Button>
                )))}
            </div>
            <Dialog open={!!removing} onClose={() => setRemoving(null)} title={`Disconnect ${removing?.address ?? ""}?`}
                    footer={<>
                        <Button variant="ghost" onClick={() => setRemoving(null)}>Cancel</Button>
                        <Button variant="primary" disabled={busy} onClick={remove}>Disconnect</Button>
                    </>}>
                <p className="text-sm text-stone-700">Its emails go from your usual address again, and new meetings won&apos;t go on its calendar. Meetings already there stay.</p>
            </Dialog>
        </Card>
    );
}
