"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button, Dialog, Input, Select, Textarea, useToast } from "@/components/ui";
import { apiJson } from "@/lib/api";

/** Someone who rang or walked in. Nobody is contacted automatically. */
export function AddLead({ open, onClose, bots }: { open: boolean; onClose: () => void; bots: { id: string; name: string }[] }) {
    const toast = useToast();
    const router = useRouter();
    const [botId, setBotId] = useState("");
    const [name, setName] = useState("");
    const [phone, setPhone] = useState("");
    const [email, setEmail] = useState("");
    const [note, setNote] = useState("");
    const [busy, setBusy] = useState(false);
    const add = async () => {
        setBusy(true);
        try {
            const made = await apiJson<{ id: string }>("/api/crm/leads", { method: "POST", json: { bot_id: botId || bots[0]?.id, name, phone, email, note } });
            router.push(`/dashboard/leads/${made.id}`);
        } catch (e) {
            toast((e as Error).message);
            setBusy(false);
        }
    };
    return (
        <Dialog open={open} onClose={onClose} title="Add a lead" description="Someone who rang or walked in. Nobody contacts them automatically."
                footer={<>
                    <Button variant="ghost" onClick={onClose}>Cancel</Button>
                    <Button variant="primary" disabled={busy || !(phone.trim() || email.trim())} onClick={add}>Add lead</Button>
                </>}>
            <div className="space-y-3">
                {bots.length > 1 && (
                    <Select aria-label="Assistant" value={botId || bots[0]?.id} onChange={(e) => setBotId(e.target.value)}>
                        {bots.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
                    </Select>
                )}
                <Input aria-label="Name" placeholder="Name" maxLength={80} value={name} onChange={(e) => setName(e.target.value)} />
                <Input aria-label="Phone" placeholder="Phone" inputMode="tel" maxLength={30} value={phone} onChange={(e) => setPhone(e.target.value)} />
                <Input aria-label="Email" placeholder="Email" type="email" maxLength={120} value={email} onChange={(e) => setEmail(e.target.value)} />
                <Textarea aria-label="What they asked" placeholder="What they asked" rows={3} maxLength={1000} value={note} onChange={(e) => setNote(e.target.value)} />
            </div>
        </Dialog>
    );
}
