import type { ReactNode } from "react";
import Image from "next/image";
import Link from "next/link";

/** Small centered card for account pages (password reset, invites). */
export default function AuthShell({ title, description, children, footer }: {
    title: string; description?: ReactNode; children: ReactNode; footer?: ReactNode;
}) {
    return (
        <div className="min-h-screen bg-paper text-ink flex flex-col items-center justify-center px-4 py-12">
            <Link href="/" className="flex items-center gap-2 mb-8 rounded focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-plum">
                <Image src="/favicon.png" alt="" width={30} height={30} />
                <span className="text-base font-semibold text-plum tracking-tight">Nimmi AI</span>
            </Link>
            <div className="w-full max-w-sm bg-white border border-line rounded-lg p-6">
                <h1 className="text-lg font-semibold tracking-tight">{title}</h1>
                {description && <p className="text-[13px] text-stone-500 mt-1 leading-relaxed">{description}</p>}
                <div className="mt-5">{children}</div>
            </div>
            {footer && <div className="mt-5 text-[13px] text-stone-500">{footer}</div>}
        </div>
    );
}
