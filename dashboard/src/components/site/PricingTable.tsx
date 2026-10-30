"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowRight, Check } from "lucide-react";
import { cn } from "./cn";
import { TIERS, YEARLY_PAYS_FOR, inr, perMonth } from "@/lib/plans";

export default function PricingTable() {
    const [yearly, setYearly] = useState(true);

    return (
        <div className="mt-10">
            <div role="radiogroup" aria-label="Billing period" className="inline-flex p-0.5 bg-stone-200/60 rounded-md text-[14px]">
                {([[false, "Monthly"], [true, "Yearly, 2 months free"]] as const).map(([value, label]) => (
                    <button key={label} type="button" role="radio" aria-checked={yearly === value} onClick={() => setYearly(value)}
                            className={cn("h-9 px-4 rounded-[5px] transition-colors focus-visible:outline-2 focus-visible:outline-plum",
                                          yearly === value ? "bg-white text-ink font-medium shadow-[0_1px_2px_rgba(0,0,0,0.08)]" : "text-stone-600 hover:text-ink")}>
                        {label}
                    </button>
                ))}
            </div>

            <div data-reveal className="grid lg:grid-cols-3 gap-px bg-line border border-line rounded-lg overflow-hidden mt-6">
                {TIERS.map((t) => {
                    const monthly = perMonth(t, yearly ? "yearly" : "monthly");
                    return (
                        <div key={t.name} className={cn("flex flex-col p-6 sm:p-7", t.featured ? "bg-plum-tint/60" : "bg-white")}>
                            <div className="flex items-center justify-between gap-2">
                                <h3 className="font-display text-[19px] font-medium">{t.name}</h3>
                                {t.featured && <span className="text-[12px] font-medium text-plum">Recommended</span>}
                            </div>
                            <p className="text-[14px] text-stone-600 mt-1">{t.summary}</p>
                            <p className="mt-5 flex items-baseline gap-1.5">
                                <span className="font-display text-[38px] leading-none font-medium tracking-tight tabular-nums">{inr(monthly)}</span>
                                <span className="text-[14px] text-stone-500">a month</span>
                            </p>
                            <p className="text-[13px] text-stone-500 mt-2 h-5">
                                {yearly ? `${inr(t.monthly * YEARLY_PAYS_FOR)} billed yearly` : "Billed monthly, cancel any time"}
                            </p>
                            <Link href="/auth/signup" className={cn(
                                "mt-6 inline-flex items-center justify-center gap-2 h-11 rounded-md text-[15px] font-medium transition-colors",
                                "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-plum",
                                t.featured ? "bg-plum text-white hover:bg-plum-hover" : "border border-line-strong bg-white text-ink hover:bg-stone-50",
                            )}>
                                Start free <ArrowRight size={15} />
                            </Link>
                            <p className="text-[13px] font-medium mt-7 mb-3">{t.previous ? `Everything in ${t.previous}, plus` : "Includes"}</p>
                            <ul className="space-y-2.5">
                                {t.includes.map((i) => (
                                    <li key={i} className="flex gap-2.5 text-[14px] leading-snug text-stone-700">
                                        <Check size={15} className="text-plum shrink-0 mt-0.5" aria-hidden />{i}
                                    </li>
                                ))}
                            </ul>
                        </div>
                    );
                })}
            </div>
        </div>
    );
}
