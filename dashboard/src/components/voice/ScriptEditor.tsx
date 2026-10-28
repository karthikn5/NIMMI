"use client";

import { useState } from "react";
import { Lock, Sparkles } from "lucide-react";
import { FieldsEditor } from "@/components/voice/AgentEditors";
import { WithPlaceholders } from "@/components/voice/CampaignBits";
import WriteWithAI from "@/components/voice/WriteWithAI";
import { Button, Card, Input, SaveBar, SettingRow, Skeleton, Textarea, cn, useToast } from "@/components/ui";
import { useApi, useDraft } from "@/lib/useApi";
import { LANGUAGES, getDisclosureText } from "@/lib/voice/api";
import type { AgentDirection, VoiceScript } from "@/lib/voice/types";

const PERSONALITIES: { value: string; label: string }[] = [
    { value: "friendly", label: "Friendly" },
    { value: "professional", label: "Professional" },
    { value: "caring", label: "Caring" },
    { value: "cheerful", label: "Cheerful" },
    { value: "formal", label: "Formal" },
    { value: "playful", label: "Playful" },
];

const INSTRUCTIONS_EXAMPLE: Record<AgentDirection, string> = {
    inbound: "1. Find out what they're calling about.\n2. Answer from what you know; if you don't know, offer a call back from the team.\n3. Before ending, take their name and a good time to call back.\nRules: never promise discounts. If they're upset, offer to connect them to the team.",
    outbound: "1. Remind them they asked for a call on our website.\n2. Ask if now is a good time; if not, ask for a better time and end the call.\n3. Answer their questions and offer a demo.\nRules: never pressure them. If they're not interested, thank them and end the call.",
};

/** What one agent says: its opening, personality, how it handles calls, its goal and what it finds out. */
export default function ScriptEditor({ botId, direction }: { botId: string; direction: AgentDirection }) {
    const toast = useToast();
    const url = `/api/voice/scripts/${botId}/${direction}`;
    const script = useApi<VoiceScript>(url);
    const { draft, setDraft, dirty, saving, save, discard } = useDraft(script, url);
    const [writing, setWriting] = useState(false);

    if (script.loading || !draft) {
        return script.error
            ? <p className="text-sm text-signal">Couldn&apos;t load the script. {script.error}</p>
            : <div className="space-y-4">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-24" />)}</div>;
    }

    const set = <K extends keyof VoiceScript>(key: K, value: VoiceScript[K]) => setDraft({ ...draft, [key]: value });
    const preset = PERSONALITIES.some((p) => p.value === draft.personality);
    const disclosure = getDisclosureText(draft.language, draft.assistant_name, draft.company_name);
    const language = LANGUAGES.find((l) => l.code === draft.language)?.label || draft.language;
    const kind = direction === "inbound" ? "incoming" : "outgoing";

    return (
        <>
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
                <p className="text-[13px] text-stone-500 max-w-xl">
                    {direction === "inbound"
                        ? "What the assistant says when people call your number."
                        : "What the assistant says when it calls people back or runs a campaign."}
                    {!draft.saved && " Until you save this, it uses the opening line, goal and details from before."}
                </p>
                <Button onClick={() => setWriting(true)}>
                    <Sparkles size={14} className="inline mr-1.5 -mt-0.5" aria-hidden />Write with AI
                </Button>
            </div>

            <Card className="px-5 py-1">
                <SettingRow label="Personality" hint="How it comes across on the phone.">
                    <div role="radiogroup" aria-label="Personality" className="flex flex-wrap gap-1.5">
                        {PERSONALITIES.map((p) => (
                            <button
                                key={p.value}
                                type="button"
                                role="radio"
                                aria-checked={draft.personality === p.value}
                                onClick={() => set("personality", p.value)}
                                className={cn(
                                    "h-8 px-3 rounded-full border text-[13px] transition-colors focus-visible:outline-2 focus-visible:outline-plum",
                                    draft.personality === p.value ? "border-plum bg-plum-tint text-plum" : "border-line text-stone-600 hover:border-line-strong",
                                )}
                            >
                                {p.label}
                            </button>
                        ))}
                    </div>
                    <label htmlFor={`personality-${direction}`} className="block text-[13px] text-stone-600 mt-3">Or in your own words</label>
                    <Input id={`personality-${direction}`} className="mt-1" maxLength={300} value={preset ? "" : draft.personality}
                           placeholder="e.g. warm and patient, like our front desk"
                           onChange={(e) => set("personality", e.target.value)} />
                </SettingRow>

                <SettingRow label="Opening line" hint="Said straight after the required line about being automated and recorded.">
                    <Input aria-label="Opening line" maxLength={300} value={draft.greeting} onChange={(e) => set("greeting", e.target.value)}
                           placeholder="e.g. Thanks for calling. How can I help you today?" />
                    <label htmlFor={`known-${direction}`} className="block text-[13px] text-stone-600 mt-3">For someone it has spoken to before</label>
                    <Input id={`known-${direction}`} className="mt-1" maxLength={300} value={draft.greeting_known}
                           onChange={(e) => set("greeting_known", e.target.value)} placeholder="e.g. Hello {{name}}, how can I help you today?" />
                    <p className="text-xs text-stone-500 mt-1.5">
                        <code className="text-[11px] bg-stone-100 rounded px-1">{"{{name}}"}</code> becomes their first name. Leave it empty to use the opening line above.
                    </p>
                    <figure className="mt-4 rounded-md bg-stone-50 border border-line px-4 py-3 space-y-2">
                        <figcaption className="text-xs text-stone-500">Callers hear in {language}</figcaption>
                        <blockquote className="text-sm leading-relaxed">
                            <span className="text-stone-500"><Lock size={11} className="inline -mt-0.5 mr-1" aria-label="Required" />{disclosure}</span>{" "}
                            <span className="text-ink font-medium"><WithPlaceholders text={draft.greeting} /></span>
                        </blockquote>
                        {draft.greeting_known.trim() && (
                            <blockquote className="text-sm leading-relaxed border-t border-line pt-2">
                                <span className="block text-xs text-stone-500 mb-0.5">Someone it knows, like Arjun:</span>
                                <span className="text-stone-500">{disclosure}</span>{" "}
                                <span className="text-ink font-medium">{draft.greeting_known.replace(/\{\{\s*name\s*\}\}/gi, "Arjun")}</span>
                            </blockquote>
                        )}
                    </figure>
                </SettingRow>
            </Card>

            <Card className="px-5 py-1 mt-6">
                <SettingRow label={`How to handle ${kind} calls`} htmlFor={`instructions-${direction}`}
                            hint="Steps and rules in plain words. It answers from the assistant's knowledge and follows these.">
                    <Textarea id={`instructions-${direction}`} rows={10} maxLength={4000} value={draft.instructions}
                              placeholder={INSTRUCTIONS_EXAMPLE[direction]} onChange={(e) => set("instructions", e.target.value)} />
                    <p className="text-xs text-stone-500 mt-1 text-right tabular-nums">{draft.instructions.length.toLocaleString("en-IN")} / 4,000</p>
                </SettingRow>
                <SettingRow label="Goal of the call" htmlFor={`goal-${direction}`}
                            hint="After every call, the assistant judges whether this happened. You'll see it as Successful in Calls and Collected data.">
                    <Textarea id={`goal-${direction}`} rows={2} maxLength={500} value={draft.call_goal}
                              placeholder="e.g. The caller books a site visit, or agrees to a call from our sales team"
                              onChange={(e) => set("call_goal", e.target.value)} />
                </SettingRow>
                <SettingRow label="Information to collect"
                            hint="It asks for these naturally during the call. After the call they're saved in Collected data and the caller's contact, and sent to your webhook.">
                    <FieldsEditor value={draft.collect_fields} onChange={(v) => set("collect_fields", v)} />
                </SettingRow>
            </Card>

            <WriteWithAI
                open={writing}
                onClose={() => setWriting(false)}
                botId={botId}
                direction={direction}
                previous={draft.answers}
                onDraft={(written, answers) => {
                    setDraft({ ...draft, ...written, answers });
                    toast("Script written. Check it, change anything you like, then save.");
                }}
            />
            <SaveBar visible={dirty} saving={saving} onDiscard={discard} onSave={async () => toast(await save())} />
        </>
    );
}
