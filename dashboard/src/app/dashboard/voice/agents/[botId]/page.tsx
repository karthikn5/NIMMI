"use client";

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { ArrowLeft, ArrowRight, Lock, PhoneIncoming, PhoneOutgoing } from "lucide-react";
import BrowserTest from "@/components/voice/BrowserTest";
import { AmbiencePicker, PronunciationEditor } from "@/components/voice/AgentEditors";
import { AgentDetailsLine, LanguageMenu, ModelMenu, VoiceMenu } from "@/components/voice/AgentToolbar";
import { FunctionsEditor } from "@/components/voice/FunctionsEditor";
import { ScheduleCard } from "@/components/voice/schedule/AgentCard";
import { WithPlaceholders } from "@/components/voice/CampaignBits";
import PhoneTest from "@/components/voice/PhoneTest";
import {
    Button, Card, Input, PhraseInput, SaveBar, Segmented, Select, SettingRow, Skeleton, Switch, Textarea, cn, useToast,
} from "@/components/ui";
import { Suspense, useRef } from "react";
import { apiUrl } from "@/lib/api";
import { useApi, useDraft } from "@/lib/useApi";
import { DIRECTIONS, LANGUAGES, directionOf, getDisclosureText } from "@/lib/voice/api";
import type { AgentDetails, AgentDirection, Voice, VoiceAgentConfig, VoiceAgentSummary, VoiceModels, VoiceScript } from "@/lib/voice/types";

export default function AgentSettingsPage() {
    return <Suspense><AgentSettings /></Suspense>;
}

function AgentSettings() {
    const { botId } = useParams<{ botId: string }>();
    const router = useRouter();
    const direction = directionOf(useSearchParams().get("direction"));
    const about = DIRECTIONS[direction];
    const toast = useToast();
    const config = useApi<VoiceAgentConfig>(`/api/voice/agents/${botId}?direction=${direction}`);
    const script = useApi<VoiceScript>(`/api/voice/scripts/${botId}/${direction}`);
    const listed = useApi<VoiceAgentSummary[]>(direction === "inbound" ? "/api/voice/agents?direction=inbound" : null);
    const voices = useApi<Voice[]>("/api/voice/voices");
    const models = useApi<VoiceModels>("/api/voice/models");
    const details = useApi<AgentDetails>(`/api/voice/agents/${botId}/details?direction=${direction}`);
    const { draft, setDraft, dirty, saving, save, discard } = useDraft(config, `/api/voice/agents/${botId}?direction=${direction}`);
    const player = useRef<HTMLAudioElement | null>(null);
    const number = listed.data?.find((a) => a.bot_id === botId)?.phone_number ?? null;
    const knowledgeLink = `/dashboard/voice/knowledge/${botId}?section=${direction}`;

    if (config.loading || !draft) {
        return config.error
            ? <p className="text-sm text-signal">Couldn&apos;t load this agent. {config.error}</p>
            : <div className="space-y-6"><Skeleton className="h-10 w-64" /><Skeleton className="h-96" /></div>;
    }

    const set = <K extends keyof VoiceAgentConfig>(key: K, value: VoiceAgentConfig[K]) => setDraft({ ...draft, [key]: value });
    const switchTo = (other: AgentDirection) => {
        if (dirty && !window.confirm("Leave without saving your changes?")) return;
        router.replace(`/dashboard/voice/agents/${botId}?direction=${other}`);
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
            <Link href={`/dashboard/voice/agents?direction=${direction}`} className="inline-flex items-center gap-1.5 text-[13px] text-stone-500 hover:text-ink">
                <ArrowLeft size={14} /> {about.label}
            </Link>

            <div className="flex flex-wrap items-center justify-between gap-4 mt-3 mb-6">
                <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
                    <h2 className="text-xl font-semibold tracking-tight">{draft.bot_name}</h2>
                    <Segmented<AgentDirection>
                        label="Which agent"
                        value={direction}
                        onChange={switchTo}
                        options={[
                            { value: "inbound", label: "Incoming calls", icon: <PhoneIncoming size={13} /> },
                            { value: "outbound", label: "Outgoing calls", icon: <PhoneOutgoing size={13} /> },
                        ]}
                    />
                </div>
                <label className="flex items-center gap-3 text-sm">
                    <span className="text-stone-600">{draft.enabled ? about.on : "Off"}</span>
                    <Switch checked={draft.enabled} onChange={(v) => set("enabled", v)}
                            label={direction === "inbound" ? "Answer incoming calls" : "Make outgoing calls"} />
                </label>
            </div>

            <Card className="px-5 py-4 mb-6">
                <AgentDetailsLine model={models.data?.models.find((m) => m.id === draft.ai_model)}
                                  saved={draft.ai_model === config.data?.ai_model} details={details.data} />
                <div className="flex flex-wrap items-center gap-2 mt-3">
                    <ModelMenu value={draft.ai_model} onChange={(v) => set("ai_model", v)} models={models.data} />
                    <VoiceMenu value={draft.voice_id} onChange={(v) => set("voice_id", v)} voices={voices.data} onPlay={playSample} />
                    <LanguageMenu value={draft.language} onChange={(v) => set("language", v)} />
                </div>
                <p className="text-xs text-stone-500 mt-2.5 leading-relaxed">
                    {models.data?.models.find((m) => m.id === draft.ai_model)?.about}{" "}
                    The {direction === "inbound" ? "outgoing" : "incoming"} agent has its own model, voice and language.
                </p>
            </Card>

            <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_340px] items-start">
                <div className="space-y-6 min-w-0">
                    <Card className="px-5 py-1">
                        <SettingRow label="Functions"
                                    hint="What the agent can do during a call: look things up in your systems, check your calendar, book appointments.">
                            <FunctionsEditor value={draft.functions ?? []} onChange={(v) => set("functions", v)} botId={botId} direction={direction}
                                             modelCanRun={models.data?.models.find((m) => m.id === draft.ai_model)?.functions ?? true}
                                             modelName={models.data?.models.find((m) => m.id === draft.ai_model)?.name} />
                        </SettingRow>
                    </Card>
                    <Card className="px-5 py-1">
                        <SettingRow
                            label="Languages"
                            hint={draft.follow_caller_language
                                ? `Calls start in ${LANGUAGES.find((l) => l.code === draft.language)?.label ?? draft.language}. The assistant switches when a caller speaks another one.`
                                : `The assistant speaks and listens in ${LANGUAGES.find((l) => l.code === draft.language)?.label ?? draft.language}.`}
                        >
                            <label className="flex items-start gap-3">
                                <Switch checked={draft.understand_code_mixed} onChange={(v) => set("understand_code_mixed", v)} label="Understand mixed language" />
                                <span className="text-[13px] text-stone-600 leading-snug">
                                    Understand callers who mix in English, like Tanglish or Hinglish
                                </span>
                            </label>
                            <label className="flex items-start gap-3 mt-3">
                                <Switch checked={draft.follow_caller_language} onChange={(v) => set("follow_caller_language", v)} label="Reply in the caller's language" />
                                <span className="text-[13px] text-stone-600 leading-snug">
                                    Reply in the caller&apos;s language when they speak another one, like Tamil or Hindi
                                </span>
                            </label>
                            {draft.follow_caller_language && (
                                <div className="mt-3 pl-12">
                                    <span className="block text-[13px] text-stone-600">Languages it can switch to</span>
                                    <div role="group" aria-label="Languages it can switch to" className="flex flex-wrap gap-1.5 mt-2">
                                        {LANGUAGES.filter((l) => l.code !== draft.language).map((l) => {
                                            const on = draft.switch_languages.includes(l.code);
                                            return (
                                                <button
                                                    key={l.code}
                                                    type="button"
                                                    aria-pressed={on}
                                                    onClick={() => set("switch_languages", on
                                                        ? draft.switch_languages.filter((c) => c !== l.code)
                                                        : [...draft.switch_languages, l.code])}
                                                    className={cn(
                                                        "h-7 px-2.5 rounded-full border text-[13px] transition-colors focus-visible:outline-2 focus-visible:outline-plum",
                                                        on ? "border-plum bg-plum-tint text-plum" : "border-line text-stone-600 hover:border-line-strong",
                                                    )}
                                                >
                                                    {l.label}
                                                </button>
                                            );
                                        })}
                                    </div>
                                    <p className="text-xs text-stone-500 mt-1.5">
                                        {draft.switch_languages.length
                                            ? "It only changes to these. Words that sound like any other language never change the call's language."
                                            : "None picked: it can change to any of them. Pick the languages your callers speak, so a few unclear words never switch it to another one."}
                                    </p>
                                </div>
                            )}
                            <div className="mt-3.5 flex items-start gap-2.5 p-3 rounded-md bg-stone-50 border border-line text-xs text-stone-600 leading-relaxed">
                                <span className="h-2 w-2 rounded-full bg-emerald-500 mt-1 shrink-0" aria-hidden />
                                <div>
                                    <strong className="text-stone-800 font-semibold">Natural spoken style:</strong>
                                    {" "}Speaks everyday {LANGUAGES.find((l) => l.code === draft.language)?.label || draft.language} the way people talk on the phone, in short sentences, without filler sounds like &quot;hmm&quot; or &quot;ah&quot;.
                                </div>
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
                            label="Introduces itself as"
                            hint="Every call starts by saying it's automated and may be recorded. That part can't be removed. The same for incoming and outgoing calls."
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

                            <figure className="mt-4 rounded-md bg-stone-50 border border-line px-4 py-3">
                                <figcaption className="text-xs text-stone-500 mb-1.5">
                                    Callers hear in {LANGUAGES.find((l) => l.code === draft.language)?.label || draft.language}
                                </figcaption>
                                <blockquote className="text-sm leading-relaxed">
                                    <span className="text-stone-500">
                                        <Lock size={11} className="inline -mt-0.5 mr-1" aria-label="Required" />
                                        {getDisclosureText(draft.language, draft.assistant_name, draft.company_name)}
                                    </span>{" "}
                                    <span className="text-ink font-medium"><WithPlaceholders text={script.data?.greeting ?? ""} /></span>
                                </blockquote>
                            </figure>
                        </SettingRow>
                        <SettingRow label="What it says" hint="Its opening line, personality, how it handles these calls, its goal and the details it asks for.">
                            <p className="text-[13px] text-stone-600 leading-relaxed">
                                These are on the Knowledge page, next to what the assistant knows, so everything it says is in one place.
                            </p>
                            <Link href={knowledgeLink} className="inline-block mt-3">
                                <Button size="sm">Edit the {about.short.toLowerCase()} script <ArrowRight size={13} className="inline ml-1" aria-hidden /></Button>
                            </Link>
                        </SettingRow>
                        <SettingRow label="Remember callers"
                                    hint="The same for incoming and outgoing calls. When off, every call starts fresh and nothing new is saved; people already saved stay in Contacts.">
                            <label className="flex items-start gap-3">
                                <Switch checked={draft.remember_callers} onChange={(v) => set("remember_callers", v)} label="Remember callers" />
                                <span className="text-[13px] text-stone-600 leading-snug">
                                    Greet people it has spoken to before by name, and remember what earlier calls were about.{" "}
                                    <Link href="/dashboard/voice/contacts" className="text-plum hover:underline">Contacts</Link>
                                </span>
                            </label>
                        </SettingRow>
                    </Card>

                    <Card className="px-5 py-1">
                        <SettingRow label="Background sound"
                                    hint="Plays quietly under the assistant for the whole call, so it sounds like a real office rather than a silent line.">
                            <AmbiencePicker kind={draft.ambience} volume={draft.ambience_volume}
                                            onKind={(v) => set("ambience", v)} onVolume={(v) => set("ambience_volume", v)} />
                        </SettingRow>
                        <SettingRow label="Pronunciation"
                                    hint="Words the voice gets wrong, like brand names or local places. Only the spoken audio changes; transcripts keep your spelling. The same for incoming and outgoing calls.">
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
                        <SettingRow label="Longest call" htmlFor="maxlen" hint="Ends calls politely at this point so a line left open doesn't use up credits.">
                            <Select id="maxlen" className="max-w-48" value={draft.max_call_minutes} onChange={(e) => set("max_call_minutes", Number(e.target.value))}>
                                {[5, 10, 15, 20].map((m) => <option key={m} value={m}>{m} minutes</option>)}
                            </Select>
                        </SettingRow>
                        <SettingRow label="End the call when they say" hint="Press Enter after each phrase.">
                            <PhraseInput label="Phrases that end the call" value={draft.end_call_phrases} onChange={(v) => set("end_call_phrases", v)} placeholder="e.g. that's all" />
                        </SettingRow>
                    </Card>

                    <Card className="px-5 py-1">
                        <SettingRow label="Ring my team in the dashboard" hint="When a caller asks for a person, or needs one, everyone available in the dashboard sees it and can pick up the call: in the browser on Twilio numbers, or on their phone. The assistant keeps the caller company meanwhile.">
                            <Switch checked={draft.team_handoff} onChange={(v) => set("team_handoff", v)} label="Ring my team in the dashboard" />
                            {draft.team_handoff && (
                                <div className="mt-4">
                                    <label htmlFor="team_handoff_wait" className="text-[13px] text-stone-600">Wait for someone to pick up</label>
                                    <Select id="team_handoff_wait" className="mt-1 max-w-48" value={draft.team_handoff_wait}
                                            onChange={(e) => set("team_handoff_wait", Number(e.target.value))}>
                                        {[15, 30, 45, 60, 90, 120].map((s) => <option key={s} value={s}>{s} seconds</option>)}
                                    </Select>
                                    <p className="text-xs text-stone-500 mt-1.5">
                                        Then the transfer number below, if you set one. Otherwise the assistant tells the caller the team is busy, and a call-back appears in Schedule.
                                    </p>
                                </div>
                            )}
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

                    {direction === "outbound" && <Card className="px-5 py-1">
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
                    </Card>}
                </div>

                <div className="lg:sticky lg:top-6">
                    <BrowserTest config={draft} dirty={dirty} direction={direction} />
                    {direction === "outbound" ? (
                        <PhoneTest botId={draft.bot_id} botName={draft.bot_name} />
                    ) : (
                        <Card className="p-5 mt-4">
                            <h3 className="text-[15px] font-semibold">Test on a real phone</h3>
                            {number ? (
                                <p className="text-[13px] text-stone-600 mt-1.5 leading-relaxed">
                                    Call <span className="font-medium text-ink tabular-nums">{number}</span> from your phone. Calls from a number it has
                                    spoken to before are greeted by name.
                                </p>
                            ) : (
                                <p className="text-[13px] text-stone-600 mt-1.5 leading-relaxed">
                                    Give this assistant a phone number to answer calls on. <Link href="/dashboard/voice/numbers" className="text-plum hover:underline">Numbers</Link>
                                </p>
                            )}
                        </Card>
                    )}
                    <ScheduleCard botId={botId} modelCanRun={models.data?.models.find((m) => m.id === draft.ai_model)?.functions ?? true}
                                  modelName={models.data?.models.find((m) => m.id === draft.ai_model)?.name} />
                </div>
            </div>

            <SaveBar visible={dirty} saving={saving} onDiscard={discard} onSave={async () => toast(await save())} />
        </>
    );
}
