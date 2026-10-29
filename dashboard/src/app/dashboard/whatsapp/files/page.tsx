"use client";

import { useRef, useState } from "react";
import { FileText, Film, Image as ImageIcon, Music, Plus } from "lucide-react";
import { Button, Card, Dialog, EmptyState, Input, Select, Skeleton, Textarea, useToast } from "@/components/ui";
import { apiJson, apiUrl } from "@/lib/api";
import { formatBytes } from "@/lib/plan";
import { apiSave, useApi } from "@/lib/useApi";
import { fileKind, useRole, type WaFile } from "@/lib/whatsapp";

const ACCEPT = ".jpg,.jpeg,.png,.mp4,.3gp,.mp3,.m4a,.aac,.ogg,.amr,.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt";
const ICONS = { image: ImageIcon, video: Film, audio: Music, document: FileText };

/** Brochures, price lists, menus and photos the assistant sends on WhatsApp when they fit the conversation. */
export default function WhatsAppFilesPage() {
    const toast = useToast();
    const files = useApi<WaFile[]>("/api/whatsapp/files");
    const role = useRole();
    const [editing, setEditing] = useState<WaFile | "new" | null>(null);
    const [removing, setRemoving] = useState<WaFile | null>(null);
    const manager = role !== null && role !== "agent";

    const remove = async () => {
        if (!removing) return;
        const res = await apiSave(`/api/whatsapp/files/${removing.id}`, "DELETE");
        setRemoving(null);
        if (!res.ok) return toast(res.message);
        toast("File removed");
        files.reload();
    };

    return (
        <>
            <div className="flex flex-col md:flex-row md:items-end justify-between gap-3 mb-4">
                <div>
                    <h2 className="text-[15px] font-semibold">Files</h2>
                    <p className="text-[13px] text-stone-500 mt-0.5 max-w-2xl">
                        Brochures, price lists, menus and photos. Tell the assistant when to send each one, and it shares it at the right moment.
                        Your team can also send them from the Inbox.
                    </p>
                </div>
                {manager && <Button variant="primary" onClick={() => setEditing("new")}><Plus size={15} /> Add a file</Button>}
            </div>

            <Card>
                {files.loading ? (
                    <div className="p-5 space-y-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-14" />)}</div>
                ) : files.error ? (
                    <p className="p-5 text-sm text-signal">Couldn&apos;t load files. {files.error}</p>
                ) : !files.data?.length ? (
                    <EmptyState title="No files yet"
                                body="Add the things customers usually ask for: a course brochure, a price list, a menu, photos of your work."
                                action={manager ? <Button variant="primary" onClick={() => setEditing("new")}><Plus size={15} /> Add a file</Button> : undefined} />
                ) : (
                    <ul>
                        {files.data.map((f) => {
                            const Icon = ICONS[f.kind] ?? FileText;
                            return (
                                <li key={f.id} className="flex gap-4 px-5 py-4 border-t border-line first:border-t-0">
                                    <span className="h-10 w-10 shrink-0 rounded-md bg-plum-tint text-plum flex items-center justify-center" aria-hidden><Icon size={18} /></span>
                                    <div className="min-w-0 flex-1">
                                        <div className="flex flex-wrap items-baseline gap-x-3">
                                            <a href={apiUrl(f.url)} target="_blank" rel="noopener noreferrer" className="text-sm font-medium hover:underline">{f.name}</a>
                                            <span className="text-xs text-stone-500">{fileKind(f)} · {formatBytes(f.size)}{f.bot_name ? ` · ${f.bot_name} only` : ""}</span>
                                        </div>
                                        <p className="text-[13px] text-stone-600 mt-1">
                                            {f.when_to_send ? <><span className="text-stone-500">When to send:</span> {f.when_to_send}</> : <span className="text-stone-400">No instructions: sent when it helps.</span>}
                                        </p>
                                        <p className="text-xs text-stone-400 mt-1 tabular-nums">{f.sends ? `Sent ${f.sends} time${f.sends === 1 ? "" : "s"}` : "Not sent yet"}</p>
                                    </div>
                                    {manager && (
                                        <div className="flex items-start gap-1 shrink-0">
                                            <Button size="sm" variant="ghost" onClick={() => setEditing(f)}>Edit</Button>
                                            <Button size="sm" variant="ghost" onClick={() => setRemoving(f)}>Remove</Button>
                                        </div>
                                    )}
                                </li>
                            );
                        })}
                    </ul>
                )}
            </Card>

            {editing && <FileDialog file={editing === "new" ? null : editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); files.reload(); }} />}
            <Dialog open={!!removing} onClose={() => setRemoving(null)} title="Remove this file?"
                    description="The assistant stops sending it. Chats where it was already sent keep it."
                    footer={<><Button variant="ghost" onClick={() => setRemoving(null)}>Cancel</Button><Button variant="primary" onClick={remove}>Remove</Button></>}>
                <p className="text-[13px] text-stone-600">{removing?.name}</p>
            </Dialog>
        </>
    );
}

function FileDialog({ file, onClose, onSaved }: { file: WaFile | null; onClose: () => void; onSaved: () => void }) {
    const toast = useToast();
    const bots = useApi<{ id: string; name: string }[]>("/api/bots");
    const input = useRef<HTMLInputElement>(null);
    const [picked, setPicked] = useState<File | null>(null);
    const [form, setForm] = useState({ name: file?.name ?? "", when_to_send: file?.when_to_send ?? "", caption: file?.caption ?? "", bot_id: file?.bot_id ?? "" });
    const [busy, setBusy] = useState(false);

    const save = async () => {
        setBusy(true);
        try {
            if (file) {
                await apiJson(`/api/whatsapp/files/${file.id}`, { method: "PATCH", json: form });
            } else {
                if (!picked) return toast("Choose a file first");
                const body = new FormData();
                body.append("file", picked);
                Object.entries(form).forEach(([k, v]) => body.append(k, v));
                await apiJson("/api/whatsapp/files", { method: "POST", body });
            }
            toast(file ? "Saved" : "File added");
            onSaved();
        } catch (e) {
            toast((e as Error).message);
        } finally {
            setBusy(false);
        }
    };

    return (
        <Dialog open onClose={onClose} title={file ? "Edit file" : "Add a file"}
                description="JPG or PNG photos up to 5 MB, MP4 videos up to 16 MB, and PDF, Word, Excel or PowerPoint documents up to 30 MB."
                footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button variant="primary" onClick={save} disabled={busy}>{busy ? "Saving…" : file ? "Save" : "Add file"}</Button></>}>
            <div className="space-y-4">
                {!file && (
                    <div>
                        <input ref={input} type="file" accept={ACCEPT} className="sr-only" aria-label="File"
                               onChange={(e) => {
                                   const f = e.target.files?.[0] ?? null;
                                   setPicked(f);
                                   if (f && !form.name) setForm({ ...form, name: f.name.replace(/\.[^.]+$/, "") });
                               }} />
                        <Button onClick={() => input.current?.click()}>{picked ? "Choose another file" : "Choose a file"}</Button>
                        {picked && <span className="ml-3 text-[13px] text-stone-600">{picked.name} · {formatBytes(picked.size)}</span>}
                    </div>
                )}
                <div>
                    <label htmlFor="f-name" className="text-[13px] text-stone-600">Name</label>
                    <Input id="f-name" className="mt-1" maxLength={120} placeholder="Course brochure" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
                </div>
                <div>
                    <label htmlFor="f-when" className="text-[13px] text-stone-600">When should the assistant send it?</label>
                    <Textarea id="f-when" className="mt-1" rows={2} maxLength={500} placeholder="When someone asks about our courses, fees or the syllabus"
                              value={form.when_to_send} onChange={(e) => setForm({ ...form, when_to_send: e.target.value })} />
                </div>
                <div>
                    <label htmlFor="f-caption" className="text-[13px] text-stone-600">Caption <span className="text-stone-400">(optional)</span></label>
                    <Input id="f-caption" className="mt-1" maxLength={1024} placeholder="Our 2026 course brochure" value={form.caption} onChange={(e) => setForm({ ...form, caption: e.target.value })} />
                </div>
                {(bots.data?.length ?? 0) > 1 && (
                    <div>
                        <label htmlFor="f-bot" className="text-[13px] text-stone-600">Which assistant can send it</label>
                        <Select id="f-bot" className="mt-1" value={form.bot_id} onChange={(e) => setForm({ ...form, bot_id: e.target.value })}>
                            <option value="">All assistants</option>
                            {bots.data?.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
                        </Select>
                    </div>
                )}
            </div>
        </Dialog>
    );
}
