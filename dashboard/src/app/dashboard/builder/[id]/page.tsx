"use client";

import { useState, use, useEffect, useCallback, useRef, Suspense } from "react";
import {
    Bot, Palette, Database, Brain, GitBranch,
    ChevronLeft, Save, Upload, Plus, MessageSquare,
    Smartphone, Monitor, Send, Image as ImageIcon, Settings as SettingsIcon,
    Play, Check, Inbox, List, Search, ChevronDown, X, Globe, Video,
    Target, Square, Layers, AlignLeft, AlignRight, Anchor, Layout
} from "lucide-react";
import Link from "next/link";
import { motion, AnimatePresence } from "framer-motion";
import { useRouter, useSearchParams } from "next/navigation";
import { Node, Edge, useNodesState, useEdgesState, addEdge, Connection, MarkerType, NodeChange, EdgeChange } from "reactflow";
import dynamic from "next/dynamic";
import Image from "next/image";
import ElementsSidebar from "./components/ElementsSidebar";
import PropertiesPanel from "./components/PropertiesPanel";
import ExportModal from "./components/ExportModal";

// Dynamic import for FlowBuilder to avoid SSR issues
const FlowBuilder = dynamic(() => import("./components/FlowBuilder"), { ssr: false });

const GOOGLE_FONTS_BATCH_1 = "https://fonts.googleapis.com/css2?family=Inter:wght@400;700&family=Roboto:wght@400;700&family=Open+Sans:wght@400;700&family=Montserrat:wght@400;700&family=Poppins:wght@400;700&family=Lato:wght@400;700&family=Oswald:wght@400;700&family=Raleway:wght@400;700&family=Nunito:wght@400;700&family=Ubuntu:wght@400;700&family=Playfair+Display:wght@400;700&family=Lora:wght@400;700&family=Merriweather:wght@400;700&family=PT+Sans:wght@400;700&family=PT+Serif:wght@400;700&family=Noto+Sans:wght@400;700&family=Noto+Serif:wght@400;700&family=Work+Sans:wght@400;700&family=Fira+Sans:wght@400;700&family=Quicksand:wght@400;700&family=Josefin+Sans:wght@400;700&display=swap";
const GOOGLE_FONTS_BATCH_2 = "https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Space+Grotesk:wght@400;700&family=Caveat:wght@400;700&family=Lexend:wght@400;700&family=Kanit:wght@400;700&family=Outfit:wght@400;700&family=Syne:wght@400;700&family=Darker+Grotesque:wght@400;700&family=DM+Sans:wght@400;700&family=Manrope:wght@400;700&family=Sora:wght@400;700&family=Urbanist:wght@400;700&family=Figtree:wght@400;700&family=Archivo:wght@400;700&family=Schibsted+Grotesk:wght@400;700&family=Hanken+Grotesk:wght@400;700&family=Bricolage+Grotesque:wght@400;700&family=Young+Serif&family=Instrument+Serif&family=Playpen+Sans&family=Cabin:wght@400;700&display=swap";
const GOOGLE_FONTS_BATCH_3 = "https://fonts.googleapis.com/css2?family=Arvo:wght@400;700&family=Exo+2:wght@400;700&family=Muli:wght@400;700&family=Titillium+Web:wght@400;700&family=Dosis:wght@400;700&family=Oxygen:wght@400;700&family=Hind:wght@400;700&family=Libre+Baskerville:wght@400;700&family=Anton&family=Karla:wght@400;700&family=Bitter:wght@400;700&family=Varela+Round&family=Crimson+Text:wght@400;700&family=Barlow:wght@400;700&family=Asap:wght@400;700&family=Fjalla+One&family=Pacifico&family=Questrial&family=Assistant:wght@400;700&family=Signika:wght@400;700&display=swap";
const GOOGLE_FONTS_BATCH_4 = "https://fonts.googleapis.com/css2?family=Alegreya:wght@400;700&family=Alegreya+Sans:wght@400;700&family=Righteous&family=Patua+One&family=Comfortaa:wght@400;700&family=Lobster&family=Dancing+Script:wght@400;700&family=Kaushan+Script&family=Satisfy&family=Great+Vibes&family=Sacramento&family=Yellowtail&family=Cookie&family=Tangerine&family=Special+Elite&family=Luckiest+Guy&family=Bangers&family=Press+Start+2P&family=VT323&display=swap";
const GOOGLE_FONTS_BATCH_5 = "https://fonts.googleapis.com/css2?family=Nanum+Gothic:wght@400;700&family=Cairo:wght@400;700&family=Mukta:wght@400;700&family=Heebo:wght@400;700&family=Prompt:wght@400;700&family=Spectral:wght@400;700&family=Cardo:wght@400;700&family=Crimson+Pro:wght@400;700&family=Eczar:wght@400;700&family=Domine:wght@400;700&family=Old+Standard+TT:wght@400;700&family=Cormorant:wght@400;700&family=Prata&family=Marcellus&family=Josefin+Slab:wght@400;700&family=BioRhyme:wght@400;700&family=Chivo:wght@400;700&family=Overpass:wght@400;700&family=Public+Sans:wght@400;700&family=Fraunces:wght@400;700&family=Besley:wght@400;700&family=Casta&family=Delius&family=Neucha&display=swap";

const FONT_OPTIONS = [
    { label: "Sans Serif", value: "sans-serif" }, { label: "Serif", value: "serif" }, { label: "Monospace", value: "monospace" },
    { label: "Inter", value: "'Inter', sans-serif" }, { label: "Roboto", value: "'Roboto', sans-serif" }, { label: "Open Sans", value: "'Open Sans', sans-serif" },
    { label: "Montserrat", value: "'Montserrat', sans-serif" }, { label: "Poppins", value: "'Poppins', sans-serif" }, { label: "Lato", value: "'Lato', sans-serif" },
    { label: "Oswald", value: "'Oswald', sans-serif" }, { label: "Raleway", value: "'Raleway', sans-serif" }, { label: "Nunito", value: "'Nunito', sans-serif" },
    { label: "Ubuntu", value: "'Ubuntu', sans-serif" }, { label: "Playfair Display", value: "'Playfair Display', serif" }, { label: "Lora", value: "'Lora', serif" },
    { label: "Merriweather", value: "'Merriweather', serif" }, { label: "PT Sans", value: "'PT Sans', sans-serif" }, { label: "PT Serif", value: "'PT Serif', serif" },
    { label: "Noto Sans", value: "'Noto Sans', sans-serif" }, { label: "Noto Serif", value: "'Noto Serif', serif" }, { label: "Work Sans", value: "'Work Sans', sans-serif" },
    { label: "Fira Sans", value: "'Fira Sans', sans-serif" }, { label: "Quicksand", value: "'Quicksand', sans-serif" }, { label: "Josefin Sans", value: "'Josefin Sans', sans-serif" },
    { label: "Bebas Neue", value: "'Bebas Neue', cursive" }, { label: "Space Grotesk", value: "'Space Grotesk', sans-serif" }, { label: "Caveat", value: "'Caveat', cursive" },
    { label: "Lexend", value: "'Lexend', sans-serif" }, { label: "Kanit", value: "'Kanit', sans-serif" }, { label: "Outfit", value: "'Outfit', sans-serif" },
    { label: "Syne", value: "'Syne', sans-serif" }, { label: "Darker Grotesque", value: "'Darker Grotesque', sans-serif" }, { label: "DM Sans", value: "'DM Sans', sans-serif" },
    { label: "Manrope", value: "'Manrope', sans-serif" }, { label: "Sora", value: "'Sora', sans-serif" }, { label: "Urbanist", value: "'Urbanist', sans-serif" },
    { label: "Figtree", value: "'Figtree', sans-serif" }, { label: "Archivo", value: "'Archivo', sans-serif" }, { label: "Schibsted Grotesk", value: "'Schibsted Grotesk', sans-serif" },
    { label: "Hanken Grotesk", value: "'Hanken Grotesk', sans-serif" }, { label: "Bricolage Grotesque", value: "'Bricolage Grotesque', sans-serif" }, { label: "Young Serif", value: "'Young Serif', serif" },
    { label: "Instrument Serif", value: "'Instrument Serif', serif" }, { label: "Playpen Sans", value: "'Playpen Sans', cursive" }, { label: "Cabin", value: "'Cabin', sans-serif" },
    { label: "Arvo", value: "'Arvo', serif" }, { label: "Exo 2", value: "'Exo 2', sans-serif" }, { label: "Muli", value: "'Muli', sans-serif" },
    { label: "Titillium Web", value: "'Titillium Web', sans-serif" }, { label: "Dosis", value: "'Dosis', sans-serif" }, { label: "Oxygen", value: "'Oxygen', sans-serif" },
    { label: "Hind", value: "'Hind', sans-serif" }, { label: "Libre Baskerville", value: "'Libre Baskerville', serif" }, { label: "Anton", value: "'Anton', sans-serif" },
    { label: "Karla", value: "'Karla', sans-serif" }, { label: "Bitter", value: "'Bitter', serif" }, { label: "Varela Round", value: "'Varela Round', sans-serif" },
    { label: "Crimson Text", value: "'Crimson Text', serif" }, { label: "Barlow", value: "'Barlow', sans-serif" }, { label: "Asap", value: "'Asap', sans-serif" },
    { label: "Fjalla One", value: "'Fjalla One', sans-serif" }, { label: "Pacifico", value: "'Pacifico', cursive" }, { label: "Questrial", value: "'Questrial', sans-serif" },
    { label: "Assistant", value: "'Assistant', sans-serif" }, { label: "Signika", value: "'Signika', sans-serif" }, { label: "Alegreya", value: "'Alegreya', serif" },
    { label: "Alegreya Sans", value: "'Alegreya Sans', sans-serif" }, { label: "Righteous", value: "'Righteous', cursive" }, { label: "Patua One", value: "'Patua One', cursive" },
    { label: "Comfortaa", value: "'Comfortaa', cursive" }, { label: "Lobster", value: "'Lobster', cursive" }, { label: "Dancing Script", value: "'Dancing Script', cursive" },
    { label: "Kaushan Script", value: "'Kaushan Script', cursive" }, { label: "Satisfy", value: "'Satisfy', cursive" }, { label: "Great Vibes", value: "'Great Vibes', cursive" },
    { label: "Sacramento", value: "'Sacramento', cursive" }, { label: "Yellowtail", value: "'Yellowtail', cursive" }, { label: "Cookie", value: "'Cookie', cursive" },
    { label: "Tangerine", value: "'Tangerine', cursive" }, { label: "Special Elite", value: "'Special Elite', cursive" }, { label: "Luckiest Guy", value: "'Luckiest Guy', cursive" },
    { label: "Bangers", value: "'Bangers', cursive" }, { label: "Press Start 2P", value: "'Press Start 2P', cursive" }, { label: "VT323", value: "'VT323', monospace" },
    { label: "Nanum Gothic", value: "'Nanum Gothic', sans-serif" }, { label: "Cairo", value: "'Cairo', sans-serif" }, { label: "Mukta", value: "'Mukta', sans-serif" },
    { label: "Heebo", value: "'Heebo', sans-serif" }, { label: "Prompt", value: "'Prompt', sans-serif" }, { label: "Spectral", value: "'Spectral', serif" },
    { label: "Cardo", value: "'Cardo', serif" }, { label: "Crimson Pro", value: "'Crimson Pro', serif" }, { label: "Eczar", value: "'Eczar', serif" },
    { label: "Domine", value: "'Domine', serif" }, { label: "Old Standard TT", value: "'Old Standard TT', serif" }, { label: "Cormorant", value: "'Cormorant', serif" },
    { label: "Prata", value: "'Prata', serif" }, { label: "Marcellus", value: "'Marcellus', serif" }, { label: "Josefin Slab", value: "'Josefin Slab', serif" },
    { label: "BioRhyme", value: "'BioRhyme', serif" }, { label: "Chivo", value: "'Chivo', sans-serif" }, { label: "Overpass", value: "'Overpass', sans-serif" },
    { label: "Public Sans", value: "'Public Sans', sans-serif" }, { label: "Fraunces", value: "'Fraunces', serif" }, { label: "Besley", value: "'Besley', serif" },
    { label: "Casta", value: "'Casta', serif" }, { label: "Delius", value: "'Delius', cursive" }, { label: "Neucha", value: "'Neucha', cursive" }
];

function ChatbotWidgetContent({
    botName, botLogo, color, textColor, headerHeight, chatBgColor,
    backgroundImage, backgroundOpacity, assistantBubbleBg, assistantBubbleText,
    userBubbleBg, userBubbleText, borderRadius, inputBgColor, inputTextColor
}: any) {
    return (
        <>
            <div
                className="p-6 font-bold flex items-center justify-between shrink-0 shadow-lg relative z-10"
                style={{ backgroundColor: color, color: textColor, height: `${headerHeight}px` }}
            >
                <div className="flex items-center gap-3">
                    <div className="w-10 h-10 bg-white/20 rounded-xl flex items-center justify-center overflow-hidden backdrop-blur-md border border-white/10">
                        {botLogo ? (
                            <img src={botLogo} alt="Bot" className="w-full h-full object-cover" />
                        ) : (
                            <Bot size={20} />
                        )}
                    </div>
                    <span className="drop-shadow-sm">{botName}</span>
                </div>
            </div>
            <div className="flex-1 relative overflow-hidden" style={{ backgroundColor: chatBgColor }}>
                {backgroundImage && (
                    <div
                        className="absolute inset-0 z-0 pointer-events-none"
                        style={{
                            backgroundImage: `url(${backgroundImage})`,
                            backgroundSize: 'cover',
                            backgroundPosition: 'center',
                            opacity: backgroundOpacity
                        }}
                    />
                )}
                <div className="absolute inset-0 overflow-y-auto p-6 z-10">
                    <div className="space-y-4 flex flex-col">
                        <div
                            className="p-4 rounded-tl-none text-xs leading-relaxed max-w-[85%] shadow-sm border border-slate-100"
                            style={{ backgroundColor: assistantBubbleBg, color: assistantBubbleText, borderRadius: `${borderRadius}px` }}
                        >
                            Hello! I'm trained on your company data. How can I help you today?
                        </div>
                        <div
                            className="p-4 rounded-tr-none text-xs leading-relaxed max-w-[80%] self-end shadow-md transition-transform hover:scale-[1.02]"
                            style={{ backgroundColor: userBubbleBg, color: userBubbleText, borderRadius: `${borderRadius}px` }}
                        >
                            What's the return policy?
                        </div>
                    </div>
                </div>
            </div>
            <div className="p-4 bg-zinc-900/80 border-t border-white/5 flex gap-2 backdrop-blur-md">
                <div
                    className="flex-1 rounded-xl border border-white/5 h-12 flex items-center px-4 text-sm shadow-inner"
                    style={{ backgroundColor: inputBgColor, color: inputTextColor }}
                >
                    Type your message...
                </div>
                <button
                    className="w-12 h-12 rounded-xl flex items-center justify-center shadow-lg active:scale-95 transition-all"
                    style={{ backgroundColor: color, color: textColor }}
                >
                    <Send size={18} />
                </button>
            </div>
        </>
    );
}

function LauncherPreview({ color, showLauncherBg, launcherShape, botLogo, logoSize, showTail }: any) {
    return (
        <div
            className="w-16 h-16 shadow-[0_20px_50px_rgba(0,0,0,0.2)] flex items-center justify-center transition-all duration-500 relative ring-1 ring-white/10 group-hover:scale-110"
            style={{
                backgroundColor: (showLauncherBg && launcherShape !== 'none') ? color : 'transparent',
                borderRadius: launcherShape === 'square' ? '0' :
                    launcherShape === 'rounded' ? '12px' :
                        launcherShape === 'oval' ? '40px' : '50%',
                width: launcherShape === 'oval' ? '80px' : '64px',
            }}
        >
            {botLogo ? (
                <img src={botLogo} alt="Launcher" style={{ width: `${logoSize}px`, height: `${logoSize}px`, objectFit: 'contain' }} />
            ) : (
                <MessageSquare size={30} className="text-white drop-shadow-md" />
            )}
            {showTail && (
                <div
                    className="absolute -bottom-2 rotate-[-15deg] drop-shadow-sm"
                    style={{
                        width: 0, height: 0,
                        borderLeft: '10px solid transparent',
                        borderRight: '10px solid transparent',
                        borderTop: `12px solid ${showLauncherBg ? color : 'transparent'}`,
                        right: launcherShape === 'oval' ? '20px' : '10px'
                    }}
                />
            )}
        </div>
    );
}

function BuilderContent({ params }: { params: Promise<{ id: string }> }) {
    const { id } = use(params);
    const [activeTab, setActiveTab] = useState("design");
    const [color, setColor] = useState("#3b82f6");
    const [botName, setBotName] = useState("Nimmi Assistant");
    const [botLogo, setBotLogo] = useState("");
    const [position, setPosition] = useState("right");
    const [fontFamily, setFontFamily] = useState("sans-serif");
    const [textColor, setTextColor] = useState("#ffffff");
    const [inputBgColor, setInputBgColor] = useState("#ffffff");
    const [inputTextColor, setInputTextColor] = useState("#000000");
    const [userBubbleBg, setUserBubbleBg] = useState("#3b82f6");
    const [userBubbleText, setUserBubbleText] = useState("#ffffff");
    const [assistantBubbleBg, setAssistantBubbleBg] = useState("#e5e7eb");
    const [assistantBubbleText, setAssistantBubbleText] = useState("#000000");
    const [chatBgColor, setChatBgColor] = useState("#f9fafb");
    const [headerHeight, setHeaderHeight] = useState(80);
    const [borderRadius, setBorderRadius] = useState(24);
    const [launcherShape, setLauncherShape] = useState("circle");
    const [showTail, setShowTail] = useState(true);
    const [showLauncherBg, setShowLauncherBg] = useState(true);
    const [logoSize, setLogoSize] = useState(32);
    const [rightPadding, setRightPadding] = useState(20);
    const [bottomPadding, setBottomPadding] = useState(20);
    const [fontSearch, setFontSearch] = useState("");
    const [backgroundImage, setBackgroundImage] = useState("");
    const [backgroundOpacity, setBackgroundOpacity] = useState(1);
    const [showFontDropdown, setShowFontDropdown] = useState(false);
    const fontDropdownRef = useRef<HTMLDivElement>(null);
    const [knowledgeBase, setKnowledgeBase] = useState("");
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [saved, setSaved] = useState(false);
    const [logoLoading, setLogoLoading] = useState(false);
    const [systemPrompt, setSystemPrompt] = useState("");
    const [aiProvider, setAiProvider] = useState("google");
    const [aiModel, setAiModel] = useState("gemini-3-flash-preview");
    const [aiApiKey, setAiApiKey] = useState("");
    const fileInputRef = useRef<HTMLInputElement>(null);
    const backgroundInputRef = useRef<HTMLInputElement>(null);
    const knowledgeInputRef = useRef<HTMLInputElement>(null);
    const [knowledgeLoading, setKnowledgeLoading] = useState(false);
    const [backgroundLoading, setBackgroundLoading] = useState(false);
    const [crawlUrl, setCrawlUrl] = useState("");
    const [youtubeUrl, setYoutubeUrl] = useState("");
    const [liveSearchEnabled, setLiveSearchEnabled] = useState(false);
    const [crawling, setCrawling] = useState(false);
    const [previewMode, setPreviewMode] = useState<'desktop' | 'mobile'>('mobile');
    const router = useRouter();
    const previewContainerRef = useRef<HTMLDivElement>(null);
    const [previewScale, setPreviewScale] = useState(1);

    // Dynamically calculate scale for desktop preview
    useEffect(() => {
        if (previewMode !== 'desktop' || !previewContainerRef.current) return;
        const container = previewContainerRef.current;
        const calculateScale = () => {
            const availableWidth = container.clientWidth - 32;
            const availableHeight = container.clientHeight - 120;
            const scaleX = Math.min(availableWidth / 900, 1);
            const scaleY = Math.min(availableHeight / 562, 1);
            setPreviewScale(Math.min(scaleX, scaleY, 1));
        };
        calculateScale();
        const observer = new ResizeObserver(calculateScale);
        observer.observe(container);
        return () => observer.disconnect();
    }, [previewMode]);

    // Flow state
    const [flowNodes, setFlowNodes, onNodesChange] = useNodesState<any>([]);
    const [flowEdges, setFlowEdges, onEdgesChange] = useEdgesState<any>([]);
    const [selectedNode, setSelectedNode] = useState<Node | null>(null);
    const [showExport, setShowExport] = useState(false);
    const lastSavedState = useRef<string>("");
    const [leads, setLeads] = useState<any[]>([]);
    const [leadsLoading, setLeadsLoading] = useState(false);

    const fetchLeads = async () => {
        setLeadsLoading(true);
        try {
            const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/bots/${id}/leads`);
            const data = await res.json();
            if (res.ok) {
                setLeads(data);
            }
        } catch (err) {
            console.error("Failed to fetch leads:", err);
        } finally {
            setLeadsLoading(false);
        }
    };

    const searchParams = useSearchParams();

    useEffect(() => {
        if (searchParams.get("payment") === "success") {
            setShowExport(true);
            // Optional: Remove query param from URL without refreshing
            router.replace(`/dashboard/builder/${id}`);
        }
    }, [searchParams, id, router]);

    useEffect(() => {
        if (activeTab === "storage") {
            fetchLeads();
        }
    }, [activeTab, id]);

    useEffect(() => {
        const handleClickOutside = (event: MouseEvent) => {
            if (fontDropdownRef.current && !fontDropdownRef.current.contains(event.target as any)) {
                setShowFontDropdown(false);
            }
        };
        document.addEventListener("mousedown", handleClickOutside);
        return () => document.removeEventListener("mousedown", handleClickOutside);
    }, []);

    const fetchConfig = useCallback(async () => {
        try {
            const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/bots/${id}/config`);
            const data = await res.json();
            if (res.ok) {
                setBotName(data.bot_name || "Nimmi Assistant");
                if (data.visual_config) {
                    setColor(data.visual_config.color || "#3b82f6");
                    setBotLogo(data.visual_config.logo_url || "");
                    setPosition(data.visual_config.position || "right");
                    setFontFamily(data.visual_config.font_family || "sans-serif");
                    setTextColor(data.visual_config.text_color || "#ffffff");
                    setInputBgColor(data.visual_config.input_bg_color || "#ffffff");
                    setInputTextColor(data.visual_config.input_text_color || "#000000");
                    setUserBubbleBg(data.visual_config.user_bubble_bg || data.visual_config.color || "#3b82f6");
                    setUserBubbleText(data.visual_config.user_bubble_text || data.visual_config.text_color || "#ffffff");
                    setAssistantBubbleBg(data.visual_config.assistant_bubble_bg || "#e5e7eb");
                    setAssistantBubbleText(data.visual_config.assistant_bubble_text || "#000000");
                    setChatBgColor(data.visual_config.chat_bg_color || "#f9fafb");
                    setHeaderHeight(data.visual_config.header_height || 80);
                    setBorderRadius(data.visual_config.border_radius || 24);
                    setLauncherShape(data.visual_config.launcher_shape || "circle");
                    setShowTail(data.visual_config.show_tail !== false);
                    setShowLauncherBg(data.visual_config.show_launcher_bg !== false);
                    setLogoSize(data.visual_config.logo_size || 32);
                    setRightPadding(data.visual_config.right_padding || 20);
                    setBottomPadding(data.visual_config.bottom_padding || 20);
                    setBackgroundImage(data.visual_config.background_image || "");
                    setBackgroundOpacity(data.visual_config.background_opacity ?? 1);
                }
                setSystemPrompt(data.system_prompt || "");
                setKnowledgeBase(data.knowledge_base || "");
                setAiProvider(data.ai_provider || "google");
                setAiModel(data.ai_model || "gemini-3-flash-preview");
                setAiApiKey(data.ai_api_key || "");
                if (data.flow_data && data.flow_data.nodes && data.flow_data.nodes.length > 0) {
                    setFlowNodes(data.flow_data.nodes);
                    setFlowEdges(data.flow_data.edges || []);
                } else {
                    setFlowNodes([{
                        id: "start-1",
                        type: "start",
                        position: { x: 250, y: 50 },
                        data: { label: "Start" },
                    }]);
                    setFlowEdges([]);
                }

                lastSavedState.current = JSON.stringify({
                    botName: data.bot_name || "Nimmi Assistant",
                    systemPrompt: data.system_prompt || "",
                    knowledgeBase: data.knowledge_base || "",
                    color: data.visual_config?.color || "#3b82f6",
                    botLogo: data.visual_config?.logo_url || "",
                    position: data.visual_config?.position || "right",
                    fontFamily: data.visual_config?.font_family || "sans-serif",
                    textColor: data.visual_config?.text_color || "#ffffff",
                    inputBgColor: data.visual_config?.input_bg_color || "#ffffff",
                    inputTextColor: data.visual_config?.input_text_color || "#000000",
                    userBubbleBg: data.visual_config?.user_bubble_bg || data.visual_config?.color || "#3b82f6",
                    userBubbleText: data.visual_config?.user_bubble_text || data.visual_config?.text_color || "#ffffff",
                    assistantBubbleBg: data.visual_config?.assistant_bubble_bg || "#e5e7eb",
                    assistantBubbleText: data.visual_config?.assistant_bubble_text || "#000000",
                    chatBgColor: data.visual_config?.chat_bg_color || "#f9fafb",
                    headerHeight: data.visual_config?.header_height || 80,
                    borderRadius: data.visual_config?.border_radius || 24,
                    launcherShape: data.visual_config?.launcher_shape || "circle",
                    showTail: data.visual_config?.show_tail !== false,
                    showLauncherBg: data.visual_config?.show_launcher_bg !== false,
                    logoSize: data.visual_config?.logo_size || 32,
                    rightPadding: data.visual_config?.right_padding || 20,
                    bottomPadding: data.visual_config?.bottom_padding || 20,
                    backgroundImage: data.visual_config?.background_image || "",
                    backgroundOpacity: data.visual_config?.background_opacity ?? 1,
                    nodes: data.flow_data?.nodes || [],
                    edges: data.flow_data?.edges || [],
                    aiProvider: data.ai_provider || "google",
                    aiModel: data.ai_model || "gemini-3-flash-preview",
                    aiApiKey: data.ai_api_key || ""
                });
            }
        } catch (err) {
            console.error("Failed to fetch bot config:", err);
        } finally {
            setLoading(false);
        }
    }, [id]);

    useEffect(() => {
        fetchConfig();
    }, [id, fetchConfig]);

    const onConnect = useCallback(
        (params: Connection) => {
            setFlowEdges((eds) =>
                addEdge(
                    {
                        ...params,
                        type: "animated",
                        style: { stroke: "#3b82f6", strokeWidth: 2 },
                        markerEnd: {
                            type: MarkerType.ArrowClosed,
                            color: "#3b82f6",
                        },
                    },
                    eds
                )
            );
        },
        [setFlowEdges]
    );

    const handleSave = useCallback(async (updatedNodes?: Node[], updatedEdges?: Edge[], overrideLogo?: string) => {
        try {
            const currentState = JSON.stringify({
                botName, systemPrompt, knowledgeBase, color, botLogo, position, fontFamily, textColor, inputBgColor, inputTextColor, userBubbleBg, userBubbleText, assistantBubbleBg, assistantBubbleText, chatBgColor, headerHeight, borderRadius, launcherShape, showTail, showLauncherBg, logoSize, rightPadding, bottomPadding, backgroundImage, backgroundOpacity,
                nodes: updatedNodes || flowNodes,
                edges: updatedEdges || flowEdges,
                aiProvider, aiModel, aiApiKey
            });

            if (currentState === lastSavedState.current) {
                return;
            }

            setSaving(true);
            const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/bots/${id}`, {
                method: "PATCH",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    bot_name: botName,
                    system_prompt: systemPrompt,
                    knowledge_base: knowledgeBase,
                    ai_provider: aiProvider,
                    ai_model: aiModel,
                    ai_api_key: aiApiKey,
                    visual_config: {
                        color,
                        logo_url: overrideLogo || botLogo,
                        position,
                        font_family: fontFamily,
                        text_color: textColor,
                        input_bg_color: inputBgColor,
                        input_text_color: inputTextColor,
                        user_bubble_bg: userBubbleBg,
                        user_bubble_text: userBubbleText,
                        assistant_bubble_bg: assistantBubbleBg,
                        assistant_bubble_text: assistantBubbleText,
                        chat_bg_color: chatBgColor,
                        header_height: headerHeight,
                        border_radius: borderRadius,
                        launcher_shape: launcherShape,
                        show_tail: showTail,
                        show_launcher_bg: showLauncherBg,
                        logo_size: logoSize,
                        right_padding: rightPadding,
                        bottom_padding: bottomPadding,
                        background_image: backgroundImage,
                        background_opacity: backgroundOpacity
                    },
                    flow_data: {
                        nodes: updatedNodes || flowNodes,
                        edges: updatedEdges || flowEdges
                    }
                })
            });
            if (res.ok) {
                lastSavedState.current = currentState;
                setSaved(true);
                setTimeout(() => setSaved(false), 2000);
            }
        } catch (err) {
            console.error("Failed to save bot:", err);
        } finally {
            setSaving(false);
        }
    }, [id, botName, systemPrompt, knowledgeBase, aiProvider, aiModel, aiApiKey, color, botLogo, position, fontFamily, textColor, inputBgColor, inputTextColor, userBubbleBg, userBubbleText, assistantBubbleBg, assistantBubbleText, chatBgColor, headerHeight, borderRadius, launcherShape, showTail, showLauncherBg, logoSize, rightPadding, bottomPadding, backgroundImage, backgroundOpacity, flowNodes, flowEdges]);

    useEffect(() => {
        if (!loading) {
            const timer = setTimeout(() => {
                handleSave();
            }, 1000);
            return () => clearTimeout(timer);
        }
    }, [handleSave, loading]);

    const handleFlowSave = useCallback((nodes: Node[], edges: Edge[]) => {
        setFlowNodes(nodes);
        setFlowEdges(edges);
        // useEffect will catch this change and handle it debounced
    }, []);

    const handleKnowledgeUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;

        setKnowledgeLoading(true);
        const formData = new FormData();
        formData.append("file", file);

        try {
            const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/bots/${id}/knowledge/upload`, {
                method: "POST",
                body: formData,
            });
            const data = await res.json();
            if (res.ok && data.knowledge_base) {
                setKnowledgeBase(data.knowledge_base);
                // useEffect will catch this and handle it debounced
            }
        } catch (err) {
            console.error("Failed to upload knowledge:", err);
        } finally {
            setKnowledgeLoading(false);
            if (knowledgeInputRef.current) knowledgeInputRef.current.value = "";
        }
    };

    const handleCrawl = async () => {
        if (!crawlUrl) return;
        setCrawling(true);
        try {
            const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/knowledge/crawl`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ bot_id: id, url: crawlUrl })
            });
            const data = await response.json();
            if (response.ok && data.status === "success") {
                fetchConfig();
                alert("Website crawled successfully!");
                setCrawlUrl("");
            } else {
                alert(data.error || "Failed to crawl website");
            }
        } catch (error) {
            console.error("Crawl error:", error);
        } finally {
            setCrawling(false);
        }
    };

    const handleYouTubeExtract = async () => {
        if (!youtubeUrl) return;
        setCrawling(true);
        try {
            const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/knowledge/youtube`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ bot_id: id, url: youtubeUrl })
            });
            const data = await response.json();
            if (response.ok && data.status === "success") {
                fetchConfig();
                alert("YouTube transcript extracted successfully!");
                setYoutubeUrl("");
            } else {
                alert(data.error || "Failed to extract transcript");
            }
        } catch (error) {
            console.error("YouTube error:", error);
        } finally {
            setCrawling(false);
        }
    };
    const handleLogoUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;

        setLogoLoading(true);
        const formData = new FormData();
        formData.append("file", file);

        try {
            const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/bots/${id}/logo`, {
                method: "POST",
                body: formData,
            });
            const data = await res.json();
            if (res.ok && data.logo_url) {
                setBotLogo(data.logo_url);
                // useEffect will catch this and handle it debounced
            }
        } catch (err) {
            console.error("Failed to upload logo:", err);
        } finally {
            setLogoLoading(false);
        }
    };

    const handleBackgroundUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;

        setBackgroundLoading(true);
        const formData = new FormData();
        formData.append("file", file);

        try {
            const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/bots/${id}/background`, {
                method: "POST",
                body: formData,
            });
            const data = await res.json();
            if (res.ok && data.bg_url) {
                setBackgroundImage(data.bg_url);
            }
        } catch (err) {
            console.error("Failed to upload background:", err);
        } finally {
            setBackgroundLoading(false);
        }
    };

    const handleNodeSelect = useCallback((node: Node | null) => {
        setSelectedNode(node);
    }, []);

    const handleNodeUpdate = useCallback((nodeId: string, data: any) => {
        setFlowNodes((nodes) =>
            nodes.map((n) => (n.id === nodeId ? { ...n, data: { ...n.data, ...data } } : n))
        );
    }, [setFlowNodes]);

    const handleNodeDelete = useCallback((nodeId: string) => {
        setFlowNodes((nodes) => nodes.filter((n) => n.id !== nodeId));
        setFlowEdges((edges) =>
            edges.filter((e) => e.source !== nodeId && e.target !== nodeId)
        );
        setSelectedNode(null);
    }, [setFlowNodes, setFlowEdges]);

    const tabs = [
        { id: "design", label: "Design", icon: Palette },
        { id: "knowledge", label: "Knowledge", icon: Database },
        { id: "personality", label: "Personality", icon: Brain },
        { id: "flow", label: "Flow", icon: GitBranch },
        { id: "storage", label: "Storage", icon: Inbox },
    ];

    // Flow tab has a different layout
    if (activeTab === "flow") {
        return (
            <div className="flex h-screen bg-[#fcfcfd] text-slate-900">
                {/* Left Sidebar - Elements */}
                <aside className="w-72 border-r border-slate-200 flex flex-col bg-white">
                    <header className="p-4 border-b border-slate-100 flex items-center justify-between">
                        <Link href="/dashboard" className="p-2 hover:bg-slate-50 rounded-lg transition-colors text-slate-400 hover:text-slate-900">
                            <ChevronLeft size={20} />
                        </Link>
                        <span className="text-xs font-bold text-slate-400 uppercase tracking-widest">Flow Builder</span>
                        <div className="flex items-center gap-2">
                            <Link
                                href={`/demo/${id}`}
                                target="_blank"
                                className="flex items-center gap-1 px-3 py-1.5 bg-slate-50 border border-slate-200 rounded-lg text-xs font-bold hover:bg-slate-100 transition-colors text-slate-600"
                            >
                                <Play size={12} fill="currentColor" /> Run
                            </Link>
                            <button
                                onClick={() => handleSave()}
                                disabled={saving}
                                className={`flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${saved ? "bg-green-600" : "bg-[#9d55ac] hover:bg-[#b06abf]"} disabled:opacity-50`}
                            >
                                {saved ? <Check size={12} /> : <Save size={12} />}
                                {saving ? "..." : saved ? "Saved!" : "Save"}
                            </button>
                        </div>
                    </header>

                    {/* Tab Switcher */}
                    <div className="flex p-2 gap-1 bg-slate-50 mx-4 mt-4 rounded-xl border border-slate-100">
                        {tabs.map(tab => (
                            <button
                                key={tab.id}
                                onClick={() => setActiveTab(tab.id)}
                                className={`flex-1 flex flex-col items-center gap-1 py-2 rounded-lg text-[10px] font-bold transition-all ${activeTab === tab.id ? "bg-white text-[#9d55ac] shadow-sm" : "text-slate-400 hover:text-slate-600"}`}
                            >
                                <tab.icon size={14} />
                                {tab.label}
                            </button>
                        ))}
                    </div>

                    {/* Elements Sidebar */}
                    <div className="flex-1 overflow-y-auto p-4">
                        <ElementsSidebar />
                    </div>
                </aside>

                {/* Main Canvas Area */}
                <main className="flex-1 flex flex-col">
                    <div className="flex-1 p-4">
                        <FlowBuilder
                            botId={id}
                            nodes={flowNodes}
                            edges={flowEdges}
                            onNodesChange={onNodesChange}
                            onEdgesChange={onEdgesChange}
                            onConnect={onConnect}
                            onSave={handleFlowSave}
                            onNodeSelect={handleNodeSelect}
                        />
                    </div>
                </main>

                {/* Right Sidebar - Properties */}
                <aside className="w-80 border-l border-slate-200 p-4 overflow-y-auto bg-slate-50/20 backdrop-blur-sm">
                    <h3 className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-6 px-1">
                        {selectedNode ? "Element Properties" : "Select an Element"}
                    </h3>
                    {selectedNode ? (
                        <PropertiesPanel
                            node={selectedNode}
                            onUpdate={handleNodeUpdate}
                            onDelete={handleNodeDelete}
                            onClose={() => setSelectedNode(null)}
                        />
                    ) : (
                        <div className="text-center py-16 px-6 border-2 border-dashed border-slate-200 rounded-[32px] bg-slate-50/50">
                            <motion.div
                                animate={{ y: [0, -4, 0] }}
                                transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}
                            >
                                <GitBranch size={40} className="mx-auto mb-4 text-slate-200" strokeWidth={2.5} />
                            </motion.div>
                            <p className="text-[11px] font-bold text-slate-400 leading-relaxed uppercase tracking-tighter">
                                Click on an element in the canvas to edit its properties
                            </p>
                        </div>
                    )}
                </aside>
            </div>
        );
    }

    // Default layout for other tabs
    return (
        <div className="flex flex-col lg:flex-row h-screen bg-[#fcfcfd] text-slate-900">
            {/* Load only the selected font to save bandwidth */}
            {fontFamily !== "sans-serif" && fontFamily !== "serif" && fontFamily !== "monospace" && (
                <link
                    rel="stylesheet"
                    href={`https://fonts.googleapis.com/css2?family=${fontFamily.replace(/'/g, "").split(",")[0].replace(/ /g, "+")}:wght@400;700&display=swap`}
                />
            )}
            {/* Sidebar / Left Config */}
            <aside className="w-full lg:w-[520px] lg:h-screen h-[45vh] border-b lg:border-b-0 lg:border-r border-slate-200 flex flex-col shrink-0 overflow-hidden bg-white">
                <header className="px-4 py-4 border-b border-slate-100 flex items-center justify-between gap-3 bg-white">
                    <Link href="/dashboard" className="p-1.5 hover:bg-slate-50 rounded-lg transition-colors shrink-0 text-slate-400 hover:text-slate-900">
                        <ChevronLeft size={20} />
                    </Link>
                    <div className="flex items-center gap-3">
                        <Image src="/nimmi-logo-new.png" alt="Nimmi AI" width={120} height={120} className="rounded-lg" />
                        <div className="flex items-center gap-1.5 font-bold uppercase text-[10px] tracking-widest text-slate-400 truncate">
                            Bot Builder <span className="text-[#9d55ac] font-black">#{id.slice(0, 8)}</span>
                        </div>
                    </div>
                    <div className="flex items-center gap-1.5 shrink-0">
                        <Link
                            href={`/demo/${id}`}
                            target="_blank"
                            className="flex items-center gap-1.5 px-2.5 py-2 bg-slate-50 border border-slate-200 rounded-lg text-xs font-bold hover:bg-slate-100 transition-colors text-slate-600"
                        >
                            <Play size={14} fill="currentColor" /> Run
                        </Link>
                        <button
                            onClick={() => handleSave()}
                            disabled={saving}
                            className={`flex items-center gap-1.5 px-2.5 py-2 rounded-lg text-xs font-bold transition-all shadow-sm ${saved ? "bg-green-600 shadow-[0_0_20px_rgba(22,163,74,0.2)] text-white" : "bg-[#9d55ac] hover:bg-[#8a4a97] text-white"} disabled:opacity-50`}
                        >
                            {saved ? <Check size={14} /> : <Save size={14} />}
                            {saving ? "..." : saved ? "Done!" : "Save"}
                        </button>
                        <button
                            onClick={() => setShowExport(true)}
                            className="flex items-center gap-1.5 px-2.5 py-2 bg-white border border-slate-200 rounded-lg text-xs font-bold hover:bg-slate-50 transition-colors text-slate-600 shadow-sm"
                        >
                            <Upload size={14} /> Export
                        </button>
                    </div>
                </header>

                {/* Tab Switcher */}
                <div className="flex p-1.5 gap-1 bg-slate-50 mx-4 lg:mx-6 mt-4 lg:mt-6 rounded-2xl overflow-x-auto no-scrollbar border border-slate-200 shadow-inner">
                    {tabs.map(tab => (
                        <button
                            key={tab.id}
                            onClick={() => setActiveTab(tab.id)}
                            className={`flex-1 flex flex-col items-center gap-2 py-4 rounded-xl text-[11px] font-black uppercase tracking-widest transition-all ${activeTab === tab.id
                                ? "bg-white text-[#9d55ac] shadow-[0_4px_12px_rgba(0,0,0,0.05)] border border-slate-200"
                                : "text-slate-400 hover:text-slate-600 hover:bg-slate-100/50"
                                }`}
                        >
                            <tab.icon size={22} strokeWidth={2.5} />
                            {tab.label}
                        </button>
                    ))}
                </div>

                {/* Tab Content */}
                <div className="flex-1 overflow-y-auto p-4 lg:p-8">
                    <AnimatePresence mode="wait">
                        {activeTab === "design" && (
                            <motion.div
                                key="design"
                                initial={{ opacity: 0, x: -10 }}
                                animate={{ opacity: 1, x: 0 }}
                                exit={{ opacity: 0, x: 10 }}
                                className="space-y-4"
                            >
                                {/* Identity & Branding Section */}
                                <div className="p-6 bg-slate-50 rounded-[32px] shadow-[10px_10px_30px_#d1d9e6,-10px_-10px_30px_#ffffff] border border-white/50 relative group">
                                    <div className="absolute top-0 left-0 w-1.5 h-full bg-[#b06abf]/50 opacity-0 group-hover:opacity-100 transition-opacity rounded-l-[32px]" />
                                    <div className="flex items-center gap-4 mb-6">
                                        <div className="w-12 h-12 bg-[#9d55ac] rounded-[20px] flex items-center justify-center shadow-[inset_4px_4px_8px_rgba(255,255,255,0.3),inset_-4px_-4px_8px_rgba(0,0,0,0.1),8px_8px_20px_rgba(157,85,172,0.25)] text-white">
                                            <Target size={24} strokeWidth={2.5} />
                                        </div>
                                        <div>
                                            <h3 className="text-base font-black text-slate-900 uppercase tracking-widest">Identity</h3>
                                            <p className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em] mt-1 opacity-80">Brand personality settings</p>
                                        </div>
                                    </div>

                                    <div className="grid grid-cols-1 gap-6">
                                        <div className="space-y-3">
                                            <label className="flex items-center gap-2 text-[10px] font-black text-slate-500 uppercase tracking-[0.2em] pl-1">
                                                <div className="w-1.5 h-1.5 bg-[#b06abf] rounded-full" />
                                                Bot Name
                                            </label>
                                            <input
                                                type="text"
                                                value={botName}
                                                onChange={(e) => setBotName(e.target.value)}
                                                placeholder="Enter bot name..."
                                                className="w-full bg-slate-50 border-2 border-white/80 rounded-[20px] px-5 py-4 text-sm font-black outline-none focus:ring-4 focus:ring-[#b06abf]/5 focus:border-[#b06abf]/30 transition-all text-slate-900 placeholder:text-slate-300 shadow-[inset_4px_4px_8px_#d1d9e6,inset_-4px_-4px_8px_#ffffff]"
                                            />
                                        </div>

                                        <div className="space-y-3">
                                            <label className="flex items-center gap-2 text-[10px] font-black text-slate-500 uppercase tracking-[0.2em] pl-1">
                                                <div className="w-1.5 h-1.5 bg-[#b06abf] rounded-full" />
                                                Bot Logo
                                            </label>
                                            <div className="flex gap-4">
                                                <div className="flex-1 relative">
                                                    <input
                                                        type="text"
                                                        placeholder="Paste URL or upload image..."
                                                        value={botLogo}
                                                        onChange={(e) => setBotLogo(e.target.value)}
                                                        className="w-full bg-slate-50 border-2 border-white/80 rounded-[20px] px-5 py-4 text-sm font-black outline-none focus:ring-4 focus:ring-[#b06abf]/5 focus:border-[#b06abf]/30 transition-all text-slate-900 pr-12 placeholder:text-slate-300 shadow-[inset_4px_4px_8px_#d1d9e6,inset_-4px_-4px_8px_#ffffff]"
                                                    />
                                                    <button
                                                        onClick={() => fileInputRef.current?.click()}
                                                        disabled={logoLoading}
                                                        className="absolute right-2 top-1/2 -translate-y-1/2 p-2 bg-white text-slate-400 rounded-xl hover:bg-[#9d55ac] hover:text-white transition-all disabled:opacity-50 shadow-[2px_2px_4px_#d1d9e6,-2px_-2px_4px_#ffffff] border border-white"
                                                    >
                                                        <Upload size={18} strokeWidth={2.5} />
                                                    </button>
                                                    <input type="file" ref={fileInputRef} onChange={handleLogoUpload} className="hidden" accept="image/*" />
                                                </div>
                                                {botLogo && (
                                                    <div className="w-12 h-12 bg-white rounded-[16px] shadow-[4px_4px_10px_#d1d9e6,-4px_-4px_10px_#ffffff] border-4 border-white flex items-center justify-center p-2 shrink-0">
                                                        <img src={botLogo} alt="Logo" className="object-contain max-w-full max-h-full" />
                                                    </div>
                                                )}
                                            </div>
                                        </div>
                                    </div>
                                </div>

                                {/* Appearance Vertical Grid */}
                                <div className="flex flex-col gap-6">
                                    {/* Visual Theme Card */}
                                    <div className="p-6 bg-slate-50 rounded-[32px] shadow-[10px_10px_30px_#d1d9e6,-10px_-10px_30px_#ffffff] border border-white/50 relative group">
                                        <div className="absolute top-0 left-0 w-1.5 h-full bg-purple-500/50 opacity-0 group-hover:opacity-100 transition-opacity rounded-l-[32px]" />
                                        <div className="flex items-center gap-4 mb-6">
                                            <div className="w-12 h-12 bg-purple-600 rounded-[20px] flex items-center justify-center shadow-[inset_4px_4px_8px_rgba(255,255,255,0.3),inset_-4px_-4px_8px_rgba(0,0,0,0.1),8px_8px_20px_rgba(147,51,234,0.25)] text-white">
                                                <Palette size={24} strokeWidth={2.5} />
                                            </div>
                                            <div>
                                                <h3 className="text-base font-black text-slate-900 uppercase tracking-widest">Theme</h3>
                                                <p className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em] mt-1 opacity-80">Accent & Position</p>
                                            </div>
                                        </div>

                                        <div className="grid grid-cols-2 gap-6">
                                            <div className="space-y-3 text-center">
                                                <label className="text-[10px] font-black text-slate-500 uppercase tracking-[0.2em] block">Primary</label>
                                                <div className="relative w-full h-14 rounded-[20px] border-4 border-white overflow-hidden cursor-pointer hover:scale-[1.05] transition-all shadow-[4px_4px_10px_#d1d9e6,-4px_-4px_10px_#ffffff] active:scale-[0.98]">
                                                    <input type="color" value={color} className="absolute inset-0 w-[200%] h-[200%] -top-1/2 -left-1/2 cursor-pointer" onChange={(e) => setColor(e.target.value)} />
                                                </div>
                                            </div>

                                            <div className="space-y-3">
                                                <label className="text-[10px] font-black text-slate-500 uppercase tracking-[0.2em] block text-center">Position</label>
                                                <div className="flex bg-slate-100/50 p-1.5 rounded-[20px] shadow-[inset_4px_4px_8px_#d1d9e6,inset_-4px_-4px_8px_#ffffff] border border-white/50">
                                                    {['left', 'right'].map(p => (
                                                        <button
                                                            key={p} onClick={() => setPosition(p as any)}
                                                            className={`flex-1 py-3 rounded-[16px] text-[10px] font-black uppercase tracking-widest transition-all ${position === p ? 'bg-white text-[#9d55ac] shadow-[2px_2px_6px_rgba(0,0,0,0.05)] border border-white' : 'text-slate-400 hover:text-slate-600'}`}
                                                        >
                                                            {p === 'left' ? <AlignLeft size={18} className="mx-auto" /> : <AlignRight size={18} className="mx-auto" />}
                                                        </button>
                                                    ))}
                                                </div>
                                            </div>
                                        </div>
                                    </div>

                                    {/* Typography Settings */}
                                    <div className="p-6 bg-slate-50 rounded-[32px] shadow-[10px_10px_30px_#d1d9e6,-10px_-10px_30px_#ffffff] border border-white/50 relative group">
                                        <div className="absolute top-0 left-0 w-1.5 h-full bg-emerald-500/50 opacity-0 group-hover:opacity-100 transition-opacity rounded-l-[32px]" />
                                        <div className="flex items-center gap-4 mb-6">
                                            <div className="w-12 h-12 bg-emerald-600 rounded-[20px] flex items-center justify-center shadow-[inset_4px_4px_8px_rgba(255,255,255,0.3),inset_-4px_-4px_8px_rgba(0,0,0,0.1),8px_8px_20px_rgba(5,150,105,0.25)] text-white">
                                                <Layers size={24} strokeWidth={2.5} />
                                            </div>
                                            <div>
                                                <h3 className="text-base font-black text-slate-900 uppercase tracking-widest">Typography</h3>
                                                <p className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em] mt-1 opacity-80">Font & Accents</p>
                                            </div>
                                        </div>

                                        <div className="space-y-4 pt-1">
                                            <div className="space-y-3" ref={fontDropdownRef}>
                                                <label className="text-[10px] font-black text-slate-500 uppercase tracking-[0.2em] pl-1">Font Family</label>
                                                <button
                                                    onClick={() => setShowFontDropdown(!showFontDropdown)}
                                                    className="w-full bg-slate-50 border-2 border-white/80 rounded-[20px] px-5 py-4 text-sm font-black flex items-center justify-between hover:border-[#b06abf]/30 transition-all text-slate-900 shadow-[inset_4px_4px_8px_#d1d9e6,inset_-4px_-4px_8px_#ffffff]"
                                                >
                                                    <span className="truncate">{FONT_OPTIONS.find(f => f.value === fontFamily)?.label}</span>
                                                    <ChevronDown size={20} className={`transition-transform shrink-0 ${showFontDropdown ? 'rotate-180' : ''}`} />
                                                </button>
                                                <AnimatePresence>
                                                    {showFontDropdown && (
                                                        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 10 }} className="absolute bottom-full mb-4 left-0 w-full bg-slate-50 border border-white rounded-[28px] shadow-[0_20px_50px_rgba(0,0,0,0.15)] z-[100] overflow-hidden p-3 ring-1 ring-black/5">
                                                            <div className="px-2 pb-4 relative">
                                                                <Search size={18} className="absolute left-6 top-1/2 -translate-y-1/2 text-slate-400" />
                                                                <input type="text" placeholder="Search fonts..." value={fontSearch} onChange={(e) => setFontSearch(e.target.value)} className="w-full bg-white/80 border border-slate-100 rounded-[16px] pl-12 pr-4 py-3.5 text-sm outline-none focus:border-[#b06abf]/50 transition-all font-black" />
                                                            </div>
                                                            <div className="max-h-56 overflow-y-auto custom-scrollbar p-1">
                                                                {FONT_OPTIONS.filter(f => f.label.toLowerCase().includes(fontSearch.toLowerCase())).map(f => (
                                                                    <button key={f.value} onClick={() => { setFontFamily(f.value); setShowFontDropdown(false); }} className={`w-full text-left px-5 py-4 rounded-[16px] text-sm font-black transition-all mb-1 ${fontFamily === f.value ? 'bg-[#9d55ac] text-white shadow-md' : 'hover:bg-white text-slate-600'}`} style={{ fontFamily: f.value }}>{f.label}</button>
                                                                ))}
                                                            </div>
                                                        </motion.div>
                                                    )}
                                                </AnimatePresence>
                                            </div>

                                            <div className="grid grid-cols-2 gap-4">
                                                <button
                                                    onClick={() => setShowTail(!showTail)}
                                                    className={`flex items-center justify-between px-4 py-4 rounded-[20px] border-2 transition-all ${showTail ? 'bg-[#f8f0fa]/50 border-[#e0c8e6] shadow-[inset_4px_4px_8px_#d1d9e6,inset_-4px_-4px_8px_#ffffff]' : 'bg-slate-50 border-white/80 shadow-[inset_4px_4px_8px_#d1d9e6,inset_-4px_-4px_8px_#ffffff] opacity-70'}`}
                                                >
                                                    <span className={`text-[10px] font-black uppercase tracking-[0.1em] ${showTail ? 'text-[#8a4a97]' : 'text-slate-500'}`}>Chat Tail</span>
                                                    <div className={`w-10 h-5.5 rounded-full transition-all relative shadow-inner ${showTail ? 'bg-[#9d55ac]' : 'bg-slate-300'}`}>
                                                        <div className={`absolute top-[3px] w-4 h-4 bg-white rounded-full transition-all shadow-sm ${showTail ? 'right-[3px] translate-x-0' : 'left-[3px] translate-x-0'}`} />
                                                    </div>
                                                </button>
                                                <button
                                                    onClick={() => setShowLauncherBg(!showLauncherBg)}
                                                    className={`flex items-center justify-between px-4 py-4 rounded-[20px] border-2 transition-all ${showLauncherBg ? 'bg-[#f8f0fa]/50 border-[#e0c8e6] shadow-[inset_4px_4px_8px_#d1d9e6,inset_-4px_-4px_8px_#ffffff]' : 'bg-slate-50 border-white/80 shadow-[inset_4px_4px_8px_#d1d9e6,inset_-4px_-4px_8px_#ffffff] opacity-70'}`}
                                                >
                                                    <span className={`text-[10px] font-black uppercase tracking-[0.1em] ${showLauncherBg ? 'text-[#8a4a97]' : 'text-slate-500'}`}>Launcher BG</span>
                                                    <div className={`w-10 h-5.5 rounded-full transition-all relative shadow-inner ${showLauncherBg ? 'bg-[#9d55ac]' : 'bg-slate-300'}`}>
                                                        <div className={`absolute top-[3px] w-4 h-4 bg-white rounded-full transition-all shadow-sm ${showLauncherBg ? 'right-[3px] translate-x-0' : 'left-[3px] translate-x-0'}`} />
                                                    </div>
                                                </button>
                                            </div>
                                        </div>
                                    </div>
                                </div>

                                {/* Geometry Studio Section */}
                                <div className="p-6 bg-slate-50 rounded-[32px] shadow-[10px_10px_30px_#d1d9e6,-10px_-10px_30px_#ffffff] border border-white/50 relative group">
                                    <div className="absolute top-0 left-0 w-1.5 h-full bg-orange-500/50 opacity-0 group-hover:opacity-100 transition-opacity rounded-l-[32px]" />
                                    <div className="flex items-center justify-between mb-6">
                                        <div className="flex items-center gap-4">
                                            <div className="w-12 h-12 bg-orange-500 rounded-[20px] flex items-center justify-center shadow-[inset_4px_4px_8px_rgba(255,255,255,0.3),inset_-4px_-4px_8px_rgba(0,0,0,0.1),8px_8px_20px_rgba(249,115,22,0.25)] text-white">
                                                <Square size={24} strokeWidth={2.5} />
                                            </div>
                                            <div>
                                                <h3 className="text-base font-black text-slate-900 uppercase tracking-widest">Geometry</h3>
                                                <p className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em] mt-1 opacity-80">Dimensions & Shape</p>
                                            </div>
                                        </div>
                                    </div>

                                    <div className="grid grid-cols-2 gap-5">
                                        {[
                                            { label: "Logo", v: logoSize, s: setLogoSize, icon: Target },
                                            { label: "Side", v: rightPadding, s: setRightPadding, icon: AlignRight },
                                            { label: "Bottom", v: bottomPadding, s: setBottomPadding, icon: Anchor },
                                            { label: "Header", v: headerHeight, s: setHeaderHeight, icon: Layers },
                                            { label: "Radius", v: borderRadius, s: setBorderRadius, icon: Square }
                                        ].map((item, i) => (
                                            <div key={i} className="space-y-2.5">
                                                <div className="flex items-center gap-2 mb-1 pl-1">
                                                    <item.icon size={13} className="text-slate-400" />
                                                    <label className="text-[10px] font-black text-slate-500 uppercase tracking-[0.2em]">{item.label}</label>
                                                </div>
                                                <div className="relative group/input">
                                                    <input
                                                        type="number"
                                                        value={item.v}
                                                        onChange={(e) => item.s(parseInt(e.target.value) || 0)}
                                                        className="w-full bg-slate-50 border-2 border-white/80 rounded-[18px] pl-3 pr-7 py-3 text-sm font-black text-slate-900 outline-none focus:ring-4 focus:ring-[#b06abf]/5 focus:border-[#b06abf]/30 transition-all text-center shadow-[inset_4px_4px_8px_#d1d9e6,inset_-4px_-4px_8px_#ffffff] [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
                                                    />
                                                    <span className="absolute right-3 top-1/2 -translate-y-1/2 text-[9px] text-slate-300 font-extrabold uppercase tracking-tighter">px</span>
                                                </div>
                                            </div>
                                        ))}

                                        <div className="col-span-2 pt-6 mt-2 border-t border-white/50">
                                            <div className="flex items-center justify-between mb-4">
                                                <label className="text-[10px] font-black text-slate-500 uppercase tracking-[0.2em] pl-1">Launcher Shape</label>
                                            </div>
                                            <div className="grid grid-cols-4 gap-4">
                                                {[
                                                    { id: "circle", r: "50%" }, { id: "rounded", r: "14px" },
                                                    { id: "square", r: "2px" }, { id: "oval", r: "20px / 14px" }
                                                ].map(s => (
                                                    <button
                                                        key={s.id} onClick={() => setLauncherShape(s.id)}
                                                        className={`h-16 flex flex-col items-center justify-center gap-2.5 rounded-[20px] border-2 transition-all ${launcherShape === s.id ? 'bg-white border-[#c080cc] shadow-[6px_6px_12px_#d1d9e6,-6px_-6px_12px_#ffffff] scale-[1.05]' : 'bg-slate-50/50 border-white shadow-[inset_4px_4px_8px_#d1d9e6,inset_-4px_-4px_8px_#ffffff] hover:scale-[1.02]'}`}
                                                    >
                                                        <div className="w-6 h-6 bg-[#9d55ac] shadow-[inset_2px_2px_4px_rgba(255,255,255,0.3),inset_-2px_-2px_4px_rgba(0,0,0,0.1),4px_4px_8px_rgba(157,85,172,0.2)] transition-all duration-500" style={{ borderRadius: s.r }} />
                                                    </button>
                                                ))}
                                            </div>
                                        </div>
                                    </div>
                                </div>


                                {/* Interface Skin Card */}
                                <div className="p-6 bg-slate-50 rounded-[32px] shadow-[10px_10px_30px_#d1d9e6,-10px_-10px_30px_#ffffff] border border-white/50 relative group">
                                    <div className="absolute top-0 left-0 w-1.5 h-full bg-emerald-500/50 opacity-0 group-hover:opacity-100 transition-opacity rounded-l-[32px]" />
                                    <div className="flex items-center gap-4 mb-6">
                                        <div className="w-12 h-12 bg-emerald-600 rounded-[20px] flex items-center justify-center shadow-[inset_4px_4px_8px_rgba(255,255,255,0.3),inset_-4px_-4px_8px_rgba(0,0,0,0.1),8px_8px_20px_rgba(16,185,129,0.25)] text-white">
                                            <Palette size={24} strokeWidth={2.5} />
                                        </div>
                                        <div>
                                            <h3 className="text-base font-black text-slate-900 uppercase tracking-widest">Interface Skin</h3>
                                            <p className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em] mt-1 opacity-80">Global UI Palette</p>
                                        </div>
                                    </div>

                                    <div className="grid grid-cols-2 gap-6">
                                        {[
                                            { l: "Header Text", v: textColor, s: setTextColor },
                                            { l: "Chat BG", v: chatBgColor, s: setChatBgColor },
                                            { l: "Input Bar", v: inputBgColor, s: setInputBgColor },
                                            { l: "Input Text", v: inputTextColor, s: setInputTextColor }
                                        ].map((item, i) => (
                                            <div key={i} className="flex flex-col gap-3 group/swatch">
                                                <span className="text-[10px] font-black text-slate-500 uppercase tracking-widest text-center">{item.l}</span>
                                                <div className="relative w-full h-14 rounded-[20px] border-4 border-white overflow-hidden shadow-[4px_4px_10px_#d1d9e6,-4px_-4px_10px_#ffffff] hover:scale-[1.05] transition-all cursor-pointer active:scale-[0.98]">
                                                    <input type="color" value={item.v} className="absolute inset-0 w-[200%] h-[200%] -top-1/2 -left-1/2 cursor-pointer" onChange={(e) => item.s(e.target.value)} />
                                                    <div className="absolute inset-x-0 bottom-0 py-1.5 bg-black/10 backdrop-blur-md opacity-0 group-hover/swatch:opacity-100 transition-opacity flex justify-center">
                                                        <span className="text-[9px] font-black text-white uppercase tracking-tighter">{item.v}</span>
                                                    </div>
                                                </div>
                                            </div>
                                        ))}
                                    </div>

                                    <div className="grid grid-cols-1 gap-8 mt-8 pt-6 border-t border-white/50">
                                        <div className="space-y-4">
                                            <div className="flex items-center gap-3 mb-2 pl-1">
                                                <div className="w-2.5 h-2.5 bg-[#9d55ac] rounded-full shadow-[0_0_8px_rgba(157,85,172,0.4)]" />
                                                <span className="text-[11px] font-black text-slate-900 uppercase tracking-[0.2em]">User Bubble</span>
                                            </div>
                                            <div className="flex gap-4 p-5 bg-slate-100/30 rounded-[28px] border border-white/50 shadow-[inset_4px_4px_8px_#d1d9e6,inset_-4px_-4px_8px_#ffffff]">
                                                <div className="flex-1 space-y-3">
                                                    <span className="text-[9px] font-black text-slate-400 uppercase block pl-1 tracking-widest">Fill</span>
                                                    <div className="relative h-12 rounded-[16px] border-4 border-white shadow-[2px_2px_6px_rgba(0,0,0,0.05)] overflow-hidden">
                                                        <input type="color" value={userBubbleBg} className="absolute inset-0 w-[200%] h-[200%] -top-1/2 -left-1/2 cursor-pointer" onChange={(e) => setUserBubbleBg(e.target.value)} />
                                                    </div>
                                                </div>
                                                <div className="flex-1 space-y-3">
                                                    <span className="text-[9px] font-black text-slate-400 uppercase block pl-1 tracking-widest">Text</span>
                                                    <div className="relative h-12 rounded-[16px] border-4 border-white shadow-[2px_2px_6px_rgba(0,0,0,0.05)] overflow-hidden">
                                                        <input type="color" value={userBubbleText} className="absolute inset-0 w-[200%] h-[200%] -top-1/2 -left-1/2 cursor-pointer" onChange={(e) => setUserBubbleText(e.target.value)} />
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                        <div className="space-y-4">
                                            <div className="flex items-center gap-3 mb-2 pl-1">
                                                <div className="w-2.5 h-2.5 bg-slate-400 rounded-full shadow-[0_0_8px_rgba(148,163,184,0.4)]" />
                                                <span className="text-[11px] font-black text-slate-900 uppercase tracking-[0.2em]">Bot Bubble</span>
                                            </div>
                                            <div className="flex gap-4 p-5 bg-slate-100/30 rounded-[28px] border border-white/50 shadow-[inset_4px_4px_8px_#d1d9e6,inset_-4px_-4px_8px_#ffffff]">
                                                <div className="flex-1 space-y-3">
                                                    <span className="text-[9px] font-black text-slate-400 uppercase block pl-1 tracking-widest">Fill</span>
                                                    <div className="relative h-12 rounded-[16px] border-4 border-white shadow-[2px_2px_6px_rgba(0,0,0,0.05)] overflow-hidden">
                                                        <input type="color" value={assistantBubbleBg} className="absolute inset-0 w-[200%] h-[200%] -top-1/2 -left-1/2 cursor-pointer" onChange={(e) => setAssistantBubbleBg(e.target.value)} />
                                                    </div>
                                                </div>
                                                <div className="flex-1 space-y-3">
                                                    <span className="text-[9px] font-black text-slate-400 uppercase block pl-1 tracking-widest">Text</span>
                                                    <div className="relative h-12 rounded-[16px] border-4 border-white shadow-[2px_2px_6px_rgba(0,0,0,0.05)] overflow-hidden">
                                                        <input type="color" value={assistantBubbleText} className="absolute inset-0 w-[200%] h-[200%] -top-1/2 -left-1/2 cursor-pointer" onChange={(e) => setAssistantBubbleText(e.target.value)} />
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                    </div>

                                    <div className="mt-8 pt-6 border-t border-white/50 space-y-6">
                                        <div className="flex items-center justify-between mb-2">
                                            <div className="flex items-center gap-4">
                                                <div className="w-10 h-10 bg-[#9d55ac] rounded-[16px] flex items-center justify-center shadow-[inset_4px_4px_8px_rgba(255,255,255,0.3),inset_-4px_-4px_8px_rgba(0,0,0,0.1),6px_6px_16px_rgba(157,85,172,0.25)] text-white">
                                                    <Layout size={20} />
                                                </div>
                                                <div>
                                                    <h3 className="text-sm font-black text-slate-900 uppercase tracking-widest">Chat Backdrop</h3>
                                                </div>
                                            </div>
                                            <span className="px-4 py-1.5 bg-[#f8f0fa]/50 text-[#9d55ac] rounded-xl text-[10px] font-black uppercase tracking-widest border border-white shadow-sm">{Math.round(backgroundOpacity * 100)}% Visibility</span>
                                        </div>

                                        <div className="grid grid-cols-1 gap-6">
                                            <div className="relative group">
                                                <input
                                                    type="text"
                                                    value={backgroundImage}
                                                    onChange={(e) => setBackgroundImage(e.target.value)}
                                                    placeholder="Paste backdrop URL or upload image..."
                                                    className="w-full bg-slate-50 border-2 border-white/80 rounded-[20px] px-5 py-4 text-sm font-black outline-none focus:ring-4 focus:ring-[#b06abf]/5 focus:border-[#b06abf]/30 transition-all text-slate-900 placeholder:text-slate-300 pr-16 shadow-[inset_4px_4px_8px_#d1d9e6,inset_-4px_-4px_8px_#ffffff]"
                                                />
                                                <button
                                                    onClick={() => backgroundInputRef.current?.click()}
                                                    disabled={backgroundLoading}
                                                    className="absolute right-2 top-1/2 -translate-y-1/2 p-2 bg-white text-slate-400 rounded-[14px] hover:bg-[#9d55ac] hover:text-white transition-all disabled:opacity-50 border border-white shadow-[2px_2px_4px_#d1d9e6,-2px_-2px_4px_#ffffff]"
                                                >
                                                    <Upload size={18} className={backgroundLoading ? "animate-spin" : ""} strokeWidth={2.5} />
                                                </button>
                                                <input type="file" ref={backgroundInputRef} onChange={handleBackgroundUpload} className="hidden" accept="image/*" />
                                            </div>
                                            <div className="px-6 py-6 bg-slate-100/30 rounded-[28px] border border-white/50 shadow-[inset_6px_6px_12px_#d1d9e6,inset_-6px_-6px_12px_#ffffff] flex items-center gap-6">
                                                <div className="text-[10px] font-black text-slate-400 uppercase tracking-[0.3em] shrink-0 transform -rotate-90">Opacity</div>
                                                <input
                                                    type="range" min="0" max="1" step="0.01"
                                                    value={backgroundOpacity}
                                                    onChange={(e) => setBackgroundOpacity(parseFloat(e.target.value))}
                                                    className="flex-1 h-2 bg-slate-200/50 rounded-full appearance-none transition-all accent-[#9d55ac] cursor-pointer shadow-inner"
                                                />
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </motion.div>
                        )}

                        {activeTab === "knowledge" && (
                            <motion.div key="knowledge" className="space-y-6">
                                <div className="p-6 bg-slate-50 border border-slate-200 rounded-3xl space-y-6 shadow-sm">
                                    <div className="flex items-center gap-4 mb-2">
                                        <div className="p-3 bg-[#9d55ac] shadow-[0_4px_12px_rgba(157,85,172,0.2)] rounded-2xl">
                                            <Brain size={24} className="text-white" />
                                        </div>
                                        <div>
                                            <h3 className="text-base font-black text-slate-900">AI Model & Provider</h3>
                                            <p className="text-[10px] text-slate-400 uppercase tracking-[0.2em] font-black">Configure the brain</p>
                                        </div>
                                    </div>

                                    <div className="grid grid-cols-2 gap-4">
                                        <div className="space-y-2">
                                            <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Provider</label>
                                            <select
                                                value={aiProvider}
                                                onChange={(e) => {
                                                    const p = e.target.value;
                                                    setAiProvider(p);
                                                    if (p === "google") setAiModel("gemini-3-flash-preview");
                                                    if (p === "openai") setAiModel("gpt-4o-mini");
                                                    if (p === "groq") setAiModel("llama3-8b-8192");
                                                }}
                                                className="w-full bg-white border border-slate-200 rounded-2xl px-4 py-3 text-sm outline-none focus:ring-2 focus:ring-[#b06abf]/20 focus:border-[#b06abf] transition-all text-slate-900 shadow-sm appearance-none cursor-pointer"
                                            >
                                                <option value="google">Google Gemini</option>
                                                <option value="openai">OpenAI ChatGPT</option>
                                                <option value="groq">Llama 3 (via Groq)</option>
                                            </select>
                                        </div>

                                        <div className="space-y-2">
                                            <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">Model</label>
                                            <select
                                                value={aiModel}
                                                onChange={(e) => setAiModel(e.target.value)}
                                                className="w-full bg-white border border-slate-200 rounded-2xl px-4 py-3 text-sm outline-none focus:ring-2 focus:ring-[#b06abf]/20 focus:border-[#b06abf] transition-all text-slate-900 shadow-sm appearance-none cursor-pointer"
                                            >
                                                {aiProvider === "google" && (
                                                    <>
                                                        <option value="gemini-2.0-flash">Gemini 2.0 Flash</option>
                                                        <option value="gemini-3-flash-preview">gemini-3-flash-preview</option>
                                                    </>
                                                )}
                                                {aiProvider === "openai" && (
                                                    <>
                                                        <option value="gpt-4o">GPT-4o</option>
                                                        <option value="gpt-4o-mini">GPT-4o Mini</option>
                                                    </>
                                                )}
                                            </select>
                                        </div>

                                        <div className="col-span-2 space-y-2">
                                            <div className="flex justify-between items-center">
                                                <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">API Key (Leave blank to use system default)</label>
                                                {aiApiKey && <Check size={14} className="text-green-600" />}
                                            </div>
                                            <input
                                                type="password"
                                                value={aiApiKey}
                                                onChange={(e) => setAiApiKey(e.target.value)}
                                                placeholder={`Enter your ${aiProvider.toUpperCase()} API Key`}
                                                className="w-full bg-white border border-slate-200 rounded-2xl px-4 py-3 text-sm outline-none focus:ring-2 focus:ring-[#b06abf]/20 focus:border-[#b06abf] transition-all text-slate-900 shadow-sm"
                                            />
                                        </div>
                                    </div>
                                </div>

                                <div className="space-y-4">
                                    <div className="p-5 bg-white border border-slate-200 rounded-3xl space-y-4 shadow-sm">
                                        <div className="flex items-center gap-3">
                                            <div className="p-2 bg-[#f8f0fa] text-[#9d55ac] rounded-xl border border-[#f0e0f4]">
                                                <Globe size={20} />
                                            </div>
                                            <h4 className="text-[11px] font-black uppercase tracking-[0.15em] text-slate-800">Website Crawler</h4>
                                        </div>
                                        <div className="space-y-3">
                                            <input
                                                type="text"
                                                placeholder="https://example.com"
                                                value={crawlUrl}
                                                onChange={(e) => setCrawlUrl(e.target.value)}
                                                className="w-full bg-slate-50 border border-slate-200 rounded-2xl px-4 py-3 text-sm outline-none focus:ring-2 focus:ring-[#b06abf]/20 focus:border-[#b06abf] shadow-inner"
                                            />
                                            <button
                                                onClick={handleCrawl}
                                                disabled={crawling}
                                                className="w-full py-3 bg-[#9d55ac] text-white rounded-2xl text-xs font-black uppercase tracking-widest hover:bg-[#8a4a97] disabled:opacity-50 transition-all shadow-[0_4px_12px_rgba(157,85,172,0.2)] active:scale-[0.98]"
                                            >
                                                {crawling ? "Crawling..." : "Start Crawling"}
                                            </button>
                                        </div>
                                    </div>

                                    <div className="p-5 bg-white border border-slate-200 rounded-3xl space-y-4 shadow-sm">
                                        <div className="flex items-center gap-3">
                                            <div className="p-2 bg-red-50 text-red-600 rounded-xl border border-red-100">
                                                <Video size={20} />
                                            </div>
                                            <h4 className="text-[11px] font-black uppercase tracking-[0.15em] text-slate-800">YouTube Extract</h4>
                                        </div>
                                        <div className="space-y-3">
                                            <input
                                                type="text"
                                                placeholder="YouTube Video URL"
                                                value={youtubeUrl}
                                                onChange={(e) => setYoutubeUrl(e.target.value)}
                                                className="w-full bg-slate-50 border border-slate-200 rounded-2xl px-4 py-3 text-sm outline-none focus:ring-2 focus:ring-red-500/20 focus:border-red-500 shadow-inner"
                                            />
                                            <button
                                                onClick={handleYouTubeExtract}
                                                disabled={crawling}
                                                className="w-full py-3 bg-red-600 text-white rounded-2xl text-xs font-black uppercase tracking-widest hover:bg-red-700 disabled:opacity-50 transition-all shadow-[0_4px_12px_rgba(220,38,38,0.2)] active:scale-[0.98]"
                                            >
                                                {crawling ? "Extracting..." : "Extract Transcript"}
                                            </button>
                                        </div>
                                    </div>
                                </div>

                                <div className="flex items-center justify-between p-6 bg-gradient-to-r from-[#f8f0fa] to-purple-50 border border-[#f0e0f4] rounded-3xl shadow-sm">
                                    <div className="flex items-center gap-4">
                                        <div className="w-12 h-12 bg-white rounded-2xl flex items-center justify-center shadow-md border border-white">
                                            <Search size={22} className="text-[#9d55ac]" />
                                        </div>
                                        <div>
                                            <h4 className="font-black text-sm text-slate-900">Live Web Search (RAG)</h4>
                                            <p className="text-[11px] text-slate-500 font-bold uppercase tracking-widest">Real-time web access</p>
                                        </div>
                                    </div>
                                    <button
                                        onClick={() => setLiveSearchEnabled(!liveSearchEnabled)}
                                        className={`w-12 h-6 rounded-full transition-all relative ${liveSearchEnabled ? 'bg-[#9d55ac] shadow-[0_4px_12px_rgba(157,85,172,0.2)]' : 'bg-slate-200'}`}
                                    >
                                        <div className={`absolute top-1 w-4 h-4 rounded-full bg-white shadow-sm transition-all ${liveSearchEnabled ? 'right-1' : 'left-1'}`} />
                                    </button>
                                </div>

                                <div
                                    onClick={() => !knowledgeLoading && knowledgeInputRef.current?.click()}
                                    className={`border-2 border-dashed rounded-[32px] p-10 text-center transition-all cursor-pointer group shadow-sm bg-white ${knowledgeLoading ? 'border-[#b06abf] bg-[#f8f0fa]' : 'border-slate-200 hover:border-[#c080cc] hover:bg-slate-50'}`}
                                >
                                    {knowledgeLoading ? (
                                        <div className="flex flex-col items-center">
                                            <div className="w-14 h-14 border-4 border-[#b06abf]/10 border-t-[#9d55ac] rounded-full animate-spin mb-4" />
                                            <p className="font-black text-lg text-[#9d55ac] uppercase tracking-widest">Processing Data...</p>
                                        </div>
                                    ) : (
                                        <>
                                            <div className="w-20 h-20 bg-slate-50 rounded-3xl flex items-center justify-center mx-auto mb-6 group-hover:scale-110 transition-transform">
                                                <Upload className="text-slate-300 group-hover:text-[#b06abf] transition-colors" size={40} />
                                            </div>
                                            <p className="font-black text-xl mb-1 text-slate-800">Upload Data Source</p>
                                            <p className="text-slate-400 text-xs font-bold uppercase tracking-widest mt-2">Support: PDF, TXT, CSV, DOCX</p>
                                        </>
                                    )}
                                    <input
                                        type="file"
                                        ref={knowledgeInputRef}
                                        onChange={handleKnowledgeUpload}
                                        className="hidden"
                                        accept=".pdf,.txt"
                                    />
                                </div>

                                <div className="space-y-4">
                                    <h4 className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em] flex justify-between px-2">
                                        Manual Knowledge Base
                                        <span className="text-[#9d55ac] font-mono font-black">{knowledgeBase.length} chars</span>
                                    </h4>
                                    <textarea
                                        rows={10}
                                        value={knowledgeBase}
                                        onChange={(e) => setKnowledgeBase(e.target.value)}
                                        placeholder="Enter product details, company info, FAQs..."
                                        className="w-full bg-white border border-slate-200 rounded-3xl px-6 py-6 outline-none focus:ring-4 focus:ring-[#b06abf]/5 focus:border-[#c080cc] shadow-sm transition-all resize-none text-sm leading-relaxed text-slate-800"
                                    />
                                </div>
                            </motion.div>
                        )}

                        {activeTab === "personality" && (
                            <motion.div key="personality" className="space-y-8">
                                <div className="space-y-4">
                                    <label className="block text-[10px] font-black text-slate-400 uppercase tracking-[0.2em] pl-1">System Instructions</label>
                                    <textarea
                                        rows={8}
                                        value={systemPrompt}
                                        onChange={(e) => setSystemPrompt(e.target.value)}
                                        placeholder="e.g. You are a professional sales assistant for a tech company..."
                                        className="w-full bg-white border border-slate-200 rounded-3xl px-6 py-6 outline-none focus:ring-4 focus:ring-[#b06abf]/5 focus:border-[#c080cc] shadow-sm transition-all resize-none text-sm leading-relaxed text-slate-800"
                                    />
                                    <p className="text-[11px] text-slate-400 font-bold leading-relaxed px-1">
                                        Define your bot's behavior, personality traits, and specific constraints.
                                    </p>
                                </div>
                                <div className="p-6 bg-slate-50 rounded-[32px] border border-slate-200 shadow-inner">
                                    <h5 className="font-black text-[10px] text-slate-400 uppercase tracking-widest mb-4">Personality Presets</h5>
                                    <div className="flex flex-wrap gap-2">
                                        {["Professional", "Friendly", "Concise", "Sassy", "Helpful", "Sales-driven"].map(m => (
                                            <button
                                                key={m}
                                                onClick={() => setSystemPrompt(`You are a ${m.toLowerCase()} AI assistant. Focus on being helpful and accurate.`)}
                                                className="px-4 py-2 bg-white border border-slate-200 rounded-xl text-xs font-black text-slate-600 hover:border-[#c080cc] hover:text-[#9d55ac] transition-all shadow-sm active:scale-95"
                                            >
                                                {m}
                                            </button>
                                        ))}
                                    </div>
                                </div>
                            </motion.div>
                        )}

                        {activeTab === "storage" && (
                            <motion.div key="storage" className="space-y-6">
                                <div className="flex justify-between items-center bg-slate-50 p-6 rounded-3xl border border-slate-200 shadow-sm">
                                    <div>
                                        <h3 className="font-bold text-lg text-slate-900">Lead Storage</h3>
                                        <p className="text-slate-500 text-xs font-medium uppercase tracking-widest">Captured from flows</p>
                                    </div>
                                    <div className="bg-[#9d55ac] shadow-lg shadow-[#b06abf]/20 text-white px-4 py-2 rounded-xl text-sm font-black flex items-center gap-2">
                                        <Inbox size={16} /> {leads.length} Leads
                                    </div>
                                </div>

                                <div className="bg-white border border-slate-200 rounded-3xl overflow-hidden min-h-[400px] shadow-sm">
                                    {leadsLoading ? (
                                        <div className="flex flex-col items-center justify-center h-[400px]">
                                            <div className="w-10 h-10 border-4 border-[#b06abf]/10 border-t-[#b06abf] rounded-full animate-spin mb-4" />
                                            <p className="text-slate-400 text-[10px] uppercase font-black tracking-[0.2em]">Syncing Records...</p>
                                        </div>
                                    ) : leads.length === 0 ? (
                                        <div className="flex flex-col items-center justify-center h-[400px] text-center p-8">
                                            <div className="w-20 h-20 bg-slate-50 rounded-[32px] flex items-center justify-center mb-6 shadow-inner ring-1 ring-slate-100">
                                                <List size={32} className="text-slate-200" />
                                            </div>
                                            <h4 className="font-black text-slate-800 mb-2 uppercase tracking-tight">No Leads Yet</h4>
                                            <p className="text-slate-400 text-[11px] font-medium max-w-[250px] leading-relaxed">
                                                When users complete forms in your bot flow, their data will appear here.
                                            </p>
                                        </div>
                                    ) : (
                                        <div className="overflow-x-auto">
                                            <table className="w-full text-left">
                                                <thead>
                                                    <tr className="bg-slate-50 border-b border-slate-200">
                                                        <th className="px-6 py-4 text-[10px] font-black text-slate-400 uppercase tracking-widest">Time</th>
                                                        <th className="px-6 py-4 text-[10px] font-black text-slate-400 uppercase tracking-widest">Data Captured</th>
                                                        <th className="px-6 py-4 text-right text-[10px] font-black text-slate-400 uppercase tracking-widest">Session</th>
                                                    </tr>
                                                </thead>
                                                <tbody className="divide-y divide-slate-100">
                                                    {leads.map((lead: any) => (
                                                        <tr key={lead.id} className="hover:bg-slate-50/50 transition-colors group">
                                                            <td className="px-6 py-4 whitespace-nowrap">
                                                                <p className="text-[11px] font-black text-slate-900">
                                                                    {new Date(lead.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                                                                </p>
                                                                <p className="text-[9px] text-slate-400 font-bold uppercase tracking-tighter">
                                                                    {new Date(lead.created_at).toLocaleDateString()}
                                                                </p>
                                                            </td>
                                                            <td className="px-6 py-4">
                                                                <div className="flex flex-wrap gap-2">
                                                                    {Object.entries(lead.data).map(([key, value]: [string, any]) => (
                                                                        <div key={key} className="bg-white border border-slate-200 rounded-xl px-2.5 py-1 flex items-center gap-2 shadow-sm transition-transform hover:scale-105">
                                                                            <span className="text-[9px] font-black text-[#9d55ac] uppercase tracking-tighter">{key}:</span>
                                                                            <span className="text-[10px] text-slate-700 font-bold">{value}</span>
                                                                        </div>
                                                                    ))}
                                                                </div>
                                                            </td>
                                                            <td className="px-6 py-4 text-right">
                                                                <span className="text-[9px] font-mono text-slate-300 group-hover:text-slate-500 transition-colors bg-slate-50 px-2 py-0.5 rounded-lg border border-slate-100">
                                                                    {lead.session_id.slice(0, 8)}
                                                                </span>
                                                            </td>
                                                        </tr>
                                                    ))}
                                                </tbody>
                                            </table>
                                        </div>
                                    )}
                                </div>
                            </motion.div>
                        )}
                    </AnimatePresence>
                </div>
            </aside>

            {/* Main Preview Area */}
            <main className="flex-1 bg-slate-50 relative flex items-center justify-center p-4 sm:p-8 lg:p-12 overflow-hidden shadow-inner">
                {/* Abstract Background for Preview */}
                <div className="absolute inset-0 z-0">
                    <div className="absolute top-0 left-0 w-full h-full bg-[radial-gradient(#e2e8f0_1px,transparent_1px)] [background-size:16px_16px] [mask-image:radial-gradient(ellipse_50%_50%_at_50%_50%,#000_70%,transparent_100%)] opacity-30" />
                    <div className="absolute top-1/4 left-1/4 w-[500px] h-[500px] bg-[#9d55ac]/5 blur-[150px] rounded-full" />
                    <div className="absolute bottom-1/4 right-1/4 w-[400px] h-[400px] bg-purple-600/5 blur-[120px] rounded-full" />
                </div>

                <div ref={previewContainerRef} className="relative z-10 w-full h-full flex flex-col items-center justify-center">
                    <div className="flex bg-slate-200/50 p-1 rounded-full mb-8 border border-slate-300 shadow-sm backdrop-blur-sm relative z-20">
                        <button
                            onClick={() => setPreviewMode('desktop')}
                            className={`px-4 py-1.5 shadow-sm rounded-full text-xs font-bold flex items-center gap-2 transition-all ${previewMode === 'desktop' ? 'bg-white text-slate-800' : 'text-slate-500 hover:text-slate-800'}`}>
                            <Monitor size={14} className={previewMode === 'desktop' ? "text-[#9d55ac]" : ""} /> Desktop
                        </button>
                        <button
                            onClick={() => setPreviewMode('mobile')}
                            className={`px-4 py-1.5 shadow-sm rounded-full text-xs font-bold flex items-center gap-2 transition-all ${previewMode === 'mobile' ? 'bg-white text-slate-800' : 'text-slate-500 hover:text-slate-800'}`}>
                            <Smartphone size={14} className={previewMode === 'mobile' ? "text-[#9d55ac]" : ""} /> Mobile
                        </button>
                    </div>

                    {previewMode === 'desktop' ? (
                        <div className="w-full flex items-center justify-center" style={{ maxHeight: 'calc(100vh - 200px)' }}>
                            <div className="origin-center transition-transform duration-300" style={{ transform: `scale(${previewScale})` }}>
                                <div
                                    className="bg-white rounded-2xl overflow-hidden shadow-2xl border border-slate-200 relative flex flex-col transition-all duration-500 animate-in fade-in zoom-in-95"
                                    style={{ width: '900px', height: '562px' }}
                                >
                                    <div className="h-10 bg-slate-100 border-b border-slate-200 flex items-center px-4 gap-2 shrink-0">
                                        <div className="w-3 h-3 rounded-full bg-red-400" />
                                        <div className="w-3 h-3 rounded-full bg-amber-400" />
                                        <div className="w-3 h-3 rounded-full bg-green-400" />
                                        <div className="flex-1 ml-4 mr-10 bg-white border border-slate-200 h-6 rounded-md shadow-inner flex items-center px-3">
                                            <div className="w-24 h-2 bg-slate-200 rounded-full" />
                                        </div>
                                    </div>
                                    <div className="flex-1 bg-slate-50 relative p-8">
                                        <div className="max-w-md space-y-6">
                                            <div className="w-48 h-8 bg-slate-200 rounded-xl" />
                                            <div className="space-y-3">
                                                <div className="w-full h-4 bg-slate-200 rounded-md" />
                                                <div className="w-5/6 h-4 bg-slate-200 rounded-md" />
                                                <div className="w-4/6 h-4 bg-slate-200 rounded-md" />
                                            </div>
                                            <div className="w-32 h-10 bg-[#f0e0f4] rounded-xl mt-8" />
                                        </div>
                                        <div className="absolute right-8 top-8 w-64 h-48 bg-slate-200 rounded-2xl" />

                                        <div
                                            className="absolute flex flex-col overflow-hidden shadow-[0_24px_48px_-12px_rgba(0,0,0,0.15)] ring-1 ring-slate-900/5 transition-all duration-300"
                                            style={{
                                                fontFamily: fontFamily,
                                                borderRadius: `${borderRadius}px`,
                                                width: '300px',
                                                height: '350px',
                                                bottom: `${bottomPadding + 70}px`,
                                                right: position === 'right' ? `${rightPadding}px` : 'auto',
                                                left: position === 'left' ? `${rightPadding}px` : 'auto',
                                                zIndex: 30
                                            }}
                                        >
                                            <ChatbotWidgetContent
                                                botName={botName}
                                                botLogo={botLogo}
                                                color={color}
                                                textColor={textColor}
                                                headerHeight={headerHeight}
                                                chatBgColor={chatBgColor}
                                                backgroundImage={backgroundImage}
                                                backgroundOpacity={backgroundOpacity}
                                                assistantBubbleBg={assistantBubbleBg}
                                                assistantBubbleText={assistantBubbleText}
                                                userBubbleBg={userBubbleBg}
                                                userBubbleText={userBubbleText}
                                                borderRadius={borderRadius}
                                                inputBgColor={inputBgColor}
                                                inputTextColor={inputTextColor}
                                            />
                                        </div>

                                        <div
                                            className="absolute flex items-center justify-center pointer-events-auto"
                                            style={{
                                                bottom: `${bottomPadding}px`,
                                                right: position === 'right' ? `${rightPadding}px` : 'auto',
                                                left: position === 'left' ? `${rightPadding}px` : 'auto',
                                                zIndex: 40
                                            }}
                                        >
                                            <LauncherPreview
                                                color={color}
                                                showLauncherBg={showLauncherBg}
                                                launcherShape={launcherShape}
                                                botLogo={botLogo}
                                                logoSize={logoSize}
                                                showTail={showTail}
                                            />
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    ) : (
                        <div
                            className="w-full max-w-[360px] aspect-[9/16] max-h-[70vh] lg:max-h-[650px] bg-zinc-950 border-[10px] border-zinc-900 shadow-[0_32px_64px_-12px_rgba(0,0,0,0.3)] flex flex-col overflow-hidden ring-1 ring-white/10 transition-all duration-500 animate-in fade-in slide-in-from-bottom-8 relative z-20"
                            style={{ fontFamily: fontFamily, borderRadius: `${borderRadius * 1.5}px` }}
                        >
                            <div className="absolute top-0 inset-x-0 h-6 bg-transparent flex justify-center z-50 pointer-events-none">
                                <div className="w-32 h-6 bg-zinc-900 rounded-b-2xl" />
                            </div>
                            <ChatbotWidgetContent
                                botName={botName}
                                botLogo={botLogo}
                                color={color}
                                textColor={textColor}
                                headerHeight={headerHeight}
                                chatBgColor={chatBgColor}
                                backgroundImage={backgroundImage}
                                backgroundOpacity={backgroundOpacity}
                                assistantBubbleBg={assistantBubbleBg}
                                assistantBubbleText={assistantBubbleText}
                                userBubbleBg={userBubbleBg}
                                userBubbleText={userBubbleText}
                                borderRadius={borderRadius}
                                inputBgColor={inputBgColor}
                                inputTextColor={inputTextColor}
                            />
                        </div>
                    )}

                    {previewMode === 'mobile' && (
                        <div
                            className="fixed flex flex-col items-center justify-center pointer-events-none transition-all duration-300"
                            style={{
                                bottom: `${bottomPadding}px`,
                                right: position === 'right' ? `${rightPadding}px` : 'auto',
                                left: position === 'left' ? `${rightPadding}px` : 'auto',
                                zIndex: 50
                            }}
                        >
                            <LauncherPreview
                                color={color}
                                showLauncherBg={showLauncherBg}
                                launcherShape={launcherShape}
                                botLogo={botLogo}
                                logoSize={logoSize}
                                showTail={showTail}
                            />
                            <p className="mt-8 text-slate-400 text-[10px] uppercase tracking-[0.3em] font-black drop-shadow-sm">Launcher Position</p>
                        </div>
                    )}

                    <p className="mt-8 text-slate-300 text-xs uppercase tracking-[0.3em] font-black z-10">Real-time Component Preview</p>
                </div>
            </main>

            <AnimatePresence>
                {showExport && (
                    <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        className="fixed inset-0 z-[90]"
                    >
                        <ExportModal botId={id} onClose={() => setShowExport(false)} />
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
}

export default function Builder(props: any) {
    return (
        <Suspense fallback={<div className="h-screen bg-black flex items-center justify-center text-white">Loading...</div>}>
            <BuilderContent {...props} />
        </Suspense>
    );
}
