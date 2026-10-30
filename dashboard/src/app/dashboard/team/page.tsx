"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Copy } from "lucide-react";
import AppHeader from "@/components/AppHeader";
import { Button, Card, Dialog, EmptyState, Input, Notice, SectionHeader, Select, Skeleton, Status, ToastProvider, useToast } from "@/components/ui";
import { useLimits } from "@/lib/plan";
import { apiJson, currentUserId } from "@/lib/api";
import { apiSave, useApi } from "@/lib/useApi";

type Member = { id: string; email: string; name: string; role: "admin" | "agent"; status: "invited" | "active"; created_at: string | null };

export default function TeamPage() {
    return (
        <ToastProvider>
            <Team />
        </ToastProvider>
    );
}

function Team() {
    const router = useRouter();
    const toast = useToast();
    const members = useApi<Member[]>("/api/team/members");
    const limits = useLimits();
    const seats = limits?.includes?.seats;
    const used = limits?.used.seats ?? 1;
    const full = seats !== undefined && used >= seats;
    const [email, setEmail] = useState("");
    const [role, setRole] = useState<"admin" | "agent">("agent");
    const [busy, setBusy] = useState(false);
    const [link, setLink] = useState<string | null>(null);
    const [removing, setRemoving] = useState<Member | null>(null);

    useEffect(() => { if (!currentUserId()) router.push("/auth/login"); }, [router]);

    const invite = async (e: React.FormEvent) => {
        e.preventDefault();
        setBusy(true);
        try {
            const res = await apiJson<Member & { email_sent: boolean; invite_link_path: string }>("/api/team/invite", { method: "POST", json: { email, role } });
            members.setData([...(members.data ?? []), res]);
            setEmail("");
            if (res.email_sent) toast(`Invite sent to ${res.email}`);
            else setLink(`${window.location.origin}${res.invite_link_path}`);
        } catch (err) {
            toast((err as Error).message);
        } finally {
            setBusy(false);
        }
    };

    const changeRole = async (m: Member, next: Member["role"]) => {
        const res = await apiSave(`/api/team/members/${m.id}`, "PATCH", { role: next });
        if (!res.ok) return toast(res.message);
        members.setData((members.data ?? []).map((x) => (x.id === m.id ? { ...x, role: next } : x)));
    };

    const remove = async (m: Member) => {
        const res = await apiSave(`/api/team/members/${m.id}`, "DELETE");
        setRemoving(null);
        if (!res.ok) return toast(res.message);
        members.setData((members.data ?? []).filter((x) => x.id !== m.id));
        toast(`${m.email} no longer has access`);
    };

    return (
        <div className="min-h-screen bg-paper text-ink">
            <AppHeader />
            <main className="max-w-4xl mx-auto px-4 sm:px-6 py-8 pb-24">
                <h1 className="text-2xl font-semibold tracking-tight">Team</h1>
                <p className="text-sm text-stone-500 mt-1">Invite people to help run this workspace. Agencies can manage each client from one login.</p>

                <dl className="grid sm:grid-cols-2 gap-3 mt-6 text-[13px]">
                    <div className="px-4 py-3 bg-white border border-line rounded-md">
                        <dt className="font-medium">Admin</dt>
                        <dd className="text-stone-500 mt-0.5">Builds and edits assistants, voice, numbers and integrations. Can&apos;t see billing or the team.</dd>
                    </div>
                    <div className="px-4 py-3 bg-white border border-line rounded-md">
                        <dt className="font-medium">Agent</dt>
                        <dd className="text-stone-500 mt-0.5">Replies in live chat and reads calls and analytics. Can&apos;t change settings.</dd>
                    </div>
                </dl>

                <section className="mt-8">
                    <SectionHeader title="Invite someone"
                                   description={seats !== undefined ? `${used} of ${seats} team ${seats === 1 ? "seat" : "seats"} used, yours included.` : undefined} />
                    {full && (
                        <Notice title="Your plan's seats are all used"
                                action={seats < 5 ? <Link href="/dashboard/billing" className="inline-flex items-center h-8 px-3 rounded-md bg-plum text-white text-[13px] font-medium hover:bg-plum-hover">Choose a plan</Link> : undefined}>
                            {seats < 3 ? "Growth includes 3 seats and Pro 5: choose one for an assistant on the Billing page."
                                : seats < 5 ? "Pro includes 5 seats: choose it for an assistant on the Billing page."
                                : "For more, write to support.nimmi@gmail.com."}
                        </Notice>
                    )}
                    <Card className="p-5">
                        <form onSubmit={invite} className="flex flex-col sm:flex-row gap-3">
                            <Input type="email" required placeholder="name@company.com" aria-label="Email" value={email} onChange={(e) => setEmail(e.target.value)} />
                            <Select aria-label="Role" className="sm:w-36" value={role} onChange={(e) => setRole(e.target.value as Member["role"])}>
                                <option value="agent">Agent</option>
                                <option value="admin">Admin</option>
                            </Select>
                            <Button type="submit" variant="primary" disabled={busy}>{busy ? "Inviting…" : "Send invite"}</Button>
                        </form>
                    </Card>
                </section>

                <section className="mt-8">
                    <SectionHeader title="People" />
                    <Card>
                        {members.loading ? <div className="p-5"><Skeleton className="h-10" /></div> : !members.data?.length ? (
                            <EmptyState title="Just you so far" body="Invite a teammate or a client to share this workspace." />
                        ) : (
                            <ul>
                                {members.data.map((m) => (
                                    <li key={m.id} className="grid grid-cols-[minmax(0,1fr)_auto] sm:grid-cols-[minmax(0,1fr)_8rem_8rem_auto] gap-x-4 gap-y-2 items-center px-5 py-3 border-t border-line first:border-t-0">
                                        <div className="min-w-0">
                                            <p className="text-sm font-medium truncate">{m.name || m.email}</p>
                                            {m.name && <p className="text-xs text-stone-500 truncate">{m.email}</p>}
                                        </div>
                                        <Status tone={m.status === "active" ? "good" : "neutral"}>{m.status === "active" ? "Active" : "Invited"}</Status>
                                        <Select aria-label={`Role for ${m.email}`} className="h-8 text-[13px]" value={m.role} onChange={(e) => changeRole(m, e.target.value as Member["role"])}>
                                            <option value="agent">Agent</option>
                                            <option value="admin">Admin</option>
                                        </Select>
                                        <Button size="sm" variant="ghost" onClick={() => setRemoving(m)}>Remove</Button>
                                    </li>
                                ))}
                            </ul>
                        )}
                    </Card>
                </section>
            </main>

            <Dialog open={!!link} onClose={() => setLink(null)} title="Share the invite link"
                    description="Email isn't set up on the server, so send this link yourself. It works once, for the invited email."
                    footer={<Button onClick={() => setLink(null)}>Done</Button>}>
                <div className="flex gap-2">
                    <Input readOnly value={link ?? ""} className="font-mono text-xs" aria-label="Invite link" />
                    <Button aria-label="Copy link" onClick={() => link && navigator.clipboard.writeText(link).then(() => toast("Copied"))}><Copy size={14} /></Button>
                </div>
            </Dialog>

            <Dialog open={!!removing} onClose={() => setRemoving(null)} title={`Remove ${removing?.email}?`}
                    description="They lose access to this workspace straight away."
                    footer={<>
                        <Button variant="ghost" onClick={() => setRemoving(null)}>Cancel</Button>
                        <Button variant="danger" onClick={() => removing && remove(removing)}>Remove</Button>
                    </>}>
                <p className="text-[13px] text-stone-600">You can invite them again later.</p>
            </Dialog>
        </div>
    );
}
