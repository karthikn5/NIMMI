"use client";

import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { Card } from "@/components/ui";
import { PanelHeader } from "./shared";

/** WhatsApp now has its own section (numbers, Inbox, the assistant's behaviour, files); this points there. */
export function WhatsAppPanel() {
    return (
        <>
            <PanelHeader title="WhatsApp" description="Your assistant answers customers on your WhatsApp Business number, and your team replies from the WhatsApp Inbox." />
            <Card className="p-5">
                <p className="text-sm">WhatsApp has its own section now.</p>
                <p className="text-[13px] text-stone-500 mt-1">
                    Connect your number, choose how the assistant behaves, add files it can send and read every chat in one place. The
                    confirmation sent after phone calls is under WhatsApp &gt; Settings.
                </p>
                <Link href="/dashboard/whatsapp" className="mt-4 inline-flex items-center gap-1.5 h-9 px-4 rounded-md bg-plum text-white text-sm font-medium hover:bg-plum-hover">
                    Open WhatsApp <ArrowRight size={14} />
                </Link>
            </Card>
        </>
    );
}
