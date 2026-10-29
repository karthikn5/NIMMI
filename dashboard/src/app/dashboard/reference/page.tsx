"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import {
    Play,
    Pause,
    RotateCcw,
    Check,
    Copy,
    Clock,
    ArrowRight,
    Bot,
    Palette,
    Database,
    GitBranch,
    FileText,
    Volume2,
    VolumeX,
    ExternalLink,
    CheckCircle2,
    SlidersHorizontal,
    MonitorPlay,
    Layers,
    Upload,
    Link2,
    Video,
} from "lucide-react";
import AppHeader from "@/components/AppHeader";
import { Button, Card, ToastProvider, useToast } from "@/components/ui";

type Chapter = {
    id: number;
    title: string;
    duration: string;
    seconds: number;
    description: string;
    screenImg: string;
    badge: string;
    steps: string[];
    actionHref: string;
    actionLabel: string;
    script: string;
};

const CHAPTERS: Chapter[] = [
    {
        id: 1,
        title: "Create your Chatbot",
        duration: "0:45",
        seconds: 0,
        badge: "Step 1",
        description: "Set up a new assistant in your workspace with brand naming and initial settings.",
        screenImg: "/screens/agent-1200.webp",
        steps: [
            "Log in to your Nimmi AI dashboard at /dashboard.",
            "Click on '+ New Assistant' in the top right corner.",
            "Provide a clear, recognizable name matching your business or brand.",
            "Select your workspace and confirm creation.",
            "You are immediately directed into the Assistant Builder.",
        ],
        actionHref: "/dashboard",
        actionLabel: "Go to Assistants",
        script:
            "Welcome to Nimmi AI. In this guide, you will learn how to build, train, and test your first AI assistant in just a few minutes. Let us start by creating a new assistant. From your dashboard, click New Assistant. Give your assistant a clear name that matches your brand, select your workspace, and click create. Within seconds, your assistant is initialized and you are brought directly into the assistant builder.",
    },
    {
        id: 2,
        title: "Design and Builder Modules",
        duration: "0:45",
        seconds: 45,
        badge: "Step 2",
        description: "Customize appearance, colors, avatars, and understand the five builder modules.",
        screenImg: "/screens/livechat-1200.webp",
        steps: [
            "Review the primary builder navigation tabs: Design, Knowledge, Behaviour, Flow, and Leads.",
            "Under the Design tab, customize your brand's primary color and dark or light mode.",
            "Upload your company logo or assistant avatar image.",
            "Set a friendly welcoming greeting message for first-time visitors.",
            "Inspect the live interactive preview on the right panel as changes update in real time.",
        ],
        actionHref: "/dashboard",
        actionLabel: "Open Builder Design",
        script:
            "Inside the builder, you have complete control over how your assistant looks, learns, and behaves. The Design tab allows you to match the chat widget to your company branding. You can customize the primary color, upload your brand logo or avatar, and set a welcoming headline that greets visitors the moment they land on your site. Notice how every change you make updates instantly in the live preview on the right.",
    },
    {
        id: 3,
        title: "Knowledge Base and Web Scraping",
        duration: "1:15",
        seconds: 90,
        badge: "Step 3",
        description: "Index your live website, upload PDF documents, and add custom question and answer pairs.",
        screenImg: "/screens/data-1200.webp",
        steps: [
            "Navigate to the Knowledge tab inside the assistant builder.",
            "Choose your data source: Documents, Custom Q and A, or Web Scraping.",
            "For website scraping: paste your website URL (e.g. https://yourbusiness.com).",
            "Click 'Crawl and Sync' to automatically extract page text and generate vector embeddings.",
            "Verify indexed pages, document status, and character counts in your knowledge bank.",
        ],
        actionHref: "/dashboard",
        actionLabel: "View Knowledge Sources",
        script:
            "Next, let us give your assistant intelligence using the Knowledge tab. Your assistant can learn from PDF documents, support manuals, custom Q and A pairs, or your existing website. To scrape your website, click on Web Scraping, paste your website URL, and click start. Nimmi AI will automatically crawl your site, extract the content, and index it into vector storage. Once synced, your assistant can answer complex customer queries with accurate, real-time facts about your business.",
    },
    {
        id: 4,
        title: "Visual Flow Builder and Lead Capture",
        duration: "1:05",
        seconds: 165,
        badge: "Step 4",
        description: "Build visual conversation branching, prompt buttons, and capture verified leads.",
        screenImg: "/screens/contacts-1200.webp",
        steps: [
            "Switch to the Flow tab to open the visual drag-and-drop workflow canvas.",
            "Drag a Lead Capture node onto the canvas.",
            "Configure the fields to collect: Name, Email address, and Phone number.",
            "Connect nodes to guide visitors from greeting directly to qualification.",
            "Check the Leads tab to view incoming captured contacts, timestamps, and export options.",
        ],
        actionHref: "/dashboard",
        actionLabel: "View Flow Canvas",
        script:
            "To convert visitors into customers, head over to the Flow tab. Nimmi AI includes a visual flow builder that lets you guide conversations and capture high-intent leads automatically. You can add prompt cards, multiple-choice buttons, or a lead capture block. When a visitor engages, the bot collects their name, email, and phone number before handing off or answering further questions. All submitted leads are organized in your Leads tab, where you can view, filter, or export them at any time.",
    },
    {
        id: 5,
        title: "Test Run and Website Embed",
        duration: "0:55",
        seconds: 230,
        badge: "Step 5",
        description: "Simulate real visitor conversations, verify knowledge retrieval, and copy the embed script.",
        screenImg: "/screens/agent-1200.webp",
        steps: [
            "Open the Test Chat panel located on the right side of the builder.",
            "Ask realistic questions like 'What are your pricing plans?' or 'Can I schedule a call?'.",
            "Verify citations and ensure answers reflect the synced knowledge base.",
            "Click the 'Add to website' button in the builder top bar.",
            "Copy the one-line JavaScript embed script and paste it into your site header.",
        ],
        actionHref: "/dashboard",
        actionLabel: "Test and Embed",
        script:
            "Before launching to the public, you can test everything right here in the builder. In the preview panel on your right, send a test message as if you were a customer. You can verify how the bot formats responses, applies your business tone, and handles lead capture. Once you are satisfied, click Add to website in the top bar. Copy the one-line script tag, paste it into your website header, and your AI assistant is live.",
    },
];

export default function ReferencePage() {
    return (
        <ToastProvider>
            <div className="min-h-screen bg-paper text-ink pb-24">
                <AppHeader />
                <ReferenceContent />
            </div>
        </ToastProvider>
    );
}

function ReferenceContent() {
    const toast = useToast();
    const videoRef = useRef<HTMLVideoElement>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);
    const [videoSrc, setVideoSrc] = useState<string>("/videos/tutorial.mp4");
    const [videoFileName, setVideoFileName] = useState<string>("");
    const [activeChapterIndex, setActiveChapterIndex] = useState(0);
    const [isPlaying, setIsPlaying] = useState(false);
    const [videoFound, setVideoFound] = useState<boolean | null>(null);
    const [isMuted, setIsMuted] = useState(false);
    const [activeTab, setActiveTab] = useState<"walkthrough" | "script" | "production">("walkthrough");

    const currentChapter = CHAPTERS[activeChapterIndex];

    const handleVideoFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (file) {
            const url = URL.createObjectURL(file);
            setVideoSrc(url);
            setVideoFileName(file.name);
            setVideoFound(true);
            toast(`Loaded ${file.name}`);
            setTimeout(() => {
                if (videoRef.current) {
                    videoRef.current.play().then(() => setIsPlaying(true)).catch(() => {});
                }
            }, 300);
        }
    };

    // Jump video to chapter start time
    const selectChapter = (index: number) => {
        setActiveChapterIndex(index);
        const targetSeconds = CHAPTERS[index].seconds;
        if (videoRef.current && videoFound) {
            videoRef.current.currentTime = targetSeconds;
            videoRef.current.play().then(() => setIsPlaying(true)).catch(() => {});
        }
    };

    const togglePlay = () => {
        if (!videoRef.current) return;
        if (isPlaying) {
            videoRef.current.pause();
            setIsPlaying(false);
        } else {
            videoRef.current.play().then(() => setIsPlaying(true)).catch(() => {});
        }
    };

    const copyText = (text: string, label: string) => {
        navigator.clipboard.writeText(text);
        toast(`Copied ${label} to clipboard`);
    };

    const fullScriptText = CHAPTERS.map(
        (c) => `[${c.duration}] CHAPTER ${c.id}: ${c.title.toUpperCase()}\n${c.script}\n`
    ).join("\n");

    return (
        <main className="max-w-6xl mx-auto px-4 sm:px-6 py-8">
            {/* Hidden file input for previewing any local video */}
            <input
                ref={fileInputRef}
                type="file"
                accept="video/mp4,video/webm,video/quicktime,video/*"
                onChange={handleVideoFileSelect}
                className="hidden"
            />
            {/* Header */}
            <div className="mb-8">
                <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-stone-100 text-stone-700 text-xs font-medium mb-3">
                    <MonitorPlay className="w-3.5 h-3.5 text-plum" />
                    Reference and Video Guides
                </div>
                <h1 className="text-2xl sm:text-3xl font-semibold text-ink tracking-tight">
                    Assistant Masterclass and Walkthrough
                </h1>
                <p className="text-stone-500 text-sm sm:text-base mt-1.5 max-w-3xl">
                    Follow the complete five-step workflow to build, train, configure, and deploy your AI chatbot.
                    Use the video player and chapters below to jump directly to any topic.
                </p>
            </div>

            {/* Video Player and Chapter Rail */}
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start mb-10">
                {/* Main Player Display (8 columns) */}
                <div className="lg:col-span-8">
                    <Card className="overflow-hidden border border-line shadow-sm bg-stone-900 text-white">
                        {/* Video viewport */}
                        <div className="relative aspect-video w-full bg-black flex items-center justify-center overflow-hidden">
                            {/* Native HTML5 Video Element */}
                            <video
                                ref={videoRef}
                                src={videoSrc}
                                key={videoSrc}
                                className={`w-full h-full object-contain ${videoFound === false ? "hidden" : "block"}`}
                                controls
                                onPlay={() => setIsPlaying(true)}
                                onPause={() => setIsPlaying(false)}
                                onLoadedData={() => setVideoFound(true)}
                                onError={() => setVideoFound(false)}
                            />

                            {/* Fallback / Interactive Screen Walkthrough Mode when video file is not yet placed */}
                            {videoFound === false && (
                                <div className="absolute inset-0 flex flex-col justify-between p-5 sm:p-6 bg-gradient-to-t from-black via-stone-900/95 to-stone-900">
                                    <div className="flex items-center justify-between text-xs text-stone-400">
                                        <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded bg-stone-800/80 border border-stone-700 text-stone-300">
                                            <span className="w-2 h-2 rounded-full bg-plum animate-pulse" />
                                            Interactive Walkthrough Mode
                                        </div>
                                        <span className="text-stone-400 font-mono">
                                            {currentChapter.badge} - {currentChapter.duration}
                                        </span>
                                    </div>

                                    {/* Center preview representation */}
                                    <div className="my-auto text-center px-4">
                                        <div className="relative mx-auto w-full max-w-sm aspect-[16/10] rounded-lg overflow-hidden border border-stone-700/80 shadow-2xl bg-stone-950 mb-2.5">
                                            <Image
                                                src={currentChapter.screenImg}
                                                alt={currentChapter.title}
                                                fill
                                                className="object-cover object-top opacity-90 hover:opacity-100 transition-opacity"
                                            />
                                            <div className="absolute inset-0 bg-gradient-to-t from-stone-950/80 via-transparent to-transparent flex items-end p-2.5">
                                                <p className="text-[11px] text-stone-300 text-left line-clamp-2">
                                                    {currentChapter.description}
                                                </p>
                                            </div>
                                        </div>
                                        <h2 className="text-base sm:text-lg font-semibold text-white tracking-tight">
                                            {currentChapter.title}
                                        </h2>

                                        {/* Direct File Picker Action Button */}
                                        <div className="mt-3 flex items-center justify-center gap-2">
                                            <button
                                                type="button"
                                                onClick={() => fileInputRef.current?.click()}
                                                className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-md text-xs font-medium bg-plum text-white hover:bg-plum-hover shadow-sm transition-colors cursor-pointer"
                                            >
                                                <Upload className="w-3.5 h-3.5" />
                                                Choose Video File from Computer
                                            </button>
                                        </div>
                                    </div>

                                    {/* Action Bar inside fallback */}
                                    <div className="pt-2 border-t border-stone-800 flex items-center justify-between text-xs text-stone-400">
                                        <span className="truncate pr-2 text-[11px]">
                                            Permanent stream: place file at <code className="text-plum-light font-mono">public/videos/tutorial.mp4</code>
                                        </span>
                                        <div className="flex items-center gap-2 shrink-0">
                                            <button
                                                onClick={() =>
                                                    setActiveChapterIndex((prev) => (prev > 0 ? prev - 1 : CHAPTERS.length - 1))
                                                }
                                                className="px-2.5 py-1 rounded bg-stone-800 hover:bg-stone-700 text-stone-200 transition-colors"
                                            >
                                                Previous
                                            </button>
                                            <button
                                                onClick={() =>
                                                    setActiveChapterIndex((prev) => (prev < CHAPTERS.length - 1 ? prev + 1 : 0))
                                                }
                                                className="px-2.5 py-1 rounded bg-plum text-white hover:bg-plum-hover transition-colors font-medium"
                                            >
                                                Next Step
                                            </button>
                                        </div>
                                    </div>
                                </div>
                            )}
                        </div>

                        {/* Player Status / Chapter Title Bar */}
                        <div className="p-4 bg-stone-950 border-t border-stone-800 flex flex-wrap items-center justify-between gap-3 text-sm">
                            <div className="flex items-center gap-3">
                                <span className="px-2 py-0.5 rounded text-[11px] font-semibold uppercase tracking-wider bg-plum/20 text-plum-light border border-plum/30">
                                    {currentChapter.badge}
                                </span>
                                <h3 className="font-medium text-white">{currentChapter.title}</h3>
                            </div>
                            <div className="flex items-center gap-2">
                                <button
                                    type="button"
                                    onClick={() => fileInputRef.current?.click()}
                                    className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-medium bg-stone-800 hover:bg-stone-700 text-stone-300 transition-colors border border-stone-700 cursor-pointer"
                                >
                                    <Upload className="w-3.5 h-3.5" />
                                    {videoFileName ? "Change Video" : "Load Video File"}
                                </button>
                                {videoFileName && (
                                    <span className="text-[11px] text-stone-400 font-mono truncate max-w-[120px]">
                                        {videoFileName}
                                    </span>
                                )}
                                <Link
                                    href={currentChapter.actionHref}
                                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium bg-stone-800 hover:bg-stone-700 text-stone-200 transition-colors border border-stone-700"
                                >
                                    {currentChapter.actionLabel}
                                    <ArrowRight className="w-3.5 h-3.5" />
                                </Link>
                            </div>
                        </div>
                    </Card>

                    {/* Chapter Narration and Action Details */}
                    <Card className="mt-4 p-5 bg-white border border-line">
                        <div className="flex items-center justify-between gap-2 border-b border-line pb-3 mb-4">
                            <div>
                                <span className="text-xs font-semibold text-plum uppercase tracking-wider">
                                    {currentChapter.badge} Breakdown
                                </span>
                                <h2 className="text-base font-semibold text-ink mt-0.5">{currentChapter.title}</h2>
                            </div>
                            <Button
                                size="sm"
                                variant="secondary"
                                onClick={() => copyText(currentChapter.script, "voiceover script")}
                                className="text-xs"
                            >
                                <Copy className="w-3.5 h-3.5" />
                                Copy Audio Script
                            </Button>
                        </div>

                        {/* Step by step instructions */}
                        <div className="space-y-2 mb-5">
                            <h3 className="text-xs font-medium text-stone-500 uppercase tracking-wider">Step-by-Step Action</h3>
                            <ul className="space-y-1.5">
                                {currentChapter.steps.map((step, i) => (
                                    <li key={i} className="flex items-start gap-2 text-sm text-ink">
                                        <CheckCircle2 className="w-4 h-4 text-plum shrink-0 mt-0.5" />
                                        <span>{step}</span>
                                    </li>
                                ))}
                            </ul>
                        </div>

                        {/* Script preview */}
                        <div className="rounded-md bg-stone-50 border border-line p-3 text-xs text-stone-600 leading-relaxed">
                            <div className="font-semibold text-stone-700 mb-1 flex items-center gap-1.5">
                                <Volume2 className="w-3.5 h-3.5 text-stone-500" />
                                Synchronized Voiceover Script
                            </div>
                            &quot;{currentChapter.script}&quot;
                        </div>
                    </Card>
                </div>

                {/* Chapter Rail / Sidebar (4 columns) */}
                <div className="lg:col-span-4 space-y-4">
                    <Card className="p-4 bg-white border border-line">
                        <div className="flex items-center justify-between mb-3 pb-2 border-b border-line">
                            <h2 className="text-sm font-semibold text-ink flex items-center gap-1.5">
                                <Layers className="w-4 h-4 text-plum" />
                                Video Chapters
                            </h2>
                            <span className="text-xs text-stone-500 font-mono">5 Modules</span>
                        </div>

                        <div className="space-y-2">
                            {CHAPTERS.map((ch, idx) => {
                                const isActive = idx === activeChapterIndex;
                                return (
                                    <button
                                        key={ch.id}
                                        onClick={() => selectChapter(idx)}
                                        className={`w-full text-left p-3 rounded-lg border transition-all text-xs flex flex-col gap-1.5 ${
                                            isActive
                                                ? "bg-plum/5 border-plum text-plum font-medium shadow-sm"
                                                : "bg-white border-line text-stone-600 hover:bg-stone-50 hover:text-ink"
                                        }`}
                                    >
                                        <div className="flex items-center justify-between">
                                            <span
                                                className={`px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wide ${
                                                    isActive
                                                        ? "bg-plum text-white"
                                                        : "bg-stone-100 text-stone-600"
                                                }`}
                                            >
                                                {ch.badge}
                                            </span>
                                            <span className="font-mono text-[11px] text-stone-400 flex items-center gap-1">
                                                <Clock className="w-3 h-3" />
                                                {ch.duration}
                                            </span>
                                        </div>
                                        <div className="font-medium text-ink text-[13px]">{ch.title}</div>
                                        <p className="text-[11px] text-stone-500 line-clamp-1 leading-normal">
                                            {ch.description}
                                        </p>
                                    </button>
                                );
                            })}
                        </div>
                    </Card>

                    {/* Quick Start Card */}
                    <Card className="p-4 bg-stone-50 border border-line text-xs">
                        <h2 className="font-semibold text-ink mb-1 flex items-center gap-1.5">
                            <Bot className="w-3.5 h-3.5 text-plum" />
                            Direct Builder Links
                        </h2>
                        <p className="text-stone-500 mb-3">Jump right into the corresponding tools in your dashboard:</p>
                        <div className="space-y-1.5">
                            <Link
                                href="/dashboard"
                                className="flex items-center justify-between p-2 rounded bg-white border border-line text-ink hover:border-plum transition-colors"
                            >
                                <span>Assistants Dashboard</span>
                                <ArrowRight className="w-3 h-3 text-stone-400" />
                            </Link>
                            <Link
                                href="/dashboard/questions"
                                className="flex items-center justify-between p-2 rounded bg-white border border-line text-ink hover:border-plum transition-colors"
                            >
                                <span>Unanswered Questions</span>
                                <ArrowRight className="w-3 h-3 text-stone-400" />
                            </Link>
                            <Link
                                href="/dashboard/integrations"
                                className="flex items-center justify-between p-2 rounded bg-white border border-line text-ink hover:border-plum transition-colors"
                            >
                                <span>Integrations & Webhooks</span>
                                <ArrowRight className="w-3 h-3 text-stone-400" />
                            </Link>
                        </div>
                    </Card>
                </div>
            </div>

            {/* Production Guidelines and Full Script Reference Section */}
            <div className="mt-12">
                <div className="border-b border-line mb-6 flex items-center gap-4">
                    <button
                        onClick={() => setActiveTab("walkthrough")}
                        className={`pb-3 text-sm font-medium border-b-2 transition-colors ${
                            activeTab === "walkthrough"
                                ? "border-plum text-plum font-semibold"
                                : "border-transparent text-stone-500 hover:text-ink"
                        }`}
                    >
                        Module Documentation
                    </button>
                    <button
                        onClick={() => setActiveTab("script")}
                        className={`pb-3 text-sm font-medium border-b-2 transition-colors ${
                            activeTab === "script"
                                ? "border-plum text-plum font-semibold"
                                : "border-transparent text-stone-500 hover:text-ink"
                        }`}
                    >
                        Full AI Voiceover Script
                    </button>
                    <button
                        onClick={() => setActiveTab("production")}
                        className={`pb-3 text-sm font-medium border-b-2 transition-colors ${
                            activeTab === "production"
                                ? "border-plum text-plum font-semibold"
                                : "border-transparent text-stone-500 hover:text-ink"
                        }`}
                    >
                        Recording & Voice Setup
                    </button>
                </div>

                {/* Tab 1: Module Documentation Cards */}
                {activeTab === "walkthrough" && (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
                        {CHAPTERS.map((ch) => (
                            <Card key={ch.id} className="p-5 bg-white border border-line flex flex-col justify-between">
                                <div>
                                    <div className="flex items-center justify-between mb-2">
                                        <span className="text-[11px] font-semibold text-plum uppercase tracking-wider">
                                            {ch.badge}
                                        </span>
                                        <span className="text-[11px] font-mono text-stone-400">{ch.duration}</span>
                                    </div>
                                    <h3 className="text-base font-semibold text-ink mb-1.5">{ch.title}</h3>
                                    <p className="text-xs text-stone-500 mb-4">{ch.description}</p>
                                    <div className="space-y-1 mb-4">
                                        {ch.steps.slice(0, 3).map((st, i) => (
                                            <div key={i} className="text-xs text-stone-600 flex items-start gap-1.5">
                                                <span className="text-stone-400 font-mono mt-0.5">•</span>
                                                <span className="line-clamp-1">{st}</span>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                                <div className="pt-3 border-t border-line flex items-center justify-between">
                                    <button
                                        onClick={() => selectChapter(ch.id - 1)}
                                        className="text-xs text-plum font-medium hover:underline inline-flex items-center gap-1"
                                    >
                                        Jump to chapter
                                        <ArrowRight className="w-3 h-3" />
                                    </button>
                                </div>
                            </Card>
                        ))}
                    </div>
                )}

                {/* Tab 2: Full Synchronized Script */}
                {activeTab === "script" && (
                    <Card className="p-6 bg-white border border-line">
                        <div className="flex items-center justify-between mb-4">
                            <div>
                                <h3 className="text-base font-semibold text-ink">Complete Studio Voiceover Script</h3>
                                <p className="text-xs text-stone-500">
                                    Copy and paste directly into ElevenLabs, OpenAI Audio, or your preferred TTS engine.
                                </p>
                            </div>
                            <Button
                                size="sm"
                                variant="primary"
                                onClick={() => copyText(fullScriptText, "complete voiceover script")}
                            >
                                <Copy className="w-3.5 h-3.5" />
                                Copy Complete Script
                            </Button>
                        </div>
                        <pre className="p-4 rounded-lg bg-stone-50 border border-line text-xs font-mono text-stone-700 whitespace-pre-wrap leading-relaxed max-h-[450px] overflow-y-auto">
                            {fullScriptText}
                        </pre>
                    </Card>
                )}

                {/* Tab 3: Recording & Voice Setup Instructions */}
                {activeTab === "production" && (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                        <Card className="p-5 bg-white border border-line">
                            <h3 className="text-sm font-semibold text-ink mb-1 flex items-center gap-2">
                                <SlidersHorizontal className="w-4 h-4 text-plum" />
                                AI Voice Generation Settings
                            </h3>
                            <p className="text-xs text-stone-500 mb-4">
                                Recommended parameters to get natural, human-paced narration without robotic artifacts:
                            </p>
                            <div className="space-y-3 text-xs">
                                <div className="p-2.5 rounded bg-stone-50 border border-line">
                                    <div className="font-semibold text-ink">Engine: ElevenLabs Multilingual v2</div>
                                    <div className="text-stone-500 mt-0.5">
                                        Voices: <strong>Charlie</strong> (calm, authoritative narrator) or{" "}
                                        <strong>Rachel</strong> (approachable, friendly presenter).
                                    </div>
                                </div>
                                <div className="grid grid-cols-3 gap-2">
                                    <div className="p-2 rounded bg-stone-50 border border-line text-center">
                                        <div className="text-[10px] text-stone-400 uppercase">Stability</div>
                                        <div className="font-semibold text-ink">0.50</div>
                                    </div>
                                    <div className="p-2 rounded bg-stone-50 border border-line text-center">
                                        <div className="text-[10px] text-stone-400 uppercase">Clarity</div>
                                        <div className="font-semibold text-ink">0.80</div>
                                    </div>
                                    <div className="p-2 rounded bg-stone-50 border border-line text-center">
                                        <div className="text-[10px] text-stone-400 uppercase">Style Exagg.</div>
                                        <div className="font-semibold text-ink">0.00</div>
                                    </div>
                                </div>
                                <div className="text-stone-500 leading-normal">
                                    Tip: Keep commas in the script text for natural breathing pauses, and use short sentences.
                                </div>
                            </div>
                        </Card>

                        <Card className="p-5 bg-white border border-line">
                            <h3 className="text-sm font-semibold text-ink mb-1 flex items-center gap-2">
                                <FileText className="w-4 h-4 text-plum" />
                                Saving the Video in Nimmi AI
                            </h3>
                            <p className="text-xs text-stone-500 mb-4">
                                How to make the video stream inside this Reference section:
                            </p>
                            <ol className="space-y-2 text-xs text-stone-600 list-decimal list-inside leading-relaxed">
                                <li>
                                    Record your screen walkthrough in 1080p (1920x1080) at 60fps using Screen Studio or OBS.
                                </li>
                                <li>Align the generated AI audio track in CapCut or Descript.</li>
                                <li>Export the final video as an MP4 file named <code>tutorial.mp4</code>.</li>
                                <li>
                                    Save the file directly to:
                                    <div className="mt-1 p-2 rounded bg-stone-100 font-mono text-[11px] text-stone-800 break-all select-all">
                                        dashboard/public/videos/tutorial.mp4
                                    </div>
                                </li>
                                <li>
                                    Refresh this page. The HTML5 video player will automatically detect and stream your HD video.
                                </li>
                            </ol>
                        </Card>
                    </div>
                )}
            </div>
        </main>
    );
}
