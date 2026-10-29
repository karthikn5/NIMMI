"use client";

import { Suspense, use, useEffect, useState, type ComponentType, type ReactNode } from "react";
import Image from "next/image";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { ArrowLeft, Check, CircleAlert, Headset, Link2, MessageCircle, MessagesSquare, Mic, PenLine, RotateCcw, UserRound } from "lucide-react";
import { apiBase, apiUrl, getToken } from "@/lib/api";
import { assetUrl } from "@/app/dashboard/builder/[id]/components/design";
import { Button, Card, Skeleton, Status, cn } from "@/components/ui";

type Config = { bot_name?: string; visual_config?: { logo_url?: string; position?: string } | null };

const TRY: { icon: ComponentType<{ size?: number; className?: string }>; title: string; body: string }[] = [
    { icon: MessagesSquare, title: "Ask what your customers ask", body: "Prices, timings, location, how to book. It answers only from the knowledge you added." },
    { icon: UserRound, title: "Share a name, phone number or email", body: "It's saved to Leads, and the assistant won't ask for it again." },
    { icon: Mic, title: "Speak instead of typing", body: "Tap the mic and talk in English or your own language." },
    { icon: Headset, title: "Ask to talk to a person", body: "Your team picks up the conversation from Live chat." },
];

/** Everything the widget remembers about this visitor, so "new conversation" really starts fresh. */
const visitorKeys = (id: string) => [`nimmi_chat_history_${id}`, `nimmi_visitor_${id}`, `nimmi_history_${id}`];

function useBotId(params: Promise<{ id: string }>) {
    const { id } = use(params);
    const searchParams = useSearchParams();
    if (id && id !== "undefined" && id.length > 5) return id;
    return searchParams.get("id") || "";
}

function DemoContent({ params }: { params: Promise<{ id: string }> }) {
    const id = useBotId(params);
    const [config, setConfig] = useState<Config | null>(null);
    const [error, setError] = useState<string | null>(id ? null : "This preview link is missing the assistant's ID.");
    const [signedIn, setSignedIn] = useState(false);
    const [copied, setCopied] = useState(false);
    const [link, setLink] = useState("");

    useEffect(() => {
        setSignedIn(!!getToken());
        setLink(window.location.href.split("#")[0]);
    }, []);

    useEffect(() => {
        if (!id) return;
        let cancelled = false;
        fetch(apiUrl(`/api/bots/${id}/config`))
            .then(async (res) => {
                if (cancelled) return;
                if (res.ok) setConfig(await res.json());
                else setError(res.status === 404 || res.status === 400 ? "This assistant doesn't exist, or it was deleted." : "We couldn't load this assistant. Try again in a moment.");
            })
            .catch(() => !cancelled && setError("We couldn't reach Nimmi. Check your connection and try again."));
        return () => { cancelled = true; };
    }, [id]);

    // Once the assistant is known to exist: the same embed script customers paste on their sites,
    // so this is the real widget.
    const ready = !!config;
    useEffect(() => {
        if (!ready) return;
        const base = apiBase();
        const w = window as Window & { __NIMMI_WIDGET_LOADED__?: boolean };
        w.__NIMMI_WIDGET_LOADED__ = false;
        const script = document.createElement("script");
        script.src = `${base}/static/nimmi-widget.js?v=${Date.now()}`;
        script.setAttribute("data-bot-id", id);
        script.setAttribute("data-api-url", base);
        script.setAttribute("data-dashboard-url", window.location.origin);
        script.setAttribute("data-is-demo", "true");
        script.async = true;
        document.body.appendChild(script);
        return () => {
            script.remove();
            document.getElementById("nimmi-widget-container")?.remove();
            w.__NIMMI_WIDGET_LOADED__ = false;
        };
    }, [ready, id]);

    const openAssistant = () => window.postMessage("open-nimmi-widget", window.location.origin);
    const restart = () => {
        try {
            visitorKeys(id).forEach((k) => localStorage.removeItem(k));
        } catch { /* storage blocked: a reload still restarts the flow */ }
        window.location.reload();
    };
    const copyLink = async () => {
        try {
            await navigator.clipboard.writeText(link);
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        } catch { /* the link stays selectable in the field */ }
    };

    const botName = config?.bot_name || "Assistant";
    const logo = config?.visual_config?.logo_url;
    const corner = config?.visual_config?.position === "left" ? "bottom-left" : "bottom-right";

    return (
        <div className="min-h-screen flex flex-col bg-paper text-ink">
            <header className="sticky top-0 z-30 h-14 shrink-0 bg-white/90 backdrop-blur border-b border-line">
                <div className="h-full max-w-6xl mx-auto flex items-center gap-2 sm:gap-3 px-2 sm:px-6">
                    {signedIn ? (
                        <Link href={`/dashboard/builder/${id}`} aria-label="Back to the builder" className="p-2 rounded-md text-stone-500 hover:text-ink hover:bg-stone-100">
                            <ArrowLeft size={18} />
                        </Link>
                    ) : (
                        <Link href="/" className="flex items-center gap-2 pl-2 pr-1 rounded-md focus-visible:outline-2 focus-visible:outline-plum">
                            <Image src="/favicon.png" alt="" width={24} height={24} />
                            <span className="hidden sm:inline text-[15px] font-semibold text-plum tracking-tight">Nimmi AI</span>
                        </Link>
                    )}
                    {!error && (
                        <div className="flex items-center gap-2.5 min-w-0">
                            <span className="h-5 w-px bg-line hidden sm:block" aria-hidden />
                            <Avatar name={botName} logo={logo} loading={!config} />
                            <span className="text-sm font-semibold truncate max-w-[8rem] sm:max-w-[16rem]">{config ? botName : "Loading…"}</span>
                            <span className="hidden sm:inline-flex items-center h-6 px-2 rounded-full bg-plum-tint text-[12px] font-medium text-plum">Preview</span>
                        </div>
                    )}
                    <div className="ml-auto flex items-center gap-2">
                        {!error && (
                            <Button size="sm" onClick={restart} aria-label="Start a new conversation">
                                <RotateCcw size={14} /> <span className="hidden sm:inline">New conversation</span>
                            </Button>
                        )}
                        {signedIn ? (
                            <Link href={`/dashboard/builder/${id}`}
                                  className="inline-flex items-center gap-1.5 h-8 px-3 rounded-md bg-plum text-white text-[13px] font-medium hover:bg-plum-hover transition-colors">
                                <PenLine size={14} /> <span className="hidden sm:inline">Edit assistant</span><span className="sm:hidden">Edit</span>
                            </Link>
                        ) : (
                            <Link href="/auth/signup"
                                  className="inline-flex items-center h-8 px-3 rounded-md bg-plum text-white text-[13px] font-medium hover:bg-plum-hover transition-colors">
                                Build your own
                            </Link>
                        )}
                    </div>
                </div>
            </header>

            {/* A quiet dotted canvas: this page stands in for the business's own website. */}
            <main className="flex-1 bg-[radial-gradient(var(--color-line-strong)_1px,transparent_1px)] [background-size:22px_22px]">
                {/* Bottom padding keeps the last card clear of the chat button. */}
                <div className="max-w-6xl mx-auto px-4 sm:px-6 pt-10 sm:pt-16 pb-28">
                    <div className="max-w-xl">
                        {error ? (
                            <Card className="p-6 sm:p-8">
                                <CircleAlert size={22} className="text-stone-400" aria-hidden />
                                <h1 className="mt-4 text-xl font-semibold tracking-tight">This preview isn&apos;t available</h1>
                                <p className="mt-1.5 text-[14px] text-stone-600 leading-relaxed">{error}</p>
                                <div className="mt-6">
                                    <Link href={signedIn ? "/dashboard" : "/"}
                                          className="inline-flex items-center h-9 px-4 rounded-md border border-line-strong bg-white text-sm font-medium hover:bg-stone-50">
                                        {signedIn ? "Go to your assistants" : "Go to Nimmi AI"}
                                    </Link>
                                </div>
                            </Card>
                        ) : (
                            <>
                                <Status tone="good">Live preview</Status>
                                {config ? (
                                    <h1 className="mt-3 text-[32px] sm:text-[40px] leading-[1.1] font-semibold tracking-[-0.02em] text-balance">Try {botName}</h1>
                                ) : (
                                    <Skeleton className="mt-4 h-10 w-64" />
                                )}
                                <p className="mt-3 text-[15px] leading-relaxed text-stone-600">
                                    This is the assistant exactly as visitors see it on a website, with its knowledge, flow and design.
                                    Open it from the {corner} corner and chat the way a customer would.
                                </p>
                                <div className="mt-6 flex flex-wrap gap-2">
                                    <button type="button" onClick={openAssistant}
                                            className="inline-flex items-center gap-2 h-10 px-4 rounded-md bg-plum text-white text-sm font-medium hover:bg-plum-hover transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-plum">
                                        <MessageCircle size={16} /> Open the assistant
                                    </button>
                                    <button type="button" onClick={restart}
                                            className="inline-flex items-center gap-2 h-10 px-4 rounded-md border border-line-strong bg-white text-sm font-medium hover:bg-stone-50 transition-colors">
                                        <RotateCcw size={15} /> Start over
                                    </button>
                                </div>

                                <Card className="mt-10 overflow-hidden">
                                    <div className="px-5 py-4 border-b border-line">
                                        <h2 className="text-[15px] font-semibold">Things to try</h2>
                                        <p className="text-[13px] text-stone-500 mt-0.5">A quick check before you add it to your website.</p>
                                    </div>
                                    <ul className="divide-y divide-line">
                                        {TRY.map(({ icon: Icon, title, body }) => (
                                            <li key={title} className="flex gap-3.5 px-5 py-3.5">
                                                <span className="h-8 w-8 shrink-0 rounded-md bg-plum-tint text-plum flex items-center justify-center" aria-hidden>
                                                    <Icon size={16} />
                                                </span>
                                                <span>
                                                    <span className="block text-[14px] font-medium">{title}</span>
                                                    <span className="block text-[13px] text-stone-500 leading-relaxed">{body}</span>
                                                </span>
                                            </li>
                                        ))}
                                    </ul>
                                </Card>

                                <Card className="mt-4 p-5">
                                    <h2 className="text-[15px] font-semibold">Share this preview</h2>
                                    <p className="text-[13px] text-stone-500 mt-0.5">Send it to a colleague or client. Anyone with the link can chat with this assistant.</p>
                                    <div className="mt-3 flex gap-2">
                                        <input readOnly value={link} aria-label="Preview link" onFocus={(e) => e.currentTarget.select()}
                                               className="min-w-0 flex-1 h-9 px-3 rounded-md border border-line-strong bg-stone-50 text-[13px] text-stone-600 outline-none focus:border-plum" />
                                        <Button onClick={copyLink} className={cn(copied && "text-emerald-700")}>
                                            {copied ? <><Check size={14} /> Copied</> : <><Link2 size={14} /> Copy link</>}
                                        </Button>
                                    </div>
                                </Card>

                                <p className="mt-6 text-[12px] text-stone-500">
                                    Saved changes from the builder appear here when you start over.
                                    {!signedIn && <> Made with <Link href="/" className="text-plum hover:underline">Nimmi AI</Link>.</>}
                                </p>
                            </>
                        )}
                    </div>
                </div>
            </main>
        </div>
    );
}

function Avatar({ name, logo, loading }: { name: string; logo?: string; loading: boolean }): ReactNode {
    if (loading) return <Skeleton className="h-7 w-7 rounded-full" />;
    return (
        <span className="h-7 w-7 shrink-0 rounded-full border border-line bg-stone-50 overflow-hidden flex items-center justify-center text-[12px] font-semibold text-stone-500">
            {logo ? <img src={assetUrl(logo)} alt="" className="h-full w-full object-cover object-top" /> : name.slice(0, 1).toUpperCase()}
        </span>
    );
}

export default function DemoPage({ params }: { params: Promise<{ id: string }> }) {
    return (
        <Suspense fallback={<div className="min-h-screen bg-paper" />}>
            <DemoContent params={params} />
        </Suspense>
    );
}
