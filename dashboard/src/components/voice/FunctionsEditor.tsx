"use client";

import { useState } from "react";
import { CalendarCheck, CalendarSearch, Plus, Trash2, Webhook, X } from "lucide-react";
import { Button, Input, Select, Sheet, Switch, Textarea, cn } from "@/components/ui";
import { apiJson } from "@/lib/api";
import type { AgentDirection, AgentFunction, FunctionParameter } from "@/lib/voice/types";

const KINDS: Record<AgentFunction["kind"], { label: string; about: string; icon: typeof Webhook }> = {
    custom: { label: "Custom function", about: "Calls your own API: look up an order, check stock, create a lead.", icon: Webhook },
    check_slots: { label: "Check calendar", about: "Finds free times on your Cal.com calendar.", icon: CalendarSearch },
    book: { label: "Book on calendar", about: "Books the time the caller picks on your Cal.com calendar.", icon: CalendarCheck },
};
const STARTERS: Record<AgentFunction["kind"], Omit<AgentFunction, "kind">> = {
    custom: { name: "", description: "", enabled: true, speak_during: "One moment, let me check that.", url: "https://", method: "POST",
              parameters: [], headers: [], timeout_sec: 10 },
    check_slots: { name: "check_free_times", description: "When the caller wants to book an appointment, to find free times.",
                   enabled: true, speak_during: "Let me check the calendar.", cal_api_key: "", event_type_id: "", timezone: "Asia/Kolkata" },
    book: { name: "book_appointment", description: "When the caller has picked a time and given their name, to book it.",
            enabled: true, speak_during: "Booking that for you now.", cal_api_key: "", event_type_id: "", timezone: "Asia/Kolkata" },
};
const ZONES = ["Asia/Kolkata", "Asia/Dubai", "Asia/Singapore", "Europe/London", "America/New_York", "America/Los_Angeles", "Australia/Sydney"];
const label = "text-[13px] text-stone-600";

/** The agent's functions: what it can do during a call. Changes go into the page's draft (saved with the agent). */
export function FunctionsEditor({ value, onChange, botId, direction, modelCanRun, modelName }: {
    value: AgentFunction[]; onChange: (v: AgentFunction[]) => void; botId: string; direction: AgentDirection;
    modelCanRun: boolean; modelName?: string;
}) {
    const [editing, setEditing] = useState<{ index: number; fn: AgentFunction } | null>(null);
    const [adding, setAdding] = useState(false);
    const save = (fn: AgentFunction) => {
        if (!editing) return;
        onChange(editing.index < 0 ? [...value, fn] : value.map((f, i) => (i === editing.index ? fn : f)));
        setEditing(null);
    };

    return (
        <div>
            {value.length > 0 && (
                <ul className="divide-y divide-line border border-line rounded-md mb-3">
                    {value.map((f, i) => {
                        const Icon = KINDS[f.kind].icon;
                        return (
                            <li key={f.id ?? `new-${i}`} className="flex items-center gap-3 px-3 py-2.5">
                                <Icon size={15} className="text-stone-500 shrink-0" aria-hidden />
                                <button type="button" onClick={() => setEditing({ index: i, fn: f })} className="flex-1 min-w-0 text-left">
                                    <span className="block text-[13px] font-medium font-mono truncate">{f.name}</span>
                                    <span className="block text-[12px] text-stone-500 truncate">{f.description}</span>
                                </button>
                                <Switch checked={f.enabled} label={`Use ${f.name}`}
                                        onChange={(on) => onChange(value.map((x, j) => (j === i ? { ...x, enabled: on } : x)))} />
                                <button type="button" aria-label={`Remove ${f.name}`} onClick={() => onChange(value.filter((_, j) => j !== i))}
                                        className="p-1.5 rounded text-stone-400 hover:text-signal hover:bg-red-50 focus-visible:outline-2 focus-visible:outline-plum">
                                    <Trash2 size={14} />
                                </button>
                            </li>
                        );
                    })}
                </ul>
            )}
            {adding ? (
                <div className="grid gap-2 sm:grid-cols-3">
                    {(Object.keys(KINDS) as AgentFunction["kind"][]).map((kind) => {
                        const Icon = KINDS[kind].icon;
                        return (
                            <button key={kind} type="button"
                                    onClick={() => { setAdding(false); setEditing({ index: -1, fn: { kind, ...STARTERS[kind] } }); }}
                                    className="text-left p-3 rounded-md border border-line hover:border-plum hover:bg-plum-tint/40 transition-colors focus-visible:outline-2 focus-visible:outline-plum">
                                <Icon size={15} className="text-plum" aria-hidden />
                                <span className="block text-[13px] font-medium mt-1.5">{KINDS[kind].label}</span>
                                <span className="block text-[12px] text-stone-500 mt-0.5 leading-snug">{KINDS[kind].about}</span>
                            </button>
                        );
                    })}
                </div>
            ) : (
                <Button size="sm" onClick={() => setAdding(true)} disabled={value.length >= 15}>
                    <Plus size={13} className="inline mr-1" aria-hidden />Add a function
                </Button>
            )}
            {!modelCanRun && value.some((f) => f.enabled) && (
                <p className="text-[13px] text-amber-700 mt-3">
                    {modelName ?? "This model"} can&apos;t run functions, so turns that need one are answered by a backup model.
                </p>
            )}
            <p className="text-xs text-stone-500 mt-3 leading-relaxed">
                Ending the call and transferring to a person are built in. Calls show each function the agent ran.
            </p>
            {editing && (
                <FunctionSheet key={editing.index} initial={editing.fn} others={value.filter((_, i) => i !== editing.index).map((f) => f.name)}
                               botId={botId} direction={direction} onClose={() => setEditing(null)} onSave={save} />
            )}
        </div>
    );
}

function FunctionSheet({ initial, others, botId, direction, onClose, onSave }: {
    initial: AgentFunction; others: string[]; botId: string; direction: AgentDirection; onClose: () => void; onSave: (fn: AgentFunction) => void;
}) {
    const [fn, setFn] = useState<AgentFunction>(initial);
    const [args, setArgs] = useState(() => JSON.stringify(sampleArguments(initial), null, 2));
    const [test, setTest] = useState<{ busy: boolean; result?: string; ms?: number; error?: string }>({ busy: false });
    const set = <K extends keyof AgentFunction>(key: K, v: AgentFunction[K]) => setFn((f) => ({ ...f, [key]: v }));
    const problem = !/^[a-z][a-z0-9_]{1,47}$/.test(fn.name) ? "Name it with lowercase letters, numbers and underscores, like check_order."
        : others.includes(fn.name) ? "Another function has this name."
        : !fn.description.trim() ? "Say when the agent should use it."
        : fn.kind === "custom" && !/^https?:\/\/[^\s/]+/.test(fn.url ?? "") ? "Add the address it calls."
        : fn.kind !== "custom" && (!fn.cal_api_key || !String(fn.event_type_id ?? "").trim()) ? "Add your Cal.com API key and event type ID."
        : null;

    const runTest = async () => {
        let parsed: Record<string, unknown>;
        try {
            parsed = JSON.parse(args || "{}");
        } catch {
            setTest({ busy: false, error: "The sample arguments aren't valid JSON." });
            return;
        }
        setTest({ busy: true });
        try {
            const r = await apiJson<{ result: string; ms: number }>(`/api/voice/agents/${botId}/functions/test`,
                { method: "POST", json: { function: fn, arguments: parsed, direction } });
            setTest({ busy: false, result: r.result, ms: r.ms });
        } catch (e) {
            setTest({ busy: false, error: (e as Error).message });
        }
    };

    return (
        <Sheet open onClose={onClose} title={initial.name ? `Edit ${initial.name}` : KINDS[fn.kind].label} subtitle={KINDS[fn.kind].about}>
            <div className="px-6 py-5 space-y-5">
                <div className="grid gap-4 sm:grid-cols-2">
                    <div>
                        <label htmlFor="fn-name" className={label}>Name</label>
                        <Input id="fn-name" className="mt-1 font-mono" value={fn.name} placeholder="check_order"
                               onChange={(e) => set("name", e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, "_").slice(0, 48))} />
                    </div>
                    <div>
                        <label htmlFor="fn-during" className={label}>While it runs, say</label>
                        <Input id="fn-during" className="mt-1" value={fn.speak_during} placeholder="Optional"
                               onChange={(e) => set("speak_during", e.target.value.slice(0, 200))} />
                    </div>
                </div>
                <div>
                    <label htmlFor="fn-when" className={label}>When should the agent use it?</label>
                    <Textarea id="fn-when" className="mt-1" rows={2} value={fn.description} maxLength={500}
                              placeholder="When the caller asks where their order is, after they give the order number."
                              onChange={(e) => set("description", e.target.value)} />
                </div>

                {fn.kind === "custom" ? (
                    <>
                        <div>
                            <span className={label}>Request</span>
                            <div className="flex gap-2 mt-1">
                                <Select aria-label="Method" className="w-28 shrink-0" value={fn.method}
                                        onChange={(e) => set("method", e.target.value as AgentFunction["method"])}>
                                    {["GET", "POST", "PUT", "PATCH", "DELETE"].map((m) => <option key={m}>{m}</option>)}
                                </Select>
                                <Input aria-label="Address" className="font-mono text-[13px]" value={fn.url ?? ""}
                                       onChange={(e) => set("url", e.target.value)} placeholder="https://api.example.com/orders" />
                            </div>
                            <p className="text-xs text-stone-500 mt-1.5">
                                {fn.method === "GET" || fn.method === "DELETE" ? "Arguments go in the query." : "Arguments are sent as JSON."}{" "}
                                {"{{caller_number}}"}, {"{{name}}"} and campaign columns work in the address and headers.
                            </p>
                        </div>
                        <ParametersEditor value={fn.parameters ?? []} onChange={(v) => set("parameters", v)} />
                        <HeadersEditor value={fn.headers ?? []} onChange={(v) => set("headers", v)} />
                        <div>
                            <label htmlFor="fn-timeout" className={label}>Wait for an answer</label>
                            <Select id="fn-timeout" className="mt-1 max-w-40" value={fn.timeout_sec ?? 10}
                                    onChange={(e) => set("timeout_sec", Number(e.target.value))}>
                                {[5, 10, 15, 20, 30].map((s) => <option key={s} value={s}>{s} seconds</option>)}
                            </Select>
                        </div>
                    </>
                ) : (
                    <div className="grid gap-4 sm:grid-cols-2">
                        <div className="sm:col-span-2">
                            <label htmlFor="fn-cal-key" className={label}>Cal.com API key</label>
                            <Input id="fn-cal-key" type="password" autoComplete="off" className="mt-1 font-mono" value={fn.cal_api_key ?? ""}
                                   placeholder="cal_live_…" onChange={(e) => set("cal_api_key", e.target.value)} />
                            <p className="text-xs text-stone-500 mt-1">In Cal.com: Settings, Developer, API keys. It&apos;s stored encrypted.</p>
                        </div>
                        <div>
                            <label htmlFor="fn-event" className={label}>Event type ID</label>
                            <Input id="fn-event" inputMode="numeric" className="mt-1 tabular-nums" value={String(fn.event_type_id ?? "")}
                                   onChange={(e) => set("event_type_id", e.target.value.replace(/\D/g, ""))} placeholder="123456" />
                        </div>
                        <div>
                            <label htmlFor="fn-zone" className={label}>Time zone</label>
                            <Select id="fn-zone" className="mt-1" value={fn.timezone ?? "Asia/Kolkata"} onChange={(e) => set("timezone", e.target.value)}>
                                {ZONES.map((z) => <option key={z}>{z}</option>)}
                            </Select>
                        </div>
                    </div>
                )}

                <div className="rounded-md border border-line bg-stone-50/70 p-3">
                    <label htmlFor="fn-args" className="text-[13px] font-medium">Test it</label>
                    <p className="text-xs text-stone-500 mt-0.5">
                        Runs it now with these arguments, as on a call from +91 98765 43210.
                        {fn.kind === "book" && " This books a real appointment on your calendar."}
                        {fn.kind === "custom" && fn.method !== "GET" && " Your API receives a real request."}
                    </p>
                    <Textarea id="fn-args" className="mt-2 font-mono text-[12px]" rows={4} value={args} onChange={(e) => setArgs(e.target.value)} />
                    <div className="flex items-center gap-3 mt-2">
                        <Button size="sm" onClick={runTest} disabled={test.busy || !!problem}>{test.busy ? "Running…" : "Run test"}</Button>
                        {test.ms !== undefined && <span className="text-xs text-stone-500 tabular-nums">{test.ms} ms</span>}
                    </div>
                    {(test.result || test.error) && (
                        <pre className={cn("mt-2 p-2.5 rounded bg-white border border-line text-[12px] whitespace-pre-wrap break-words max-h-48 overflow-auto",
                                           test.error && "text-signal")}>{test.error ?? test.result}</pre>
                    )}
                </div>
            </div>
            <div className="sticky bottom-0 flex items-center justify-between gap-3 px-6 py-3 border-t border-line bg-white">
                <p className="text-[13px] text-amber-700 min-w-0">{problem}</p>
                <div className="flex gap-2 shrink-0">
                    <Button variant="ghost" onClick={onClose}>Cancel</Button>
                    <Button variant="primary" disabled={!!problem} onClick={() => onSave(fn)}>Done</Button>
                </div>
            </div>
        </Sheet>
    );
}

function ParametersEditor({ value, onChange }: { value: FunctionParameter[]; onChange: (v: FunctionParameter[]) => void }) {
    const update = (i: number, patch: Partial<FunctionParameter>) => onChange(value.map((p, j) => (j === i ? { ...p, ...patch } : p)));
    return (
        <div>
            <span className={label}>What it needs from the caller</span>
            <p className="text-xs text-stone-500">The agent asks the caller for these before running it.</p>
            {value.length > 0 && (
                <ul className="space-y-2 mt-2">
                    {value.map((p, i) => (
                        <li key={i} className="rounded-md border border-line p-2.5">
                            <div className="grid grid-cols-[minmax(0,1fr)_7.5rem_auto] gap-2 items-center">
                                <Input aria-label="Parameter name" className="font-mono text-[13px]" value={p.name} placeholder="order_id"
                                       onChange={(e) => update(i, { name: e.target.value.replace(/[^A-Za-z0-9_]/g, "_").slice(0, 40) })} />
                                <Select aria-label="Type" value={p.type} onChange={(e) => update(i, { type: e.target.value as FunctionParameter["type"] })}>
                                    <option value="string">Text</option>
                                    <option value="number">Number</option>
                                    <option value="boolean">Yes / no</option>
                                    <option value="enum">One of a list</option>
                                </Select>
                                <button type="button" aria-label="Remove parameter" onClick={() => onChange(value.filter((_, j) => j !== i))}
                                        className="p-1.5 rounded text-stone-400 hover:text-ink"><X size={14} /></button>
                            </div>
                            <Input aria-label="What it is" className="mt-2 text-[13px]" value={p.description} placeholder="What it is, e.g. the order number"
                                   onChange={(e) => update(i, { description: e.target.value.slice(0, 200) })} />
                            {p.type === "enum" && (
                                <Input aria-label="Choices" className="mt-2 text-[13px]" value={p.choices.join(", ")} placeholder="Choices, separated by commas"
                                       onChange={(e) => update(i, { choices: e.target.value.split(",").map((c) => c.trimStart()) })} />
                            )}
                            <label className="flex items-center gap-2 mt-2 text-[13px] text-stone-600">
                                <input type="checkbox" className="accent-plum" checked={p.required} onChange={(e) => update(i, { required: e.target.checked })} />
                                Required
                            </label>
                        </li>
                    ))}
                </ul>
            )}
            <Button size="sm" variant="ghost" className="mt-1.5" disabled={value.length >= 12}
                    onClick={() => onChange([...value, { name: "", type: "string", description: "", required: true, choices: [] }])}>
                <Plus size={13} className="inline mr-1" aria-hidden />Add what it needs
            </Button>
        </div>
    );
}

function HeadersEditor({ value, onChange }: { value: { name: string; value: string }[]; onChange: (v: { name: string; value: string }[]) => void }) {
    const update = (i: number, patch: Partial<{ name: string; value: string }>) => onChange(value.map((h, j) => (j === i ? { ...h, ...patch } : h)));
    return (
        <div>
            <span className={label}>Headers</span>
            <p className="text-xs text-stone-500">For your API key, for example. Values are stored encrypted.</p>
            {value.map((h, i) => (
                <div key={i} className="grid grid-cols-[10rem_minmax(0,1fr)_auto] gap-2 mt-2 items-center">
                    <Input aria-label="Header name" className="font-mono text-[13px]" value={h.name} placeholder="Authorization"
                           onChange={(e) => update(i, { name: e.target.value.replace(/[^A-Za-z0-9-]/g, "").slice(0, 60) })} />
                    <Input aria-label="Header value" type="password" autoComplete="off" className="font-mono text-[13px]" value={h.value}
                           placeholder="Bearer …" onChange={(e) => update(i, { value: e.target.value })} />
                    <button type="button" aria-label="Remove header" onClick={() => onChange(value.filter((_, j) => j !== i))}
                            className="p-1.5 rounded text-stone-400 hover:text-ink"><X size={14} /></button>
                </div>
            ))}
            <Button size="sm" variant="ghost" className="mt-1.5" disabled={value.length >= 10}
                    onClick={() => onChange([...value, { name: "", value: "" }])}>
                <Plus size={13} className="inline mr-1" aria-hidden />Add a header
            </Button>
        </div>
    );
}

function sampleArguments(fn: AgentFunction): Record<string, unknown> {
    if (fn.kind === "check_slots") {
        const today = new Date().toISOString().slice(0, 10);
        return { start_date: today };
    }
    if (fn.kind === "book") {
        const tomorrow = new Date(Date.now() + 86_400_000).toISOString().slice(0, 10);
        return { start: `${tomorrow}T11:00`, name: "Test Caller", email: "test@example.com" };
    }
    return Object.fromEntries((fn.parameters ?? []).map((p) => [p.name, p.type === "number" ? 1 : p.type === "boolean" ? true : p.choices[0] ?? "sample"]));
}
