"use client";

import { useRef, useState } from "react";
import { FileArchive, FolderUp, UploadCloud } from "lucide-react";
import { apiUrl, authHeaders } from "@/lib/api";
import { Button, cn } from "@/components/ui";
import { formatBytes } from "@/lib/plan";
import { skipPath, type Deploy } from "./shared";

type Limits = { deploy_bytes: number; deploy_files: number; file_bytes: number };
type Picked = { kind: "zip"; file: File } | { kind: "files"; files: { path: string; file: File }[]; skipped: number };

/* ---------- reading a dropped folder ---------- */
type Entry = { isFile: boolean; isDirectory: boolean; name: string; fullPath: string };
type FileEntry = Entry & { file: (ok: (f: File) => void, fail: (e: unknown) => void) => void };
type DirEntry = Entry & { createReader: () => { readEntries: (ok: (e: Entry[]) => void, fail: (e: unknown) => void) => void } };

async function walk(entry: Entry, out: { path: string; file: File }[]) {
    if (entry.isFile) {
        const file = await new Promise<File>((ok, fail) => (entry as FileEntry).file(ok, fail));
        out.push({ path: entry.fullPath.replace(/^\//, ""), file });
    } else if (entry.isDirectory) {
        if (skipPath(`${entry.fullPath.replace(/^\//, "")}/x`)) return; // don't even read node_modules
        const reader = (entry as DirEntry).createReader();
        for (;;) { // readEntries returns at most ~100 at a time
            const batch = await new Promise<Entry[]>((ok, fail) => reader.readEntries(ok, fail));
            if (!batch.length) break;
            for (const child of batch) await walk(child, out);
        }
    }
}

function fromList(list: { path: string; file: File }[]): Picked {
    const kept = list.filter((f) => !skipPath(f.path));
    return { kind: "files", files: kept, skipped: list.length - kept.length };
}

/** A folder or .zip, dropped or chosen, uploaded with progress. The server publishes it in the background. */
export default function Uploader({ siteId, limits, disabled, onStarted }: {
    siteId: string; limits: Limits; disabled?: boolean; onStarted: (d: Deploy) => void;
}) {
    const folderInput = useRef<HTMLInputElement>(null);
    const zipInput = useRef<HTMLInputElement>(null);
    const [over, setOver] = useState(false);
    const [progress, setProgress] = useState<number | null>(null);
    const [error, setError] = useState<string | null>(null);

    const check = (picked: Picked): string | null => {
        if (picked.kind === "zip") {
            if (!/\.zip$/i.test(picked.file.name)) return "Choose a .zip file, or drop the folder itself.";
            if (picked.file.size > limits.deploy_bytes) return `That .zip is ${formatBytes(picked.file.size)}; your plan allows ${formatBytes(limits.deploy_bytes)} per deployment.`;
            return null;
        }
        if (!picked.files.length) return "That folder has no files to publish.";
        if (picked.files.length > limits.deploy_files) return `That's ${picked.files.length.toLocaleString("en-IN")} files; your plan allows ${limits.deploy_files.toLocaleString("en-IN")}.`;
        const big = picked.files.find((f) => f.file.size > limits.file_bytes);
        if (big) return `${big.path} is ${formatBytes(big.file.size)}; files can be up to ${formatBytes(limits.file_bytes)}.`;
        const total = picked.files.reduce((n, f) => n + f.file.size, 0);
        if (total > limits.deploy_bytes) return `Those files are ${formatBytes(total)}; your plan allows ${formatBytes(limits.deploy_bytes)} per deployment.`;
        if (!picked.files.some((f) => /(^|\/)index\.html?$/i.test(f.path))) return "There's no index.html in that folder. Choose the folder that has your home page in it.";
        return null;
    };

    const upload = (picked: Picked) => {
        setError(null);
        const problem = check(picked);
        if (problem) return setError(problem);
        const form = new FormData();
        if (picked.kind === "zip") form.append("archive", picked.file);
        else picked.files.forEach(({ path, file }) => { form.append("files", file); form.append("paths", path); });

        const xhr = new XMLHttpRequest();
        xhr.open("POST", apiUrl(`/api/sites/${siteId}/deploys`));
        Object.entries(authHeaders()).forEach(([k, v]) => xhr.setRequestHeader(k, v));
        xhr.upload.onprogress = (e) => e.lengthComputable && setProgress(Math.round((e.loaded / e.total) * 100));
        xhr.onload = () => {
            setProgress(null);
            let body: { detail?: unknown } & Partial<Deploy> = {};
            try { body = JSON.parse(xhr.responseText); } catch { /* not JSON */ }
            if (xhr.status >= 200 && xhr.status < 300) onStarted(body as Deploy);
            else setError(typeof body.detail === "string" ? body.detail : xhr.status === 413 ? "That upload is too large for your plan." : "The upload didn't go through. Try again.");
        };
        xhr.onerror = () => { setProgress(null); setError("The upload didn't go through. Check your connection and try again."); };
        setProgress(0);
        xhr.send(form);
    };

    const onDrop = async (e: React.DragEvent) => {
        e.preventDefault();
        setOver(false);
        if (disabled || progress !== null) return;
        const items = Array.from(e.dataTransfer.items || []);
        const entries = items.map((i) => (i as DataTransferItem & { webkitGetAsEntry?: () => Entry | null }).webkitGetAsEntry?.()).filter(Boolean) as Entry[];
        const files = Array.from(e.dataTransfer.files || []);
        if (files.length === 1 && entries.length <= 1 && /\.zip$/i.test(files[0].name)) return upload({ kind: "zip", file: files[0] });
        if (entries.length) {
            const out: { path: string; file: File }[] = [];
            try {
                for (const entry of entries) await walk(entry, out);
            } catch {
                return setError("We couldn't read that folder. Try choosing it with the button instead.");
            }
            return upload(fromList(out));
        }
        upload(fromList(files.map((file) => ({ path: file.name, file }))));
    };

    const busy = progress !== null;
    return (
        <div>
            <div
                onDragOver={(e) => { e.preventDefault(); if (!disabled) setOver(true); }}
                onDragLeave={() => setOver(false)}
                onDrop={onDrop}
                className={cn("rounded-lg border-2 border-dashed px-6 py-10 text-center transition-colors",
                              over ? "border-plum bg-plum-tint" : "border-line-strong bg-stone-50/60", disabled && "opacity-60")}
            >
                <UploadCloud size={28} className={cn("mx-auto", over ? "text-plum" : "text-stone-400")} aria-hidden />
                {busy ? (
                    <div className="mt-3 max-w-xs mx-auto" role="status">
                        <p className="text-sm font-medium">{progress! < 100 ? `Uploading… ${progress}%` : "Uploaded. Publishing…"}</p>
                        <div className="mt-2 h-1.5 rounded-full bg-stone-200 overflow-hidden">
                            <div className="h-full bg-plum transition-[width] duration-200" style={{ width: `${progress}%` }} />
                        </div>
                    </div>
                ) : (
                    <>
                        <p className="mt-3 text-sm font-medium">Drag your site&apos;s folder or a .zip here</p>
                        <p className="mt-1 text-[13px] text-stone-500">
                            The folder with your index.html. Up to {formatBytes(limits.deploy_bytes)} and {limits.deploy_files.toLocaleString("en-IN")} files;
                            node_modules, .git and .env files are left out.
                        </p>
                        <div className="mt-4 flex flex-wrap justify-center gap-2">
                            <Button onClick={() => folderInput.current?.click()} disabled={disabled}><FolderUp size={15} /> Choose folder</Button>
                            <Button onClick={() => zipInput.current?.click()} disabled={disabled}><FileArchive size={15} /> Choose .zip</Button>
                        </div>
                    </>
                )}
            </div>
            {error && <p role="alert" className="mt-2 text-[13px] text-signal">{error}</p>}
            <input ref={folderInput} type="file" className="hidden" multiple
                   {...({ webkitdirectory: "", directory: "" } as Record<string, string>)}
                   onChange={(e) => {
                       const list = Array.from(e.target.files || []).map((file) => ({ path: (file as File & { webkitRelativePath: string }).webkitRelativePath || file.name, file }));
                       e.target.value = "";
                       if (list.length) upload(fromList(list));
                   }} />
            <input ref={zipInput} type="file" accept=".zip,application/zip" className="hidden"
                   onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) upload({ kind: "zip", file: f }); }} />
        </div>
    );
}
