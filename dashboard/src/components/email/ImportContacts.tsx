"use client";

import { useState } from "react";
import { Button, Dialog, Textarea, useToast } from "@/components/ui";
import { apiJson } from "@/lib/api";
import type { ImportResult } from "@/lib/email";

const MAX_BYTES = 3_000_000;

/** A list the business already has, as a CSV. How these people agreed is kept with each of them: a bought list isn't consent. */
export function ImportContacts({ botId, business, onClose, onDone }: { botId: string; business: string; onClose: () => void; onDone: () => void }) {
    const toast = useToast();
    const [csv, setCsv] = useState("");
    const [file, setFile] = useState("");
    const [how, setHow] = useState("");
    const [sure, setSure] = useState(false);
    const [busy, setBusy] = useState(false);
    const [done, setDone] = useState<ImportResult | null>(null);

    const pick = async (f: File | undefined) => {
        if (!f) return;
        if (f.size > MAX_BYTES) return toast("That file is over 3 MB. Split it into smaller files.");
        setCsv(await f.text());
        setFile(f.name);
    };
    const go = async () => {
        setBusy(true);
        try {
            setDone(await apiJson<ImportResult>("/api/email/contacts/import", { method: "POST", json: { bot_id: botId, csv, how: how.trim(), confirmed: sure } }));
            onDone();
        } catch (e) {
            toast((e as Error).message);
        } finally {
            setBusy(false);
        }
    };

    if (done) {
        return (
            <Dialog open onClose={onClose} title="Imported" footer={<Button variant="primary" onClick={onClose}>Done</Button>}>
                <div className="space-y-2 text-sm">
                    <p>{done.added} added, {done.updated} already there. {done.agreed} can now get offers and news.</p>
                    {done.skipped_count > 0 && (
                        <div>
                            <p className="text-[13px] text-stone-600">{done.skipped_count} {done.skipped_count === 1 ? "line was" : "lines were"} left out:</p>
                            <ul className="mt-1 text-[13px] text-stone-500 space-y-0.5">{done.skipped.map((s) => <li key={s.line}>Line {s.line}: {s.why}</li>)}</ul>
                        </div>
                    )}
                </div>
            </Dialog>
        );
    }
    return (
        <Dialog open onClose={onClose} title="Import a list" description="A CSV file with a line of column names first: email, and name, phone or tags if you have them. Other columns are kept as their details."
                footer={<>
                    <Button variant="ghost" onClick={onClose}>Cancel</Button>
                    <Button variant="primary" onClick={go} disabled={busy || !csv.trim() || how.trim().length < 10 || !sure}>{busy ? "Importing…" : "Import"}</Button>
                </>}>
            <div className="space-y-3">
                <label className="block">
                    <span className="text-xs text-stone-500">The file</span>
                    <input type="file" accept=".csv,text/csv,text/plain" className="block mt-1 text-[13px]" aria-label="CSV file" onChange={(e) => pick(e.target.files?.[0])} />
                    {file && <span className="block text-xs text-stone-500 mt-1">{file}</span>}
                </label>
                <label className="block">
                    <span className="text-xs text-stone-500">How did these people agree to hear from {business}?</span>
                    <Textarea className="mt-1" rows={2} maxLength={500} value={how} onChange={(e) => setHow(e.target.value)}
                              placeholder="They ticked the newsletter box on our sign-up form at the October expo" />
                    <span className="block text-xs text-stone-500 mt-1">Kept with each person, as the record of their consent.</span>
                </label>
                <label className="flex items-start gap-2 text-[13px] text-stone-700">
                    <input type="checkbox" className="mt-0.5" checked={sure} onChange={(e) => setSure(e.target.checked)} />
                    <span>These people agreed to get offers and news from {business}. It isn&apos;t a bought or rented list.</span>
                </label>
                <p className="text-xs text-stone-500">Anyone who unsubscribed stays unsubscribed, whatever the list says.</p>
            </div>
        </Dialog>
    );
}
