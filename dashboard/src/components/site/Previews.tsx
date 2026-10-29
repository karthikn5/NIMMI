import { ChevronDown, FileText, Phone, PhoneIncoming, PhoneOutgoing } from "lucide-react";
import { cn } from "./cn";
import { Dot, Frame } from "./primitives";

/*
 * Product previews drawn in code (not screenshots), using the same styles as the dashboard.
 * The conversations are illustrations of how the product works, labelled as examples.
 */

function Bubble({ from, children }: { from: "customer" | "assistant"; children: React.ReactNode }) {
    return (
        <div className={cn("flex", from === "assistant" ? "justify-start" : "justify-end")}>
            <p className={cn(
                "max-w-[82%] px-3 py-2 rounded-lg text-[13px] leading-snug",
                from === "assistant" ? "bg-stone-100 text-ink rounded-tl-sm" : "bg-plum text-white rounded-tr-sm",
            )}>{children}</p>
        </div>
    );
}

export function ChatPreview({ className }: { className?: string }) {
    return (
        <Frame title="WhatsApp · Green Park Homes" meta="Example" className={className}>
            <div className="p-4 space-y-2.5">
                <Bubble from="customer">Hi, 2BHK flat price enna?</Bubble>
                <Bubble from="assistant">2BHK homes at Green Park start at ₹58 lakhs, with possession in March. Would you like to see the site this weekend?</Bubble>
                <Bubble from="customer">Saturday morning ok</Bubble>
                <Bubble from="assistant">Done. Saturday at 11 AM. What name should I book it under?</Bubble>
            </div>
        </Frame>
    );
}

export function CallSummaryPreview({ className }: { className?: string }) {
    return (
        <Frame title={<span className="inline-flex items-center gap-1.5"><Phone size={12} className="text-stone-500" /> Inbound call · Tamil</span>} meta="2:14" className={className}>
            <div className="px-4 py-3.5">
                <p className="text-[13px] leading-snug">Asked about 3BHK prices and home loans. Booked a site visit for Sunday morning.</p>
                <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 mt-3 text-[12px]">
                    <dt className="text-stone-500">Name</dt><dd>Arun</dd>
                    <dt className="text-stone-500">Budget</dt><dd>85 lakhs</dd>
                    <dt className="text-stone-500">Visit</dt><dd>Sunday, 10 AM</dd>
                </dl>
                <div className="flex flex-wrap gap-x-4 gap-y-1 mt-3 pt-3 border-t border-line">
                    <Dot tone="good">Goal met</Dot>
                    <Dot tone="good">Positive</Dot>
                    <Dot tone="bad">Hot lead</Dot>
                </div>
            </div>
        </Frame>
    );
}

export function TranscriptPreview() {
    const turns: [string, "agent" | "caller", string][] = [
        ["0:02", "agent", "Vanakkam, I'm Nimmi, an automated assistant for Sri Ramana College. This call may be recorded. How can I help?"],
        ["0:08", "caller", "MBA admission ku fees evlo?"],
        ["0:10", "agent", "The two-year MBA is ₹1.2 lakhs a year, and scholarships are available. Shall I book a counselling session?"],
        ["0:19", "caller", "Yes, tomorrow evening"],
        ["0:21", "agent", "Booked for tomorrow at 5 PM. You'll get the details on WhatsApp."],
    ];
    return (
        <Frame title="Call transcript" meta="Example" className="text-left">
            <ol className="px-4 py-3.5 space-y-2.5">
                {turns.map(([at, who, text]) => (
                    <li key={at} className="grid grid-cols-[2.25rem_1fr] gap-2 text-[13px] leading-snug">
                        <span className="text-stone-400 tabular-nums">{at}</span>
                        <span>
                            <span className={cn("block text-[11px]", who === "agent" ? "text-plum font-medium" : "text-stone-500")}>
                                {who === "agent" ? "Assistant" : "Caller"}
                            </span>
                            {text}
                        </span>
                    </li>
                ))}
            </ol>
        </Frame>
    );
}

export function CampaignPreview() {
    const rows: [string, string, "good" | "plum" | "neutral" | "bad", string][] = [
        ["Ravi Kumar", "B-204", "good", "Visit booked"],
        ["Asha Nair", "Villa 7", "good", "Wants price list"],
        ["Imran S", "C-110", "bad", "No answer, retry 4 PM"],
        ["Meera Iyer", "B-118", "plum", "Calling"],
    ];
    return (
        <Frame title={<span className="inline-flex items-center gap-1.5"><PhoneOutgoing size={12} className="text-stone-500" /> Site-visit follow-ups</span>} meta="Example">
            <div className="px-4 pt-3.5">
                <div className="flex justify-between text-[11px] text-stone-500 mb-1.5"><span>62 of 120 called</span><span>41 reached</span></div>
                <div className="h-1.5 rounded-full bg-stone-100 overflow-hidden flex" aria-hidden>
                    <div className="bg-plum" style={{ width: "34%" }} />
                    <div className="bg-stone-300" style={{ width: "18%" }} />
                </div>
            </div>
            <ul className="mt-3 border-t border-line">
                {rows.map(([name, unit, tone, note]) => (
                    <li key={name} className="grid grid-cols-[1fr_auto] gap-2 px-4 py-2 border-t border-line first:border-t-0 text-[12px]">
                        <span><span className="block text-[13px]">{name}</span><span className="text-stone-500">Unit {unit}</span></span>
                        <span className="self-center"><Dot tone={tone}>{note}</Dot></span>
                    </li>
                ))}
            </ul>
        </Frame>
    );
}

export function DataPreview() {
    const rows = [
        ["Priya R", "Flat", "65", "Hot", "Met"],
        ["Karthik S", "Villa", "120", "Warm", "Met"],
        ["Fatima B", "Plot", "40", "Warm", "Not met"],
        ["Deepak J", "Flat", "", "Cold", "Not met"],
    ];
    return (
        <Frame title="Collected data · Green Park Homes" meta="Export CSV">
            <div className="overflow-x-auto">
                <table className="w-full text-[12px]">
                    <thead>
                        <tr className="text-left text-stone-500">
                            {["Caller", "Type", "Budget (L)", "Lead", "Goal"].map((h) => <th key={h} className="font-normal px-4 py-2 whitespace-nowrap">{h}</th>)}
                        </tr>
                    </thead>
                    <tbody>
                        {rows.map(([n, t, b, lead, goal]) => (
                            <tr key={n} className="border-t border-line">
                                <td className="px-4 py-2 whitespace-nowrap">{n}</td>
                                <td className="px-4 py-2">{t}</td>
                                <td className="px-4 py-2 tabular-nums">{b || <span className="text-stone-300">–</span>}</td>
                                <td className="px-4 py-2"><Dot tone={lead === "Hot" ? "bad" : lead === "Warm" ? "warn" : "neutral"}>{lead}</Dot></td>
                                <td className="px-4 py-2"><Dot tone={goal === "Met" ? "good" : "neutral"}>{goal}</Dot></td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </Frame>
    );
}

export function LiveChatPreview() {
    return (
        <Frame title="Live chat" meta="Example">
            <div className="grid grid-cols-[9.5rem_1fr] min-h-[220px]">
                <ul className="border-r border-line text-[12px]">
                    {[["Ravi Kumar", "WhatsApp", true], ["Asha", "Website", false], ["+91 98400 77…", "WhatsApp", false]].map(([n, ch, on]) => (
                        <li key={n as string} className={cn("px-3 py-2.5 border-b border-line", on && "bg-plum-tint")}>
                            <span className="block font-medium truncate">{n}</span>
                            <span className="text-stone-500">{ch}</span>
                        </li>
                    ))}
                </ul>
                <div className="p-3 flex flex-col gap-2 text-[12px]">
                    <p className="self-start max-w-[90%] bg-stone-100 rounded-lg rounded-tl-sm px-2.5 py-1.5">Nobody called me back yesterday!</p>
                    <p className="self-center w-full bg-amber-50 border border-amber-200 rounded px-2.5 py-1.5">
                        <span className="block text-[10px] text-amber-800">Note · only your team sees this</span>
                        Tried at 6 PM, no answer. Offer Saturday 11 AM.
                    </p>
                    <p className="self-end max-w-[90%] bg-plum text-white rounded-lg rounded-tr-sm px-2.5 py-1.5">Sorry about that, Ravi. Can I book Saturday at 11 AM for you?</p>
                </div>
            </div>
        </Frame>
    );
}

/* ---------- Newer features: WhatsApp, caller memory, follow-ups and meetings, functions ---------- */

const NOTE = [5, 9, 14, 8, 16, 11, 6, 13, 18, 10, 7, 12, 15, 9, 6, 11, 8];

export function WhatsAppPreview() {
    return (
        <Frame title="WhatsApp · Sri Ramana College" meta="Example">
            <div className="p-4 space-y-2.5">
                <div className="flex justify-end">
                    <div className="max-w-[82%] px-3 py-2 rounded-lg rounded-tr-sm bg-plum text-white">
                        <span className="flex items-center gap-2">
                            <span className="flex items-center gap-[2px] h-5" aria-hidden>
                                {NOTE.map((h, i) => <span key={i} className="w-[2px] rounded-full bg-white/70" style={{ height: h }} />)}
                            </span>
                            <span className="text-[11px] text-white/80 tabular-nums">0:09</span>
                        </span>
                        <span className="block text-[11px] text-white/75 mt-1">Voice note: &ldquo;Weekend MBA batch ku fees evlo?&rdquo;</span>
                    </div>
                </div>
                <Bubble from="assistant">The weekend MBA is ₹1.4 lakhs a year, with scholarships for early applicants. Here&apos;s the brochure with the full fees.</Bubble>
                <div className="flex justify-start">
                    <div className="flex items-center gap-2.5 max-w-[82%] px-3 py-2 rounded-lg rounded-tl-sm bg-stone-100">
                        <span className="h-8 w-8 shrink-0 rounded-md bg-white border border-line inline-flex items-center justify-center text-plum">
                            <FileText size={15} aria-hidden />
                        </span>
                        <span className="min-w-0">
                            <span className="block text-[12px] font-medium truncate">MBA-Weekend-Brochure.pdf</span>
                            <span className="block text-[11px] text-stone-500">PDF · 1.2 MB</span>
                        </span>
                    </div>
                </div>
                <Bubble from="assistant">Would you like to see the campus this Saturday?</Bubble>
                <div className="flex flex-wrap gap-1.5 pl-1">
                    {["Book a campus visit", "Talk to a counsellor"].map((b) => (
                        <span key={b} className="px-2.5 py-1 rounded-full border border-line-strong bg-white text-[12px] text-plum">{b}</span>
                    ))}
                </div>
            </div>
        </Frame>
    );
}

export function MemoryPreview() {
    return (
        <Frame title={<span className="inline-flex items-center gap-1.5"><PhoneIncoming size={12} className="text-stone-500" /> Incoming call · +91 98400 7…</span>} meta="Known caller">
            <div className="px-4 py-3.5">
                <p className="text-[11px] text-plum font-medium">Assistant · 0:01</p>
                <p className="text-[13px] leading-snug mt-0.5">
                    Hello Karthik! Last time you asked about the weekend MBA batch. Did you get a chance to look at the brochure?
                </p>
                <div className="mt-3.5 pt-3 border-t border-line">
                    <p className="text-[11px] text-stone-500 mb-2">What it remembers</p>
                    <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-[12px]">
                        <dt className="text-stone-500">Name</dt><dd>Karthik S</dd>
                        <dt className="text-stone-500">Course</dt><dd>MBA, weekend batch</dd>
                        <dt className="text-stone-500">26 Oct, call</dt><dd>Asked about fees and scholarships</dd>
                        <dt className="text-stone-500">27 Oct, WhatsApp</dt><dd>Brochure sent</dd>
                        <dt className="text-stone-500">Team note</dt><dd>Prefers Tamil. Free after 6 PM.</dd>
                    </dl>
                </div>
                <div className="flex flex-wrap gap-x-4 gap-y-1 mt-3 pt-3 border-t border-line">
                    <Dot tone="warn">Warm lead</Dot>
                    <Dot tone="plum">Follow-up Saturday, 11 AM</Dot>
                </div>
            </div>
        </Frame>
    );
}

export function SchedulePreview() {
    const rows: [string, string, string, "good" | "warn" | "plum" | "neutral", string][] = [
        ["Meeting request", "Priya Raman", "Online · tomorrow, 11 AM · MBA fees", "warn", "Waiting for you"],
        ["Call-back", "Arun Kumar", "Today, 4:40 PM · he asked for 10 minutes later", "plum", "In 10 min"],
        ["Follow-up", "Fatima B", "Saturday, 10 AM · ask if she compared the two plots", "neutral", "Planned"],
        ["Asked for a person", "Deepak J", "Wants the site engineer to call him", "warn", "To do"],
    ];
    return (
        <Frame title="Schedule · Needs you" meta="Example">
            <ul>
                {rows.map(([kind, name, note, tone, state]) => (
                    <li key={name} className="grid grid-cols-[1fr_auto] gap-x-3 gap-y-0.5 px-4 py-2.5 border-t border-line first:border-t-0">
                        <span className="min-w-0">
                            <span className="block text-[11px] text-stone-500">{kind}</span>
                            <span className="block text-[13px] font-medium">{name}</span>
                            <span className="block text-[12px] text-stone-600 leading-snug">{note}</span>
                        </span>
                        <span className="self-center flex flex-col items-end gap-1.5">
                            <Dot tone={tone}>{state}</Dot>
                            {kind === "Meeting request" && (
                                <span className="px-2.5 py-0.5 rounded-md bg-plum text-white text-[11px] font-medium" aria-hidden>Approve</span>
                            )}
                        </span>
                    </li>
                ))}
            </ul>
            <div className="flex flex-wrap gap-x-4 gap-y-1 px-4 py-2.5 border-t border-line bg-stone-50/70">
                <Dot tone="good">Confirmation call</Dot>
                <Dot tone="good">Reminder the day before</Dot>
                <Dot tone="good">Link 5 min before</Dot>
            </div>
        </Frame>
    );
}

export function FunctionPreview() {
    const turns: [string, "agent" | "caller" | "system", string][] = [
        ["0:05", "caller", "Where's my order? The number is A1234."],
        ["0:06", "system", "check_order_status · A1234 → shipped, arriving Friday"],
        ["0:07", "agent", "Order A1234 has shipped. It'll reach you on Friday."],
        ["0:14", "caller", "Can I book a fitting this weekend?"],
        ["0:15", "system", "Cal.com · free on Saturday → 10 AM, 2 PM"],
        ["0:16", "agent", "Saturday has 10 AM or 2 PM free. Which suits you?"],
    ];
    return (
        <Frame title="Call · looking it up" meta="Example">
            <ol className="px-4 py-3.5 space-y-2.5">
                {turns.map(([at, who, text]) => (
                    <li key={at} className="grid grid-cols-[2.25rem_1fr] gap-2 text-[13px] leading-snug">
                        <span className="text-stone-400 tabular-nums">{at}</span>
                        {who === "system" ? (
                            <span className="self-center inline-flex items-start gap-1.5 text-[11.5px] text-stone-600 bg-plum-tint/70 border border-line rounded px-2 py-1">
                                <span className="h-1.5 w-1.5 mt-[5px] rounded-full bg-plum shrink-0" aria-hidden />{text}
                            </span>
                        ) : (
                            <span>
                                <span className={cn("block text-[11px]", who === "agent" ? "text-plum font-medium" : "text-stone-500")}>
                                    {who === "agent" ? "Assistant" : "Caller"}
                                </span>
                                {text}
                            </span>
                        )}
                    </li>
                ))}
            </ol>
            <div className="flex flex-wrap items-center gap-2 px-4 py-2.5 border-t border-line bg-stone-50/70 text-[12px]">
                <span className="text-stone-500">AI model</span>
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md border border-line-strong bg-white">
                    GPT-OSS 120B <span className="text-stone-500">· quick</span> <ChevronDown size={12} className="text-stone-400" aria-hidden />
                </span>
                <span className="text-stone-500">or Gemini, GPT and more</span>
            </div>
        </Frame>
    );
}
