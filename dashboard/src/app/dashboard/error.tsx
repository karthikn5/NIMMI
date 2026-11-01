"use client";

import { useEffect } from "react";
import Link from "next/link";
import { Button, Card } from "@/components/ui";

/** A dashboard page that failed while drawing, such as in the minute a new version deploys. Reloading brings the newest code, which also cures a chunk that's gone. */
export default function DashboardError({ error }: { error: Error & { digest?: string } }) {
    useEffect(() => { console.error(error); }, [error]);
    return (
        <div className="min-h-screen bg-paper text-ink flex items-center justify-center px-4">
            <Card className="w-full max-w-md p-6">
                <h1 className="text-lg font-semibold tracking-tight">This page didn&apos;t load properly</h1>
                <p className="text-sm text-stone-500 mt-1.5">Everything you saved is safe. Reload the page, and if it happens again, come back in a minute.</p>
                <div className="flex flex-wrap items-center gap-4 mt-5">
                    <Button variant="primary" onClick={() => window.location.reload()}>Reload the page</Button>
                    <Link href="/dashboard" className="text-sm text-plum hover:underline">Go to the dashboard</Link>
                </div>
            </Card>
        </div>
    );
}
