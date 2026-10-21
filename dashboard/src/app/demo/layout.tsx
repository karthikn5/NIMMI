import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
    title: "Assistant preview | Nimmi AI",
    robots: { index: false, follow: false },
};

export default function DemoLayout({ children }: { children: ReactNode }) {
    return children;
}
