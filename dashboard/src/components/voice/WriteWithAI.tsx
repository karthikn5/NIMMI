"use client";

import { useEffect, useState } from "react";
import { Button, Sheet, Textarea, cn } from "@/components/ui";
import { apiJson } from "@/lib/api";
import type { AgentDirection, ScriptAnswer, ScriptDraft } from "@/lib/voice/types";

type Question = { question: string; picks?: string[]; placeholder: string; suggestion?: string };

const PERSONALITY: Question = {
    question: "How should it sound?",
    picks: ["Friendly", "Professional", "Caring", "Cheerful", "Formal", "Playful"],
    placeholder: "Or describe it, e.g. warm and patient, like our front desk",
};

/** What "Write with AI" asks, for each kind of call. */
const QUESTIONS: Record<AgentDirection, Question[]> = {
    inbound: [
        PERSONALITY,
        { question: "What do people usually call you about?", placeholder: "e.g. course fees, admission dates, internship details" },
        {
            question: "What should it do on these calls?",
            picks: ["Answer questions", "Book appointments", "Take orders or bookings", "Qualify leads for sales", "Take a message", "Give timings and directions"],
            placeholder: "Anything else it should do",
        },
        { question: "What should it find out from callers?", placeholder: "e.g. their name, which course, a good time to call back" },
        { question: "When should it pass the call to a person?", placeholder: "e.g. complaints, payment problems, if they ask for the manager" },
        { question: "What should it say outside your working hours?", placeholder: "e.g. take their details and say the team will call back next morning" },
        { question: "Anything it must never say or promise?", placeholder: "e.g. discounts, exact delivery dates, medical advice" },
        {
            question: "How should it treat people who have called before?", placeholder: "",
            suggestion: "Greet them by name and ask whether they still need what they asked about last time.",
        },
    ],
    outbound: [
        PERSONALITY,
        {
            question: "Why does it call people?",
            picks: ["Call back people who asked in chat", "Follow up on enquiries", "Remind about appointments", "Collect feedback", "Payment reminders"],
            placeholder: "Anything else",
        },
        { question: "How should it start the call?", placeholder: "e.g. remind them they asked for a call on our website yesterday" },
        { question: "What counts as a successful call?", placeholder: "e.g. they book a demo, or confirm their appointment" },
        { question: "What should it find out?", placeholder: "e.g. a good date for the demo, their budget" },
        {
            question: "What if they're busy or not interested?", placeholder: "",
            suggestion: "If busy, ask for a better time. If not interested, thank them and end the call politely.",
        },
        { question: "Anything it must never say or do?", placeholder: "e.g. pressure them, promise discounts, call again if they said no" },
    ],
};

type Answer = { picks: string[]; text: string };

/** Answer a few questions; the AI writes the script from them and the assistant's knowledge. Nothing is saved here:
 * the script editor shows the result to review and save. */
export default function WriteWithAI({ open, onClose, botId, direction, previous, onDraft }: {
    open: boolean; onClose: () => void; botId: string; direction: AgentDirection; previous: ScriptAnswer[];
    onDraft: (draft: ScriptDraft, answers: ScriptAnswer[]) => void;
}) {
    const questions = QUESTIONS[direction];
    const [answers, setAnswers] = useState<Answer[]>([]);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        if (!open) return;
        // Start from what they answered last time.
        setAnswers(questions.map((q) => {
            const before = previous.find((p) => p.question === q.question)?.answer ?? "";
            const picks = (q.picks ?? []).filter((p) => before.split(", ").includes(p));
            const text = before.split(", ").filter((part) => !picks.includes(part)).join(", ");
            return { picks, text: before ? text : (q.suggestion ?? "") };
        }));
        setError(null);
    }, [open, questions, previous]);

    const togglePick = (i: number, pick: string, single: boolean) => setAnswers((all) => all.map((a, j) => j !== i ? a : {
        ...a, picks: a.picks.includes(pick) ? a.picks.filter((p) => p !== pick) : single ? [pick] : [...a.picks, pick],
    }));
    const setText = (i: number, text: string) => setAnswers((all) => all.map((a, j) => (j === i ? { ...a, text } : a)));

    const told = (): ScriptAnswer[] => questions.map((q, i) => ({
        question: q.question, answer: [...(answers[i]?.picks ?? []), (answers[i]?.text ?? "").trim()].filter(Boolean).join(", "),
    }));

    const write = async () => {
        setBusy(true);
        setError(null);
        try {
            const answered = told();
            const draft = await apiJson<ScriptDraft>(`/api/voice/scripts/${botId}/${direction}/draft`, {
                method: "POST", json: { answers: answered.filter((a) => a.answer) },
            });
            onDraft(draft, answered.filter((a) => a.answer));
            onClose();
        } catch (e) {
            setError((e as Error).message || "Couldn't write the script. Please try again.");
        } finally {
            setBusy(false);
        }
    };

    return (
        <Sheet
            open={open}
            onClose={onClose}
            title={`Write the ${direction === "inbound" ? "incoming" : "outgoing"} script with AI`}
            subtitle="Answer what you can. It writes the script from your answers and what the assistant knows. You can change anything before saving."
        >
            <div className="px-6 py-5 space-y-6">
                {questions.map((q, i) => (
                    <fieldset key={q.question}>
                        <legend className="text-sm font-medium text-ink">{q.question}</legend>
                        {q.picks && (
                            <div className="flex flex-wrap gap-1.5 mt-2.5">
                                {q.picks.map((pick) => {
                                    const on = answers[i]?.picks.includes(pick) ?? false;
                                    return (
                                        <button
                                            key={pick}
                                            type="button"
                                            aria-pressed={on}
                                            onClick={() => togglePick(i, pick, q === PERSONALITY)}
                                            className={cn(
                                                "h-7 px-2.5 rounded-full border text-[13px] transition-colors focus-visible:outline-2 focus-visible:outline-plum",
                                                on ? "border-plum bg-plum-tint text-plum" : "border-line text-stone-600 hover:border-line-strong",
                                            )}
                                        >
                                            {pick}
                                        </button>
                                    );
                                })}
                            </div>
                        )}
                        <Textarea
                            aria-label={q.question}
                            className="mt-2.5"
                            rows={2}
                            maxLength={900}
                            value={answers[i]?.text ?? ""}
                            placeholder={q.placeholder}
                            onChange={(e) => setText(i, e.target.value)}
                        />
                    </fieldset>
                ))}
                {error && <p className="text-sm text-signal" role="alert">{error}</p>}
                <div className="flex justify-end gap-2 pt-2 pb-4">
                    <Button variant="ghost" onClick={onClose}>Cancel</Button>
                    <Button variant="primary" onClick={write} disabled={busy}>{busy ? "Writing…" : "Write the script"}</Button>
                </div>
            </div>
        </Sheet>
    );
}
