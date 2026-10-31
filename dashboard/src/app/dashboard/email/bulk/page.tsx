"use client";

import { Skeleton } from "@/components/ui";
import { BulkEmail } from "@/components/integrations/BulkEmail";
import { useIntegrations } from "@/components/integrations/useIntegrations";

export default function EmailBulkPage() {
    const { settings, props } = useIntegrations();
    if (settings.error) return <p className="text-sm text-signal">{settings.error}</p>;
    if (!props) return <Skeleton className="h-96" />;
    return <BulkEmail draft={props.draft} saved={props.saved} />;
}
