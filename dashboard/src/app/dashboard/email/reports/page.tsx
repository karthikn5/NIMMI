"use client";

import { useState } from "react";
import { Card, EmptyState, Segmented, Select, Skeleton, Status } from "@/components/ui";
import type { EmailReports, ReportRow, Senders } from "@/lib/email";
import { useApi } from "@/lib/useApi";

const n = (v: number) => v.toLocaleString("en-IN");
const pct = (part: number, whole: number) => (whole ? `${Math.round((part / whole) * 100)}%` : "–");
const rate = (r: number | null) => (r === null ? "–" : `${(r * 100).toFixed(r < 0.01 ? 2 : 1)}%`);
const TYPE: Record<ReportRow["type"], string> = { automatic: "Automatic", journey: "Journey", bulk: "Bulk email" };
const LEVEL = { good: { tone: "good", text: "Fine" }, warn: { tone: "warn", text: "Watch it" }, bad: { tone: "bad", text: "Too high" }, unknown: { tone: "neutral", text: "Not enough yet" } } as const;
const LOGO = {
    on: "Your logo can show in Gmail.",
    needs_certificate: "Logo in Gmail: the record is there; Gmail also wants a mark certificate.",
    ready: "Logo in Gmail: DMARC is ready. Next is a mark certificate (about $500 to $2,000 a year) and one DNS record.",
    needs_dmarc: "Logo in Gmail: first DMARC has to be quarantine or reject, on all your mail.",
};
const DMARC: Record<string, { tone: "good" | "warn" | "bad" | "neutral"; text: string }> = {
    reject: { tone: "good", text: "DMARC: reject" }, quarantine: { tone: "good", text: "DMARC: quarantine" }, none: { tone: "warn", text: "DMARC: monitoring only" },
    missing: { tone: "bad", text: "No DMARC record" }, unreadable: { tone: "warn", text: "DMARC record unreadable" },
};

function Funnel({ f }: { f: EmailReports["funnel"] }) {
    const steps: [string, number, string][] = [["New leads", f.leads, "Came in during this time"], ["Emailed", f.emailed, "Got at least one email"],
        ["Engaged", f.engaged, "Replied or clicked"], ["Meeting", f.meetings, "Asked for or booked one"], ["Customer", f.customers, "Marked customer"]];
    const top = Math.max(f.leads, 1);
    return (
        <Card className="p-5">
            <h2 className="text-sm font-medium">From lead to customer</h2>
            <p className="text-[13px] text-stone-500 mt-0.5">The leads who came in during this time, and how far each got.</p>
            <ol className="mt-4 space-y-2.5">
                {steps.map(([label, value, hint], i) => (
                    <li key={label} className="grid grid-cols-[7rem_1fr_4.5rem] items-center gap-3 text-[13px]">
                        <span><span className="block text-ink">{label}</span><span className="block text-xs text-stone-500">{hint}</span></span>
                        <span className="h-2.5 rounded-full bg-stone-100 overflow-hidden" aria-hidden><span className="block h-full bg-plum/70 rounded-full" style={{ width: `${(value / top) * 100}%` }} /></span>
                        <span className="text-right tabular-nums">{n(value)}{i > 0 && <span className="text-stone-500"> · {pct(value, f.leads)}</span>}</span>
                    </li>
                ))}
            </ol>
        </Card>
    );
}

export default function EmailReportsPage() {
    const senders = useApi<Senders>("/api/email/senders");
    const [days, setDays] = useState<"7" | "30" | "90">("30");
    const [botId, setBotId] = useState("");
    const report = useApi<EmailReports>(`/api/email/reports?days=${days}${botId ? `&bot_id=${botId}` : ""}`);
    const assistants = senders.data?.assistants ?? [];

    if (report.error) return <p className="text-sm text-signal">{report.error}</p>;
    const r = report.data;
    const d = r?.deliverability;
    return (
        <div className="space-y-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
                <Segmented label="Period" value={days} onChange={setDays} options={[{ value: "7", label: "7 days" }, { value: "30", label: "30 days" }, { value: "90", label: "90 days" }]} />
                {assistants.length > 1 && (
                    <Select aria-label="Assistant" className="w-56" value={botId} onChange={(e) => setBotId(e.target.value)}>
                        <option value="">All assistants</option>
                        {assistants.map((a) => <option key={a.bot_id} value={a.bot_id}>{a.bot_name}</option>)}
                    </Select>
                )}
            </div>
            {!r || !d ? <Skeleton className="h-96" /> : (
                <>
                    <Funnel f={r.funnel} />
                    <Card>
                        <div className="px-5 pt-4 pb-3">
                            <h2 className="text-sm font-medium">Each email</h2>
                            <p className="text-[13px] text-stone-500 mt-0.5">A reply or an unsubscribe counts for the last email the person got, within a week. Clicks are people&apos;s: security scanners&apos; are left out, and opens aren&apos;t counted.</p>
                        </div>
                        {r.emails.length === 0 ? <div className="border-t border-line"><EmptyState title="Nothing sent in this time" body="Reports fill in as your emails go out." /></div> : (
                            <div className="overflow-x-auto border-t border-line">
                                <table className="w-full text-[13px]">
                                    <thead className="text-xs text-stone-500 text-left">
                                        <tr>{["Email", "Sent", "Delivered", "Clicked", "Replied", "Unsubscribed", "Bounced", "Spam reports"].map((h, i) => (
                                            <th key={h} scope="col" className={`px-4 py-2.5 font-normal whitespace-nowrap ${i ? "text-right" : ""}`}>{h}</th>
                                        ))}</tr>
                                    </thead>
                                    <tbody>
                                        {r.emails.map((row) => (
                                            <tr key={row.key} className="border-t border-line">
                                                <th scope="row" className="px-4 py-2.5 text-left font-normal">
                                                    <span className="block text-ink">{row.label}</span><span className="block text-xs text-stone-500">{TYPE[row.type]}</span>
                                                </th>
                                                <td className="px-4 py-2.5 text-right tabular-nums">{n(row.sent)}</td>
                                                <td className="px-4 py-2.5 text-right tabular-nums">{n(row.delivered)}</td>
                                                <td className="px-4 py-2.5 text-right tabular-nums">{n(row.clicked)} <span className="text-stone-500">{pct(row.clicked, row.delivered || row.sent)}</span></td>
                                                <td className="px-4 py-2.5 text-right tabular-nums">{n(row.replied)} <span className="text-stone-500">{pct(row.replied, row.delivered || row.sent)}</span></td>
                                                <td className="px-4 py-2.5 text-right tabular-nums">{n(row.unsubscribed)}</td>
                                                <td className={`px-4 py-2.5 text-right tabular-nums ${row.bounced ? "text-signal" : ""}`}>{n(row.bounced)}</td>
                                                <td className={`px-4 py-2.5 text-right tabular-nums ${row.complained ? "text-signal" : ""}`}>{n(row.complained)}</td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        )}
                    </Card>
                    <div className="grid lg:grid-cols-2 gap-5 items-start">
                        <Card>
                            <div className="px-5 pt-4 pb-3">
                                <h2 className="text-sm font-medium">Your team&apos;s answers</h2>
                                <p className="text-[13px] text-stone-500 mt-0.5">Replies to people from the Inbox, and how long people waited for them.</p>
                            </div>
                            {r.team.length === 0 ? <p className="px-5 py-3 border-t border-line text-[13px] text-stone-500">Nobody answered from the Inbox in this time.</p> : (
                                <ul>
                                    {r.team.map((t) => (
                                        <li key={t.id} className="flex items-center justify-between gap-3 px-5 py-2.5 border-t border-line text-[13px]">
                                            <span className="truncate">{t.name}</span>
                                            <span className="tabular-nums text-stone-600 shrink-0">{t.answers} {t.answers === 1 ? "answer" : "answers"}
                                                {t.median_minutes !== null && <> · usually {t.median_minutes < 60 ? `${t.median_minutes} min` : `${Math.round(t.median_minutes / 6) / 10} h`}</>}</span>
                                        </li>
                                    ))}
                                </ul>
                            )}
                        </Card>
                        <Card>
                            <div className="px-5 pt-4 pb-3">
                                <h2 className="text-sm font-medium">Is your mail landing?</h2>
                                <p className="text-[13px] text-stone-500 mt-0.5">Gmail asks senders to keep spam reports under 0.1% and never reach 0.3%.</p>
                            </div>
                            <ul className="text-[13px]">
                                <li className="flex items-center justify-between gap-3 px-5 py-2.5 border-t border-line">
                                    <span>Bounces: {n(d.bounced)} of {n(d.sent)} <span className="text-stone-500">({rate(d.bounce_rate)})</span></span>
                                    <Status tone={LEVEL[d.bounce_level].tone}>{LEVEL[d.bounce_level].text}</Status>
                                </li>
                                <li className="flex items-center justify-between gap-3 px-5 py-2.5 border-t border-line">
                                    <span>Spam reports: {n(d.complained)} of {n(d.delivered)} delivered <span className="text-stone-500">({rate(d.complaint_rate)})</span></span>
                                    <Status tone={LEVEL[d.complaint_level].tone}>{LEVEL[d.complaint_level].text}</Status>
                                </li>
                                <li className="px-5 py-2.5 border-t border-line text-stone-600">
                                    {n(d.scanner_clicks)} {d.scanner_clicks === 1 ? "click was" : "clicks were"} by security scanners, not people, and {d.scanner_clicks === 1 ? "is" : "are"} left out.
                                </li>
                                {d.domains.map((dm) => (
                                    <li key={dm.name} className="px-5 py-2.5 border-t border-line">
                                        <div className="flex items-center justify-between gap-3">
                                            <span className="truncate">{dm.name}</span>
                                            {dm.checked && dm.dmarc ? <Status tone={DMARC[dm.dmarc]?.tone ?? "neutral"}>{DMARC[dm.dmarc]?.text ?? dm.dmarc}</Status>
                                                : <span className="text-stone-500">Couldn&apos;t check DMARC just now</span>}
                                        </div>
                                        {dm.logo && <p className="text-stone-600 mt-1">{LOGO[dm.logo]}</p>}
                                    </li>
                                ))}
                            </ul>
                            <details className="px-5 py-3 border-t border-line text-[13px] text-stone-600">
                                <summary className="cursor-pointer text-ink">See what Gmail sees: Postmaster Tools</summary>
                                <ol className="list-decimal pl-5 mt-2 space-y-1">
                                    <li>Go to postmaster.google.com and sign in with a Google account.</li>
                                    <li>Press the plus button and enter the domain your emails come from{d.domains[0] ? `, ${d.domains[0].name}` : ""}.</li>
                                    <li>Google shows a TXT record. Add it at your DNS provider (for GoDaddy: My Products, your domain, DNS, Add New Record), then press Verify.</li>
                                    <li>Within a few days Gmail shows your spam rate and your domain&apos;s reputation there, once you send enough mail to Gmail addresses.</li>
                                </ol>
                            </details>
                        </Card>
                    </div>
                </>
            )}
        </div>
    );
}
