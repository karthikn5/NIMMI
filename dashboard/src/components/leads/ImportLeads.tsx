"use client";

import { useState } from "react";
import { Button, Dialog, Input, Select, useToast } from "@/components/ui";
import { apiJson } from "@/lib/api";

const MAX_BYTES = 3_000_000;

interface Done { added: number; existing: number; skipped_count: number; skipped: { line: number; why: string }[] }

/** Leads from an old spreadsheet. They're kept with their source, and nobody is contacted because of this. */
export function ImportLeads({ bots, onClose, onDone }: { bots: { id: string; name: string }[]; onClose: () => void; onDone: () => void }) {
    const toast = useToast();
    const [botId, setBotId] = useState(bots[0]?.id ?? "");
    const [csv, setCsv] = useState("");
    const [file, setFile] = useState("");
    const [source, setSource] = useState("");
    const [busy, setBusy] = useState(false);
    const [done, setDone] = useState<Done | null>(null);

    const pick = async (f: File | undefined) => {
        if (!f) return;
        if (f.size > MAX_BYTES) return toast("That file is over 3 MB. Split it into smaller files.");
        setCsv(await f.text());
        setFile(f.name);
    };
    const go = async () => {
        setBusy(true);
        try {
            setDone(await apiJson<Done>("/api/crm/import", { method: "POST", json: { bot_id: botId, csv, source: source.trim() } }));
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
                    <p>{done.added} added, {done.existing} already here.</p>
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
        <Dialog open onClose={onClose} title="Import old leads" description="A CSV file with a line of column names first: name, phone, email, and source, stage or notes if you have them. Nobody is contacted because of this."
                footer={<>
                    <Button variant="ghost" onClick={onClose}>Cancel</Button>
                    <Button variant="primary" onClick={go} disabled={busy || !csv.trim() || !botId}>{busy ? "Importing…" : "Import"}</Button>
                </>}>
            <div className="space-y-3">
                {bots.length > 1 && (
                    <label className="block">
                        <span className="text-xs text-stone-500">Assistant</span>
                        <Select className="mt-1" aria-label="Assistant" value={botId} onChange={(e) => setBotId(e.target.value)}>
                            {bots.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
                        </Select>
                    </label>
                )}
                <label className="block">
                    <span className="text-xs text-stone-500">The file</span>
                    <input type="file" accept=".csv,text/csv,text/plain" className="block mt-1 text-[13px]" aria-label="CSV file" onChange={(e) => pick(e.target.files?.[0])} />
                    {file && <span className="block text-xs text-stone-500 mt-1">{file}</span>}
                </label>
                <label className="block">
                    <span className="text-xs text-stone-500">Where these leads came from, if the file doesn&apos;t say</span>
                    <Input className="mt-1" aria-label="Where they came from" maxLength={40} placeholder="Old spreadsheet" value={source} onChange={(e) => setSource(e.target.value)} />
                </label>
            </div>
        </Dialog>
    );
}
