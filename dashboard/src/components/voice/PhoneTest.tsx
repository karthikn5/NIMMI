"use client";

import { useEffect, useState } from "react";
import { Phone } from "lucide-react";
import { Button, Card, Input } from "@/components/ui";
import { apiJson } from "@/lib/api";

/** Ring your own phone from one of your numbers and talk to the assistant. */
export default function PhoneTest({ botId, botName }: { botId: string; botName: string }) {
    const [phone, setPhone] = useState("");
    const [state, setState] = useState<"idle" | "calling" | "done" | "error">("idle");
    const [message, setMessage] = useState("");

    useEffect(() => {
        try { setPhone(localStorage.getItem("nimmi_test_phone") ?? ""); } catch { /* storage blocked */ }
    }, []);

    const call = async (e: React.FormEvent) => {
        e.preventDefault();
        setState("calling");
        setMessage("");
        try {
            const res = await apiJson<{ from: string; to: string }>("/api/voice/test-call", { method: "POST", json: { bot_id: botId, phone } });
            try { localStorage.setItem("nimmi_test_phone", phone); } catch { /* storage blocked */ }
            setState("done");
            setMessage(`Calling ${res.to} from ${res.from}. Pick up to talk to ${botName}.`);
        } catch (err) {
            setState("error");
            setMessage((err as Error).message);
        }
    };

    return (
        <Card className="p-5 mt-4">
            <h2 className="text-[15px] font-semibold">Test on a real phone</h2>
            <p className="text-[13px] text-stone-500 mt-0.5">We&apos;ll ring this number from one of your phone numbers. Uses saved settings and credits.</p>
            <form onSubmit={call} className="flex gap-2 mt-4">
                <Input type="tel" inputMode="tel" required placeholder="+91 98765 43210" aria-label="Your phone number"
                       className="tabular-nums" value={phone} onChange={(e) => setPhone(e.target.value)} />
                <Button type="submit" disabled={state === "calling"}><Phone size={14} /> {state === "calling" ? "Calling…" : "Call me"}</Button>
            </form>
            {message && <p className={`text-[13px] mt-3 ${state === "error" ? "text-signal" : "text-stone-600"}`}>{message}</p>}
        </Card>
    );
}
