"use client";

import { useState } from "react";
import { Card, EmptyState, Segmented, Skeleton } from "@/components/ui";
import { MADE_ON, rupees, sourceLabel, type LeadReport } from "@/lib/leads";
import { useApi } from "@/lib/useApi";

const n = (v: number) => v.toLocaleString("en-IN");

export default function LeadReportsPage() {
    const [days, setDays] = useState("30");
    const r = useApi<LeadReport>(`/api/crm/reports?days=${days}`);
    const d = r.data;
    return (
        <div className="space-y-5">
            <Segmented label="Period" value={days} onChange={setDays} options={[{ value: "7", label: "7 days" }, { value: "30", label: "30 days" }, { value: "90", label: "90 days" }]} />
            {r.error ? <p className="text-sm text-signal">{r.error}</p> : !d ? <Skeleton className="h-64" /> : d.leads === 0 && !d.won && !d.lost ? (
                <Card><EmptyState title="No leads in this time" body="Reports fill in as leads come in and your team works them." /></Card>
            ) : (
                <>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                        {[["Leads", n(d.leads)], ["Won", n(d.won)], ["Lost", n(d.lost)], ["Value won", rupees(d.value)]].map(([label, value]) => (
                            <Card key={label} className="p-4"><p className="text-xs text-stone-500">{label}</p><p className="text-xl font-semibold mt-1 tabular-nums">{value}</p></Card>
                        ))}
                    </div>
                    <Card>
                        <div className="px-5 pt-4 pb-3"><h2 className="text-sm font-medium">By source</h2></div>
                        <div className="overflow-x-auto">
                            <table className="w-full text-[13px]">
                                <thead><tr className="text-stone-500 border-y border-line">{["Source", "Leads", "Reached", "Won", "Lost", "Value", "Junk"].map((h, i) => <th key={h} scope="col" className={`px-5 py-2 font-normal ${i ? "text-right" : "text-left"}`}>{h}</th>)}</tr></thead>
                                <tbody>
                                    {d.sources.map((s) => (
                                        <tr key={s.source} className="border-b border-line last:border-b-0">
                                            <td className="px-5 py-2">{sourceLabel(s.source)}</td>
                                            <td className="px-5 py-2 text-right tabular-nums">{n(s.leads)}</td>
                                            <td className="px-5 py-2 text-right tabular-nums">{n(s.reached)}</td>
                                            <td className="px-5 py-2 text-right tabular-nums">{n(s.won)}</td>
                                            <td className="px-5 py-2 text-right tabular-nums">{n(s.lost)}</td>
                                            <td className="px-5 py-2 text-right tabular-nums">{s.value ? rupees(s.value) : "-"}</td>
                                            <td className="px-5 py-2 text-right tabular-nums">{s.junk ? n(s.junk) : "-"}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </Card>
                    <div className="grid md:grid-cols-2 gap-5 items-start">
                        <Card>
                            <div className="px-5 pt-4 pb-3 border-b border-line">
                                <h2 className="text-sm font-medium">How fast people were first tried</h2>
                                <p className="text-[13px] text-stone-500 mt-0.5">From when they came in to the first try, by a person or the assistant.</p>
                            </div>
                            <ul className="text-[13px]">
                                <li className="flex justify-between px-5 py-2.5 border-b border-line"><span>Half were tried within</span><span className="tabular-nums">{d.first_response.median_minutes === null ? "-" : `${d.first_response.median_minutes} min`}</span></li>
                                <li className="flex justify-between px-5 py-2.5 border-b border-line"><span>Within 5 minutes</span><span className="tabular-nums">{n(d.first_response.within_5)}</span></li>
                                <li className="flex justify-between px-5 py-2.5 border-b border-line"><span>Within an hour</span><span className="tabular-nums">{n(d.first_response.within_60)}</span></li>
                                <li className="flex justify-between px-5 py-2.5"><span>Not tried yet</span><span className="tabular-nums">{n(d.first_response.not_tried)}</span></li>
                            </ul>
                        </Card>
                        <Card>
                            <div className="px-5 pt-4 pb-3 border-b border-line"><h2 className="text-sm font-medium">Your team</h2></div>
                            <div className="overflow-x-auto">
                                <table className="w-full text-[13px]">
                                    <thead><tr className="text-stone-500 border-b border-line">{["Person", "Done", "Overdue", "Won"].map((h, i) => <th key={h} scope="col" className={`px-5 py-2 font-normal ${i ? "text-right" : "text-left"}`}>{h}</th>)}</tr></thead>
                                    <tbody>{d.team.map((p) => <tr key={p.id} className="border-b border-line last:border-b-0"><td className="px-5 py-2">{p.name}</td><td className="px-5 py-2 text-right tabular-nums">{n(p.done)}</td><td className="px-5 py-2 text-right tabular-nums">{n(p.overdue)}</td><td className="px-5 py-2 text-right tabular-nums">{n(p.won)}</td></tr>)}</tbody>
                                </table>
                            </div>
                        </Card>
                    </div>
                    {!!d.promises?.made && (
                        <Card>
                            <div className="px-5 pt-4 pb-3 border-b border-line">
                                <h2 className="text-sm font-medium">Promises</h2>
                                <p className="text-[13px] text-stone-500 mt-0.5">What your assistant and your team told people would be done, made in this time, and what happened to it.</p>
                            </div>
                            <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 px-5 py-4">
                                {([["Made", d.promises.made], ["Kept", d.promises.kept], ["Kept on time", d.promises.on_time], ["Late, still open", d.promises.late],
                                   ["Cancelled", d.promises.cancelled]] as [string, number][]).map(([label, value]) => (
                                    <div key={label}><p className="text-xs text-stone-500">{label}</p><p className={`text-lg font-semibold tabular-nums ${label.startsWith("Late") && value ? "text-signal" : ""}`}>{n(value)}</p></div>
                                ))}
                            </div>
                            {d.promises.by_channel.length > 1 && (
                                <div className="overflow-x-auto border-t border-line">
                                    <table className="w-full text-[13px]">
                                        <thead><tr className="text-stone-500 border-b border-line">{["Promised", "Made", "Kept", "On time"].map((h, i) => <th key={h} scope="col" className={`px-5 py-2 font-normal ${i ? "text-right" : "text-left"}`}>{h}</th>)}</tr></thead>
                                        <tbody>{d.promises.by_channel.map((c) => (
                                            <tr key={c.made_on} className="border-b border-line last:border-b-0">
                                                <td className="px-5 py-2">{(MADE_ON[c.made_on] ?? c.made_on).replace(/^\w/, (x) => x.toUpperCase())}</td>
                                                <td className="px-5 py-2 text-right tabular-nums">{n(c.made)}</td>
                                                <td className="px-5 py-2 text-right tabular-nums">{n(c.kept)}</td>
                                                <td className="px-5 py-2 text-right tabular-nums">{n(c.on_time)}</td>
                                            </tr>
                                        ))}</tbody>
                                    </table>
                                </div>
                            )}
                        </Card>
                    )}
                    {!!d.lost_reasons.length && (
                        <div className="grid md:grid-cols-2 gap-5 items-start">
                            <Card>
                                <div className="px-5 pt-4 pb-3 border-b border-line"><h2 className="text-sm font-medium">Why leads were lost</h2></div>
                                <ul className="text-[13px]">{d.lost_reasons.map((x) => <li key={x.reason} className="flex justify-between px-5 py-2.5 border-b border-line last:border-b-0"><span>{x.reason}</span><span className="tabular-nums">{n(x.count)}</span></li>)}</ul>
                            </Card>
                            {!!d.lost_by_source?.length && (
                                <Card>
                                    <div className="px-5 pt-4 pb-3 border-b border-line">
                                        <h2 className="text-sm font-medium">Lost, by where they came from</h2>
                                        <p className="text-[13px] text-stone-500 mt-0.5">A source that loses many leads for one reason is worth a look.</p>
                                    </div>
                                    <ul className="text-[13px]">
                                        {d.lost_by_source.map((x) => (
                                            <li key={x.source} className="px-5 py-2.5 border-b border-line last:border-b-0">
                                                <div className="flex justify-between gap-3"><span className="font-medium">{sourceLabel(x.source)}</span><span className="tabular-nums">{n(x.lost)}</span></div>
                                                <p className="text-stone-500 mt-0.5">{x.reasons.map((r) => `${r.reason} ${n(r.count)}`).join(" · ")}</p>
                                            </li>
                                        ))}
                                    </ul>
                                </Card>
                            )}
                        </div>
                    )}
                </>
            )}
        </div>
    );
}
