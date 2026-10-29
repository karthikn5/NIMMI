import type { Metadata } from "next";
import type { ReactNode } from "react";

// The chat window customers' websites embed: not a page of its own for search engines.
export const metadata: Metadata = {
    title: "Chat",
    robots: { index: false, follow: false },
};

export default function WidgetLayout({ children }: { children: ReactNode }) {
    return children;
}
