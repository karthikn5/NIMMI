"use client";

import { Suspense, useState } from "react";
import { DomainSetup } from "@/components/email/DomainSetup";
import { KeepEmails } from "@/components/email/KeepEmails";
import { MailboxSetup } from "@/components/email/MailboxSetup";
import { SenderSettings } from "@/components/email/SenderSettings";
import { StoppedAddresses } from "@/components/email/StoppedAddresses";

export default function EmailSettingsPage() {
    const [domainsChanged, setDomainsChanged] = useState(0);  // a domain added or removed: the senders' choices change
    return (
        <div className="space-y-6">
            <DomainSetup onChanged={() => setDomainsChanged((n) => n + 1)} />
            <Suspense fallback={null}><MailboxSetup /></Suspense>
            <SenderSettings reloadKey={domainsChanged} />
            <StoppedAddresses />
            <KeepEmails />
        </div>
    );
}
