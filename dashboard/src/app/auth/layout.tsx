import type { Metadata } from "next";
import type { ReactNode } from "react";

// Sign-in pages: useful to people, not to search results.
export const metadata: Metadata = {
    title: "Account",
    robots: { index: false, follow: true },
};

export default function AuthLayout({ children }: { children: ReactNode }) {
    return children;
}
