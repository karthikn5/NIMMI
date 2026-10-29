"use client";

import { useEffect, useState } from "react";
import { Check, Copy } from "lucide-react";
import { Button, Card, Input } from "@/components/ui";
import { apiBase, apiJson } from "@/lib/api";

/**
 * Profile > Nimmi in your AI apps: keys that let Claude, ChatGPT or an editor use Nimmi's tools over MCP as this
 * person, in this workspace (backend/agent/mcp.py). A key is shown once; only its hash is kept.
 */
type Key = { id: string; name: string; prefix: string; created_at: string; last_used_at: string | null };

export default function AgentKeys() {
    const [keys, setKeys] = useState<Key[] | null>(null);
    const [name, setName] = useState("");
    const [fresh, setFresh] = useState<string | null>(null);
    const [error, setError] = useState("");
    const [copied, setCopied] = useState("");
    const url = `${apiBase()}/mcp`;
    const load = () => apiJson<Key[]>("/api/agent/keys").then(setKeys).catch((e: Error) => setError(e.message));
    useEffect(() => { void load(); }, []);

    const create = async () => {
        setError("");
        try {
            const made = await apiJson<{ key: string }>("/api/agent/keys", { method: "POST", json: { name: name.trim() || "My AI app" } });
            setFresh(made.key);
            setName("");
            void load();
        } catch (e) { setError((e as Error).message); }
    };
    const revoke = async (id: string) => {
        try { await apiJson(`/api/agent/keys/${id}`, { method: "DELETE" }); void load(); } catch (e) { setError((e as Error).message); }
    };
    const copy = (label: string, value: string) => navigator.clipboard.writeText(value).then(() => { setCopied(label); setTimeout(() => setCopied(""), 1500); });
    const command = `claude mcp add --transport http nimmi ${url} --header "Authorization: Bearer ${fresh ?? "<your key>"}"`;

    return (
        <section className="mt-10">
            <h2 className="text-[15px] font-semibold">Nimmi in your AI apps</h2>
            <p className="text-[13px] text-stone-500 mt-1 mb-4">
                Let Claude, ChatGPT or your editor work in your Nimmi workspace with the same tools as the Nimmi panel, as you.
                Changes can be undone in Nimmi, and anything risky waits for your Confirm in the Nimmi panel.
            </p>
            <Card className="px-5 py-4 space-y-4">
                <div>
                    <p className="text-sm font-medium">Server address (MCP)</p>
                    <div className="mt-1.5 flex gap-2">
                        <Input readOnly value={url} className="font-mono text-xs" aria-label="MCP server address" />
                        <Button aria-label="Copy the address" onClick={() => copy("url", url)}>{copied === "url" ? <Check size={14} /> : <Copy size={14} />}</Button>
                    </div>
                </div>
                {fresh && (
                    <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2.5">
                        <p className="text-[13px] font-medium text-amber-900">Your new key. Copy it now: it won&apos;t be shown again.</p>
                        <div className="mt-1.5 flex gap-2">
                            <Input readOnly value={fresh} className="font-mono text-xs" aria-label="Your new key" />
                            <Button aria-label="Copy the key" onClick={() => copy("key", fresh)}>{copied === "key" ? <Check size={14} /> : <Copy size={14} />}</Button>
                        </div>
                    </div>
                )}
                <div>
                    <p className="text-sm font-medium">Add it to Claude Code</p>
                    <div className="mt-1.5 flex gap-2">
                        <Input readOnly value={command} className="font-mono text-xs" aria-label="Command for Claude Code" />
                        <Button aria-label="Copy the command" onClick={() => copy("cmd", command)}>{copied === "cmd" ? <Check size={14} /> : <Copy size={14} />}</Button>
                    </div>
                    <p className="text-[12px] text-stone-500 mt-1.5">Other apps (Claude Desktop, Cursor, VS Code): add a remote MCP server with this address and the header Authorization: Bearer and your key.</p>
                </div>
                <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); void create(); }}>
                    <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Name it, e.g. Claude on my laptop" maxLength={80} aria-label="Key name" />
                    <Button type="submit" variant="primary">Create a key</Button>
                </form>
                {error && <p role="alert" className="text-[13px] text-signal">{error}</p>}
                {keys && keys.length > 0 && (
                    <ul className="divide-y divide-line border-t border-line">
                        {keys.map((k) => (
                            <li key={k.id} className="flex items-center gap-3 py-2.5">
                                <div className="min-w-0 flex-1">
                                    <p className="text-[13px] font-medium truncate">{k.name} <span className="font-mono text-stone-400">{k.prefix}…</span></p>
                                    <p className="text-[12px] text-stone-500">
                                        Made {new Date(k.created_at).toLocaleDateString("en-IN", { dateStyle: "medium" })}
                                        {k.last_used_at ? ` · last used ${new Date(k.last_used_at).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" })}` : " · not used yet"}
                                    </p>
                                </div>
                                <Button size="sm" variant="ghost" onClick={() => revoke(k.id)}>Revoke</Button>
                            </li>
                        ))}
                    </ul>
                )}
            </Card>
        </section>
    );
}
