"use client";

import { Notice, SaveBar, Skeleton, useToast } from "@/components/ui";
import { AssistantEmails } from "@/components/email/AssistantEmails";
import { TeamAlerts } from "@/components/integrations/EmailPanel";
import { useIntegrations } from "@/components/integrations/useIntegrations";

export default function EmailAutomationsPage() {
    const toast = useToast();
    const { settings, dirty, saving, save, discard, props } = useIntegrations();
    if (settings.error) return <p className="text-sm text-signal">{settings.error}</p>;
    if (!props) return <Skeleton className="h-96" />;
    return (
        <>
            {!props.draft.server.email && (
                <Notice title="Email sending isn't switched on yet">
                    Everything here is saved, and shows in History, but nothing is delivered until Nimmi&apos;s email service is set up.
                </Notice>
            )}
            <TeamAlerts {...props} />
            <AssistantEmails />
            <SaveBar visible={dirty} saving={saving} onDiscard={discard} onSave={async () => toast(await save())} />
        </>
    );
}
