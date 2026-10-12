"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, Lock, Play } from "lucide-react";
import BrowserTest from "@/components/voice/BrowserTest";
import { AmbiencePicker, FieldsEditor, PronunciationEditor } from "@/components/voice/AgentEditors";
import { WithPlaceholders } from "@/components/voice/CampaignBits";
import PhoneTest from "@/components/voice/PhoneTest";
import {
    Card, Input, PhraseInput, SaveBar, Segmented, Select, SettingRow, Skeleton, Switch, Textarea, cn, useToast,
} from "@/components/ui";
import { useRef } from "react";
import { apiUrl } from "@/lib/api";
import { useApi, useDraft } from "@/lib/useApi";
import { DEFAULT_GREETINGS, LANGUAGES, getDisclosureText } from "@/lib/voice/api";
import type { Voice, VoiceAgentConfig } from "@/lib/voice/types";

export default function AgentSettingsPage() {
    const { botId } = useParams<{ botId: string }>();
    const toast = useToast();
    const config = useApi<VoiceAgentConfig>(`/api/voice/agents/${botId}`);
    const voices = useApi<Voice[]>("/api/voice/voices");
    const { draft, setDraft, dirty, saving, save, discard } = useDraft(config, `/api/voice/agents/${botId}`);
    const player = useRef<HTMLAudioElement | null>(null);

    if (config.loading || !draft) {
        return config.error
            ? <p className="text-sm text-signal">Couldn&apos;t load this agent. {config.error}</p>
            : <div className="space-y-6"><Skeleton className="h-10 w-64" /><Skeleton className="h-96" /></div>;
    }

    const set = <K extends keyof VoiceAgentConfig>(key: K, value: VoiceAgentConfig[K]) => setDraft({ ...draft, [key]: value });

    const handleLanguageChange = (newLang: VoiceAgentConfig["language"]) => {
        const currentGreeting = (draft.greeting || "").trim().toLowerCase();
        const isDefaultGreeting =
            !currentGreeting ||
            currentGreeting.includes("how can i help you") ||
            Object.values(DEFAULT_GREETINGS).some((g) => g.trim().toLowerCase() === currentGreeting);

        const newGreeting = isDefaultGreeting ? (DEFAULT_GREETINGS[newLang] || draft.greeting) : draft.greeting;
        setDraft({ ...draft, language: newLang, greeting: newGreeting });
    };

    const playSample = (v: Voice) => {
        if (!v.sample_url) return;
        player.current?.pause();
        const audio = new Audio(apiUrl(`${v.sample_url}?language=${draft.language}`));
        player.current = audio;
        audio.play().catch(() => toast("Couldn't play the sample. The voice engine may not be connected yet."));
    };

    return (
        <>
            <Link href="/dashboard/voice/agents" className="inline-flex items-center gap-1.5 text-[13px] text-stone-500 hover:text-ink">
                <ArrowLeft size={14} /> Agents
            </Link>

            <div className="flex flex-wrap items-center justify-between gap-4 mt-3 mb-6">
                <h2 className="text-xl font-semibold tracking-tight">{draft.bot_name}</h2>
                <label className="flex items-center gap-3 text-sm">
                    <span className="text-stone-600">{draft.enabled ? "Taking calls" : "Voice off"}</span>
                    <Switch checked={draft.enabled} onChange={(v) => set("enabled", v)} label="Take calls with this assistant" />
                </label>
            </div>

            <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_340px] items-start">
                <div className="space-y-6 min-w-0">
                    <Card className="px-5 py-1">
                        <SettingRow label="Language" htmlFor="language" hint="The assistant speaks and listens in this language.">
                            <Select id="language" value={draft.language} onChange={(e) => handleLanguageChange(e.target.value as VoiceAgentConfig["language"])}>
                                {LANGUAGES.map((l) => <option key={l.code} value={l.code}>{l.label}</option>)}
                            </Select>
                            <label className="flex items-start gap-3 mt-4">
                                <Switch checked={draft.understand_code_mixed} onChange={(v) => set("understand_code_mixed", v)} label="Understand mixed language" />
                                <span className="text-[13px] text-stone-600 leading-snug">
                                    Understand callers who mix in English, like Tanglish or Hinglish
                                </span>
                            </label>
                            <div className="mt-3.5 flex items-start gap-2.5 p-3 rounded-md bg-stone-50 border border-line text-xs text-stone-600 leading-relaxed">
                                <span className="h-2 w-2 rounded-full bg-emerald-500 mt-1 shrink-0" aria-hidden />
                                <div>
                                    <strong className="text-stone-800 font-semibold">Human-like Spoken Register Active:</strong>
                                    {" "}Speaks in natural colloquial vernacular ({LANGUAGES.find((l) => l.code === draft.language)?.label || draft.language}) with realistic human listening cues (&quot;ஹ்ம்ம்...&quot;, &quot;சரிங்க...&quot;, &quot;ஆமா...&quot;, &quot;Hmm...&quot;, &quot;Ah...&quot;) and natural conversational breathing pauses.
                                </div>
                            </div>
                        </SettingRow>

                        <SettingRow label="Voice" hint="Pick the voice that suits your business. You can change it any time.">
                            <div role="radiogroup" aria-label="Voice" className="grid sm:grid-cols-2 gap-2">
                                {(voices.data ?? []).map((v) => {
                                    const selected = draft.voice_id === v.id;
                                    return (
                                        <div
                                            key={v.id}
                                            className={cn(
                                                "flex items-center gap-2 pl-3 pr-1.5 py-2 rounded-md border transition-colors",
                                                selected ? "border-plum bg-plum-tint" : "border-line hover:border-line-strong",
                                            )}
                                        >
                                            <button
                                                type="button"
                                                role="radio"
                                                aria-checked={selected}
                                                onClick={() => set("voice_id", v.id)}
                                                className="flex-1 text-left min-w-0 focus-visible:outline-none"
                                            >
                                                <span className="block text-sm font-medium">{v.name}</span>
                                                <span className="block text-xs text-stone-500">{v.gender === "female" ? "Female" : "Male"}{v.tone ? ` · ${v.tone}` : ""}</span>
                                            </button>
                                            <button
                                                type="button"
                                                onClick={() => playSample(v)}
                                                aria-label={`Play ${v.name}`}
                                                className="p-2 rounded text-stone-500 hover:text-plum hover:bg-white focus-visible:outline-2 focus-visible:outline-plum"
                                            >
                                                <Play size={13} />
                                            </button>
                                        </div>
                                    );
                                })}
                            </div>
                        </SettingRow>

                        <SettingRow label="Speaking speed">
                            <Segmented
                                label="Speaking speed"
                                value={String(draft.speaking_rate)}
                                onChange={(v) => set("speaking_rate", Number(v))}
                                options={[{ value: "0.9", label: "Slower" }, { value: "1", label: "Normal" }, { value: "1.1", label: "Faster" }]}
                            />
                        </SettingRow>
                    </Card>

                    <Card className="px-5 py-1">
                        <SettingRow
                            label="Opening line"
                            hint="Every call starts by saying it's automated and may be recorded. That part can't be removed."
                        >
                            <div className="grid sm:grid-cols-2 gap-3">
                                <div>
                                    <label htmlFor="assistant_name" className="text-[13px] text-stone-600">Assistant name</label>
                                    <Input id="assistant_name" className="mt-1" value={draft.assistant_name} onChange={(e) => set("assistant_name", e.target.value)} />
                                </div>
                                <div>
                                    <label htmlFor="company" className="text-[13px] text-stone-600">Business name</label>
                                    <Input id="company" className="mt-1" value={draft.company_name} onChange={(e) => set("company_name", e.target.value)} />
                                </div>
                            </div>
                            <label htmlFor="greeting" className="block text-[13px] text-stone-600 mt-3">Then it says</label>
                            <Input id="greeting" className="mt-1" value={draft.greeting} onChange={(e) => set("greeting", e.target.value)} />
                            <p className="text-xs text-stone-500 mt-1.5">
                                On outbound calls you can use details from your list, like <code className="text-[11px] bg-stone-100 rounded px-1">{"{{name}}"}</code>.
                            </p>

                            <figure className="mt-4 rounded-md bg-stone-50 border border-line px-4 py-3">
                                <figcaption className="text-xs text-stone-500 mb-1.5 flex items-center justify-between">
                                    <span>Callers hear in {LANGUAGES.find((l) => l.code === draft.language)?.label || draft.language}</span>
                                    <span className="text-[11px] text-emerald-700 bg-emerald-50 border border-emerald-200/60 px-2 py-0.5 rounded-full font-medium">Natural Spoken Register</span>
                                </figcaption>
                                <blockquote className="text-sm leading-relaxed">
                                    <span className="text-stone-500">
                                        <Lock size={11} className="inline -mt-0.5 mr-1" aria-label="Required" />
                                        {getDisclosureText(draft.language, draft.assistant_name, draft.company_name)}
                                    </span>{" "}
                                    <span className="text-ink font-medium"><WithPlaceholders text={draft.greeting} /></span>
                                </blockquote>
                            </figure>
                        </SettingRow>
                    </Card>

                    <Card className="px-5 py-1">
                        <SettingRow label="Goal of the call" htmlFor="call_goal"
                                    hint="After every call, the assistant judges whether this happened. You'll see it as Successful in Calls and Collected data.">
                            <Textarea id="call_goal" rows={2} value={draft.call_goal} maxLength={500}
                                      placeholder="e.g. The caller books a site visit, or agrees to a call from our sales team"
                                      onChange={(e) => set("call_goal", e.target.value)} />
                        </SettingRow>
                        <SettingRow label="Information to collect"
                                    hint="The assistant asks for these naturally during the call. After the call they're saved as columns in Collected data, and sent to your webhook.">
                            <FieldsEditor value={draft.collect_fields} onChange={(v) => set("collect_fields", v)} />
                        </SettingRow>
                    </Card>

                    <Card className="px-5 py-1">
                        <SettingRow label="Background sound"
                                    hint="Plays quietly under the assistant for the whole call, so it sounds like a real office rather than a silent line.">
                            <AmbiencePicker kind={draft.ambience} volume={draft.ambience_volume}
                                            onKind={(v) => set("ambience", v)} onVolume={(v) => set("ambience_volume", v)} />
                        </SettingRow>
                        <SettingRow label="Pronunciation"
                                    hint="Words the voice gets wrong, like brand names or local places. Only the spoken audio changes; transcripts keep your spelling.">
                            <PronunciationEditor value={draft.pronunciations} onChange={(v) => set("pronunciations", v)} />
                        </SettingRow>
                    </Card>

                    <Card className="px-5 py-1">
                        <SettingRow label="Let callers interrupt" hint="The assistant stops talking as soon as the caller speaks.">
                            <Switch checked={draft.allow_interruptions} onChange={(v) => set("allow_interruptions", v)} label="Let callers interrupt" />
                        </SettingRow>
                        <SettingRow label="If the caller goes quiet" htmlFor="silence" hint="How long to wait before checking they're still there.">
                            <Select id="silence" className="max-w-48" value={draft.silence_timeout_sec} onChange={(e) => set("silence_timeout_sec", Number(e.target.value))}>
                                {[5, 8, 12, 20].map((s) => <option key={s} value={s}>After {s} seconds</option>)}
                            </Select>
                            <label htmlFor="reminders" className="block text-[13px] text-stone-600 mt-3">Then</label>
                            <Select id="reminders" className="max-w-64 mt-1" value={draft.silence_reminders} onChange={(e) => set("silence_reminders", Number(e.target.value))}>
                                <option value={0}>Say goodbye and hang up</option>
                                <option value={1}>Check once, then hang up</option>
                                <option value={2}>Check twice, then hang up</option>
                                <option value={3}>Check three times, then hang up</option>
                            </Select>
                        </SettingRow>
                        <SettingRow label="Longest call" htmlFor="maxlen" hint="Ends calls politely at this point so a line left open doesn't use up minutes.">
                            <Select id="maxlen" className="max-w-48" value={draft.max_call_minutes} onChange={(e) => set("max_call_minutes", Number(e.target.value))}>
                                {[5, 10, 15, 20].map((m) => <option key={m} value={m}>{m} minutes</option>)}
                            </Select>
                        </SettingRow>
                        <SettingRow label="End the call when they say" hint="Press Enter after each phrase.">
                            <PhraseInput label="Phrases that end the call" value={draft.end_call_phrases} onChange={(v) => set("end_call_phrases", v)} placeholder="e.g. that's all" />
                        </SettingRow>
                    </Card>

                    <Card className="px-5 py-1">
                        <SettingRow label="Transfer to a person" hint="If nobody picks up, the assistant takes a message. You'll see it in Calls.">
                            <Switch checked={draft.transfer_enabled} onChange={(v) => set("transfer_enabled", v)} label="Transfer to a person" />
                            {draft.transfer_enabled && (
                                <div className="mt-4 space-y-3">
                                    <div>
                                        <label htmlFor="transfer_number" className="text-[13px] text-stone-600">Number to transfer to</label>
                                        <Input id="transfer_number" type="tel" inputMode="tel" className="mt-1 max-w-64 tabular-nums" value={draft.transfer_number} onChange={(e) => set("transfer_number", e.target.value)} />
                                    </div>
                                    <div>
                                        <label htmlFor="transfer_when" className="text-[13px] text-stone-600">Transfer when</label>
                                        <Textarea id="transfer_when" className="mt-1" rows={2} value={draft.transfer_when} onChange={(e) => set("transfer_when", e.target.value)} />
                                    </div>
                                    <div>
                                        <span className="block text-[13px] text-stone-600 mb-1.5">How to hand over</span>
                                        <Segmented label="How to hand over" value={draft.transfer_mode} onChange={(v) => set("transfer_mode", v)}
                                                   options={[{ value: "cold", label: "Connect straight away" }, { value: "warm", label: "Brief them first" }]} />
                                        <p className="text-xs text-stone-500 mt-1.5">
                                            {draft.transfer_mode === "warm"
                                                ? "The person answering hears a one-line summary of the call before the caller is connected. Works on Twilio numbers."
                                                : "The caller is connected as soon as the person answers."}
                                        </p>
                                    </div>
                                </div>
                            )}
                        </SettingRow>
                    </Card>

                    <Card className="px-5 py-1">
                        <SettingRow label="If voicemail answers" hint="For call-backs and campaigns. The assistant listens for an answering machine before it speaks. Works on Twilio numbers.">
                            <Segmented label="If voicemail answers" value={draft.voicemail_action} onChange={(v) => set("voicemail_action", v)}
                                       options={[{ value: "off", label: "Don't check" }, { value: "hangup", label: "Hang up, try later" }, { value: "leave_message", label: "Leave a message" }]} />
                            {draft.voicemail_action === "leave_message" && (
                                <div className="mt-3">
                                    <label htmlFor="voicemail_message" className="text-[13px] text-stone-600">Message</label>
                                    <Textarea id="voicemail_message" className="mt-1" rows={3} maxLength={500} value={draft.voicemail_message}
                                              placeholder="Hi {{name}}, this is Nimmi from your company. Sorry we missed you. We'll try again soon, or call us back on this number."
                                              onChange={(e) => set("voicemail_message", e.target.value)} />
                                    <p className="text-xs text-stone-500 mt-1">Leave it empty to use a short default message.</p>
                                </div>
                            )}
                            {draft.voicemail_action !== "off" && (
                                <p className="text-xs text-stone-500 mt-2">Checking adds a few seconds before the assistant speaks, while it listens for a greeting or beep.</p>
                            )}
                        </SettingRow>
                    </Card>
                </div>

                <div className="lg:sticky lg:top-6">
                    <BrowserTest config={draft} dirty={dirty} />
                    <PhoneTest botId={draft.bot_id} botName={draft.bot_name} />
                </div>
            </div>

            <SaveBar visible={dirty} saving={saving} onDiscard={discard} onSave={async () => toast(await save())} />
        </>
    );
}
