"use client";

import { useState } from "react";
import { Card, Select, useToast } from "@/components/ui";
import { apiJson } from "@/lib/api";
import { useApi } from "@/lib/useApi";

/** How long the words of emails are kept. After that the text goes; the record that an email was sent stays. */
export function KeepEmails() {
    const toast = useToast();
    const keep = useApi<{ months: number; choices: number[] }>("/api/email/retention");
    const [saving, setSaving] = useState(false);
    if (!keep.data) return null;
    const save = async (months: number) => {
        setSaving(true);
        try {
            keep.setData(await apiJson<{ months: number; choices: number[] }>("/api/email/retention", { method: "PUT", json: { months } }));
            toast("Saved");
        } catch (e) {
            toast((e as Error).message);
        } finally {
            setSaving(false);
        }
    };
    return (
        <Card>
            <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-4">
                <div className="min-w-0 max-w-2xl">
                    <h2 className="text-sm font-medium">How long email text is kept</h2>
                    <p className="text-[13px] text-stone-500 mt-0.5">
                        After this the words of emails and replies are deleted. The record that an email was sent stays, and so do consent and unsubscribes.
                    </p>
                </div>
                <Select aria-label="Keep email text for" className="w-40" value={keep.data.months} disabled={saving} onChange={(e) => save(Number(e.target.value))}>
                    {keep.data.choices.map((m) => <option key={m} value={m}>{m} months</option>)}
                </Select>
            </div>
        </Card>
    );
}
