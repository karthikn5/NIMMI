"use client";

import { useState, use, useEffect, useCallback, useRef, Suspense } from "react";
import {
    Bot, Palette, Database, Brain, GitBranch,
    ChevronLeft, Save, Upload, Plus, MessageSquare,
    Smartphone, Monitor, Send, Image as ImageIcon, Settings as SettingsIcon,
    Play, Check, Inbox, List, Search, ChevronDown, X, Globe, Video
} from "lucide-react";
import Link from "next/link";
import { motion, AnimatePresence } from "framer-motion";
import { useRouter, useSearchParams } from "next/navigation";
import { Node, Edge } from "reactflow";
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
    const [aiModel, setAiModel] = useState("gemini-2.0-flash");
    const [aiApiKey, setAiApiKey] = useState("");
    const fileInputRef = useRef<HTMLInputElement>(null);
    const knowledgeInputRef = useRef<HTMLInputElement>(null);
    const [knowledgeLoading, setKnowledgeLoading] = useState(false);
    const [crawlUrl, setCrawlUrl] = useState("");
    const [youtubeUrl, setYoutubeUrl] = useState("");
    const [liveSearchEnabled, setLiveSearchEnabled] = useState(false);
    const [crawling, setCrawling] = useState(false);
    const router = useRouter();

    // Flow state
    const [flowNodes, setFlowNodes] = useState<Node[]>([]);
    const [flowEdges, setFlowEdges] = useState<Edge[]>([]);
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
                setAiModel(data.ai_model || "gemini-2.0-flash");
                setAiApiKey(data.ai_api_key || "");
                if (data.flow_data) {
                    setFlowNodes(data.flow_data.nodes || []);
                    setFlowEdges(data.flow_data.edges || []);
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
                    aiModel: data.ai_model || "gemini-2.0-flash",
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

    const handleNodeSelect = useCallback((node: Node | null) => {
        setSelectedNode(node);
    }, []);

    const handleNodeUpdate = useCallback((nodeId: string, data: any) => {
        setFlowNodes((nodes) =>
            nodes.map((n) => (n.id === nodeId ? { ...n, data } : n))
        );
    }, []);

    const handleNodeDelete = useCallback((nodeId: string) => {
        setFlowNodes((nodes) => nodes.filter((n) => n.id !== nodeId));
        setFlowEdges((edges) =>
            edges.filter((e) => e.source !== nodeId && e.target !== nodeId)
        );
        setSelectedNode(null);
    }, []);

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
            <div className="flex h-screen bg-[#050505] text-white">
                {/* Left Sidebar - Elements */}
                <aside className="w-72 border-r border-white/5 flex flex-col">
                    <header className="p-4 border-b border-white/5 flex items-center justify-between">
                        <Link href="/dashboard" className="p-2 hover:bg-white/5 rounded-lg transition-colors">
                            <ChevronLeft size={20} />
                        </Link>
                        <span className="text-xs font-bold text-white/50 uppercase tracking-widest">Flow Builder</span>
                        <div className="flex items-center gap-2">
                            <Link
                                href={`/demo/${id}`}
                                target="_blank"
                                className="flex items-center gap-1 px-3 py-1.5 bg-white/5 border border-white/10 rounded-lg text-xs font-bold hover:bg-white/10 transition-colors"
                            >
                                <Play size={12} fill="currentColor" /> Run
                            </Link>
                            <button
                                onClick={() => handleSave()}
                                disabled={saving}
                                className={`flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${saved ? "bg-green-600" : "bg-blue-600 hover:bg-blue-500"} disabled:opacity-50`}
                            >
                                {saved ? <Check size={12} /> : <Save size={12} />}
                                {saving ? "..." : saved ? "Saved!" : "Save"}
                            </button>
                        </div>
                    </header>

                    {/* Tab Switcher */}
                    <div className="flex p-2 gap-1 bg-white/5 mx-4 mt-4 rounded-xl">
                        {tabs.map(tab => (
                            <button
                                key={tab.id}
                                onClick={() => setActiveTab(tab.id)}
                                className={`flex-1 flex flex-col items-center gap-1 py-2 rounded-lg text-[10px] font-bold transition-all ${activeTab === tab.id ? "bg-white/10 text-white" : "text-white/40 hover:text-white/60"}`}
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
                            initialNodes={flowNodes}
                            initialEdges={flowEdges}
                            onSave={handleFlowSave}
                            onNodeSelect={handleNodeSelect}
                        />
                    </div>
                </main>

                {/* Right Sidebar - Properties */}
                <aside className="w-80 border-l border-white/5 p-4 overflow-y-auto">
                    <h3 className="text-xs font-bold text-white/50 uppercase tracking-widest mb-4">
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
                        <div className="text-center py-12 text-white/20">
                            <GitBranch size={48} className="mx-auto mb-4 opacity-50" />
                            <p className="text-sm">Click on an element in the canvas to edit its properties</p>
                        </div>
                    )}
                </aside>
            </div>
        );
    }

    // Default layout for other tabs
    return (
        <div className="flex h-screen bg-[#050505] text-white">
            {/* Load only the selected font to save bandwidth */}
            {fontFamily !== "sans-serif" && fontFamily !== "serif" && fontFamily !== "monospace" && (
                <link 
                    rel="stylesheet" 
                    href={`https://fonts.googleapis.com/css2?family=${fontFamily.replace(/'/g, "").split(",")[0].replace(/ /g, "+")}:wght@400;700&display=swap`} 
                />
            )}
            {/* Sidebar / Left Config */}
            <aside className="w-[450px] border-r border-white/5 flex flex-col">
                <header className="px-4 py-4 border-b border-white/5 flex items-center justify-between gap-3">
                    <Link href="/dashboard" className="p-1.5 hover:bg-white/5 rounded-lg transition-colors shrink-0">
                        <ChevronLeft size={20} />
                    </Link>
                    <div className="flex items-center gap-1.5 font-bold uppercase text-[10px] tracking-widest text-white/50 truncate">
                        Bot Builder <span className="text-white">#{id.slice(0, 8)}</span>
                    </div>
                    <div className="flex items-center gap-1.5 shrink-0">
                        <Link
                            href={`/demo/${id}`}
                            target="_blank"
                            className="flex items-center gap-1.5 px-2.5 py-2 bg-white/5 border border-white/10 rounded-lg text-xs font-bold hover:bg-white/10 transition-colors"
                        >
                            <Play size={14} fill="currentColor" /> Run
                        </Link>
                        <button
                            onClick={() => handleSave()}
                            disabled={saving}
                            className={`flex items-center gap-1.5 px-2.5 py-2 rounded-lg text-xs font-bold transition-all ${saved ? "bg-green-600 shadow-[0_0_20px_rgba(22,163,74,0.4)]" : "bg-blue-600 hover:bg-blue-500"} disabled:opacity-50`}
                        >
                            {saved ? <Check size={14} /> : <Save size={14} />}
                            {saving ? "..." : saved ? "Done!" : "Save"}
                        </button>
                        <button
                            onClick={() => setShowExport(true)}
                            className="flex items-center gap-1.5 px-2.5 py-2 bg-white/10 border border-white/10 rounded-lg text-xs font-bold hover:bg-white/20 transition-colors"
                        >
                            <Upload size={14} /> Export
                        </button>
                    </div>
                </header>

                {/* Tab Switcher */}
                <div className="flex p-2 gap-1 bg-white/5 mx-6 mt-6 rounded-xl">
                    {tabs.map(tab => (
                        <button
                            key={tab.id}
                            onClick={() => setActiveTab(tab.id)}
                            className={`flex-1 flex flex-col items-center gap-1.5 py-3 rounded-lg text-xs font-bold transition-all ${activeTab === tab.id ? "bg-white/10 text-white shadow-lg" : "text-white/40 hover:text-white/60"
                                }`}
                        >
                            <tab.icon size={18} />
                            {tab.label}
                        </button>
                    ))}
                </div>

                {/* Tab Content */}
                <div className="flex-1 overflow-y-auto p-8">
                    <AnimatePresence mode="wait">
                        {activeTab === "design" && (
                            <motion.div
                                key="design"
                                initial={{ opacity: 0, x: -10 }}
                                animate={{ opacity: 1, x: 0 }}
                                exit={{ opacity: 0, x: 10 }}
                                className="space-y-8"
                            >
                                <div className="grid grid-cols-2 gap-6">
                                    <div className="col-span-2">
                                        <label className="block text-[10px] font-bold text-white/50 mb-2 uppercase tracking-widest">Bot Name</label>
                                        <input
                                            type="text"
                                            value={botName}
                                            onChange={(e) => setBotName(e.target.value)}
                                            className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-sm outline-none focus:border-blue-500 transition-colors"
                                        />
                                    </div>

                                    <div className="col-span-2 space-y-4">
                                        <div className="flex items-center justify-between">
                                            <label className="text-[10px] font-bold text-white/50 uppercase tracking-widest">Launcher Background</label>
                                            <button
                                                onClick={() => setShowLauncherBg(!showLauncherBg)}
                                                className={`w-10 h-5 rounded-full transition-colors relative ${showLauncherBg ? 'bg-blue-600' : 'bg-white/10'}`}
                                            >
                                                <div className={`absolute top-1 w-3 h-3 rounded-full bg-white transition-all ${showLauncherBg ? 'right-1' : 'left-1'}`} />
                                            </button>
                                        </div>

                                        <div className="space-y-2">
                                            <div className="flex justify-between">
                                                <label className="text-[10px] font-bold text-white/50 uppercase tracking-widest">Logo Size</label>
                                                <span className="text-[10px] text-white/30">{logoSize}px</span>
                                            </div>
                                            <input
                                                type="range" min="20" max="60" value={logoSize}
                                                onChange={(e) => setLogoSize(parseInt(e.target.value))}
                                                className="w-full h-1 bg-white/10 rounded-lg appearance-none cursor-pointer accent-blue-500"
                                            />
                                        </div>

                                        <div className="space-y-2">
                                            <div className="flex justify-between">
                                                <label className="text-[10px] font-bold text-white/50 uppercase tracking-widest">Side Padding</label>
                                                <span className="text-[10px] text-white/30">{rightPadding}px</span>
                                            </div>
                                            <input
                                                type="range" min="0" max="100" value={rightPadding}
                                                onChange={(e) => setRightPadding(parseInt(e.target.value))}
                                                className="w-full h-1 bg-white/10 rounded-lg appearance-none cursor-pointer accent-blue-500"
                                            />
                                        </div>

                                        <div className="space-y-2">
                                            <div className="flex justify-between">
                                                <label className="text-[10px] font-bold text-white/50 uppercase tracking-widest">Bottom Padding</label>
                                                <span className="text-[10px] text-white/30">{bottomPadding}px</span>
                                            </div>
                                            <input
                                                type="range" min="0" max="100" value={bottomPadding}
                                                onChange={(e) => setBottomPadding(parseInt(e.target.value))}
                                                className="w-full h-1 bg-white/10 rounded-lg appearance-none cursor-pointer accent-blue-500"
                                            />
                                        </div>
                                    </div>

                                    <div className="col-span-2">
                                        <label className="block text-[10px] font-bold text-white/50 mb-2 uppercase tracking-widest">Bot Logo</label>
                                        <div className="flex gap-3">
                                            <div className="flex-1 relative group">
                                                <input
                                                    type="text"
                                                    placeholder="https://example.com/logo.png"
                                                    value={botLogo}
                                                    onChange={(e) => setBotLogo(e.target.value)}
                                                    className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-sm outline-none focus:border-blue-500 transition-colors pr-12"
                                                />
                                                <button
                                                    onClick={() => fileInputRef.current?.click()}
                                                    disabled={logoLoading}
                                                    className="absolute right-2 top-1.5 p-1.5 bg-blue-500/20 text-blue-400 rounded-lg hover:bg-blue-500 hover:text-white transition-all disabled:opacity-50"
                                                    title="Upload Logo"
                                                >
                                                    {logoLoading ? (
                                                        <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                                                    ) : (
                                                        <Upload size={16} />
                                                    )}
                                                </button>
                                                <input
                                                    type="file"
                                                    ref={fileInputRef}
                                                    onChange={handleLogoUpload}
                                                    className="hidden"
                                                    accept="image/*"
                                                />
                                            </div>
                                            {botLogo && (
                                                <div className="w-10 h-10 bg-white/5 rounded-xl border border-white/10 flex items-center justify-center overflow-hidden shrink-0 relative">
                                                    <Image 
                                                        src={botLogo} 
                                                        alt="Logo Preview" 
                                                        fill 
                                                        className="object-cover" 
                                                        unoptimized={botLogo.startsWith('data:')}
                                                    />
                                                </div>
                                            )}
                                        </div>
                                    </div>

                                    <div>
                                        <label className="block text-[10px] font-bold text-white/50 mb-3 uppercase tracking-widest">Accent & Font</label>
                                        <div className="flex items-center gap-4">
                                            <div className="relative w-10 h-10 rounded-full border border-white/20 overflow-hidden cursor-pointer hover:scale-110 transition-transform flex-shrink-0 shadow-lg ring-2 ring-white/5">
                                                <input type="color" value={color} className="absolute inset-0 w-[200%] h-[200%] -top-1/2 -left-1/2 cursor-pointer" onChange={(e) => setColor(e.target.value)} />
                                            </div>
                                            <div className="flex-1 relative" ref={fontDropdownRef}>
                                                <button
                                                    onClick={() => setShowFontDropdown(!showFontDropdown)}
                                                    className="w-full bg-[#111] border border-white/10 rounded-xl px-3 py-2 text-xs flex items-center justify-between hover:border-blue-500 transition-colors text-white"
                                                >
                                                    <span className="truncate">
                                                        {FONT_OPTIONS.find(f => f.value === fontFamily)?.label || "Select Font"}
                                                    </span>
                                                    <ChevronDown size={14} className={`transition-transform grow-0 shrink-0 ${showFontDropdown ? 'rotate-180' : ''}`} />
                                                </button>

                                                <AnimatePresence>
                                                    {showFontDropdown && (
                                                        <motion.div
                                                            initial={{ opacity: 0, y: 10, scale: 0.95 }}
                                                            animate={{ opacity: 1, y: 0, scale: 1 }}
                                                            exit={{ opacity: 0, y: 10, scale: 0.95 }}
                                                            className="absolute bottom-full mb-2 left-0 w-64 bg-[#111] border border-white/10 rounded-2xl shadow-2xl z-[100] overflow-hidden flex flex-col"
                                                        >
                                                            <div className="p-2 border-b border-white/5">
                                                                <div className="relative">
                                                                    <Search size={12} className="absolute left-3 top-1/2 -translate-y-1/2 text-white/30" />
                                                                    <input
                                                                        autoFocus
                                                                        type="text"
                                                                        placeholder="Search fonts..."
                                                                        value={fontSearch}
                                                                        onChange={(e) => setFontSearch(e.target.value)}
                                                                        className="w-full bg-white/5 border border-white/5 rounded-lg pl-8 pr-8 py-1.5 text-[11px] outline-none focus:border-blue-500/50 transition-colors"
                                                                    />
                                                                    {fontSearch && (
                                                                        <button
                                                                            onClick={() => setFontSearch("")}
                                                                            className="absolute right-2 top-1/2 -translate-y-1/2 p-1 hover:bg-white/10 rounded"
                                                                        >
                                                                            <X size={10} className="text-white/40" />
                                                                        </button>
                                                                    )}
                                                                </div>
                                                            </div>
                                                            <div className="max-h-60 overflow-y-auto p-1 custom-scrollbar">
                                                                {FONT_OPTIONS.filter(f => f.label.toLowerCase().includes(fontSearch.toLowerCase())).map((font) => (
                                                                    <button
                                                                        key={font.value}
                                                                        onClick={() => {
                                                                            setFontFamily(font.value);
                                                                            setShowFontDropdown(false);
                                                                            setFontSearch("");
                                                                        }}
                                                                        className={`w-full text-left px-3 py-2 rounded-lg text-xs transition-colors flex items-center justify-between group ${fontFamily === font.value ? 'bg-blue-600 text-white' : 'hover:bg-white/5 text-white/70 hover:text-white'}`}
                                                                        style={{ fontFamily: font.value.includes("'") ? font.value : font.value }}
                                                                    >
                                                                        <span>{font.label}</span>
                                                                        {fontFamily === font.value && <Check size={12} />}
                                                                    </button>
                                                                ))}
                                                                {FONT_OPTIONS.filter(f => f.label.toLowerCase().includes(fontSearch.toLowerCase())).length === 0 && (
                                                                    <div className="px-3 py-4 text-center text-white/20 text-[10px] uppercase font-bold tracking-widest">
                                                                        No fonts found
                                                                    </div>
                                                                )}
                                                            </div>
                                                        </motion.div>
                                                    )}
                                                </AnimatePresence>
                                            </div>
                                        </div>
                                    </div>

                                    <div>
                                        <label className="block text-[10px] font-bold text-white/50 mb-3 uppercase tracking-widest">Position</label>
                                        <div className="flex bg-white/5 p-1 rounded-xl border border-white/10">
                                            <button
                                                onClick={() => setPosition("right")}
                                                className={`flex-1 py-1.5 rounded-lg text-[10px] font-bold transition-all ${position === "right" ? "bg-white/10 text-white shadow-sm" : "text-white/40 hover:text-white/60"}`}
                                            >
                                                Right
                                            </button>
                                            <button
                                                onClick={() => setPosition("left")}
                                                className={`flex-1 py-1.5 rounded-lg text-[10px] font-bold transition-all ${position === "left" ? "bg-white/10 text-white shadow-sm" : "text-white/40 hover:text-white/60"}`}
                                            >
                                                Left
                                            </button>
                                        </div>
                                    </div>

                                    <div className="col-span-2 grid grid-cols-2 gap-6">
                                        <div>
                                            <div className="flex justify-between items-center mb-2">
                                                <label className="block text-[10px] font-bold text-white/50 uppercase tracking-widest">Accent Height</label>
                                                <span className="text-[10px] text-blue-400 font-mono">{headerHeight}px</span>
                                            </div>
                                            <input
                                                type="range"
                                                min="60"
                                                max="120"
                                                value={headerHeight}
                                                onChange={(e) => setHeaderHeight(parseInt(e.target.value))}
                                                className="w-full accent-blue-500 h-1.5 bg-white/10 rounded-lg appearance-none cursor-pointer"
                                            />
                                        </div>
                                        <div>
                                            <div className="flex justify-between items-center mb-2">
                                                <label className="block text-[10px] font-bold text-white/50 uppercase tracking-widest">Radius</label>
                                                <span className="text-[10px] text-blue-400 font-mono">{borderRadius}px</span>
                                            </div>
                                            <input
                                                type="range"
                                                min="0"
                                                max="40"
                                                value={borderRadius}
                                                onChange={(e) => setBorderRadius(parseInt(e.target.value))}
                                                className="w-full accent-blue-500 h-1.5 bg-white/10 rounded-lg appearance-none cursor-pointer"
                                            />
                                        </div>
                                        <div className="col-span-2 space-y-4 pt-4 border-t border-white/5">
                                            <label className="block text-[10px] font-bold text-white/50 uppercase tracking-widest">Launcher Shape</label>
                                            <div className="grid grid-cols-4 gap-3">
                                                {[
                                                    { id: "circle", label: "Circle", radius: "50%" },
                                                    { id: "square", label: "Square", radius: "0" },
                                                    { id: "rounded", label: "Rounded", radius: "12px" },
                                                    { id: "oval", label: "Oval", radius: "20px / 12px", width: "w-10", height: "h-6" },
                                                    { id: "none", label: "None", radius: "0" }
                                                ].map((s) => (
                                                    <button
                                                        key={s.id}
                                                        onClick={() => setLauncherShape(s.id)}
                                                        className={`flex flex-col items-center gap-2 p-2 rounded-xl transition-all ${launcherShape === s.id ? "bg-blue-500/20 ring-1 ring-blue-500" : "bg-white/5 hover:bg-white/10"}`}
                                                    >
                                                        <div
                                                            className={`${s.width || "w-8"} ${s.height || "h-8"} ${s.id === 'none' ? 'bg-transparent border border-dashed border-white/20' : 'bg-blue-500 shadow-lg'}`}
                                                            style={{ borderRadius: s.radius }}
                                                        />
                                                        <span className="text-[9px] font-bold uppercase tracking-tighter opacity-50">{s.label}</span>
                                                    </button>
                                                ))}
                                            </div>

                                            <div className="flex items-center justify-between pt-2">
                                                <label className="block text-[10px] font-bold text-white/50 uppercase tracking-widest">Bubble Tail</label>
                                                <button
                                                    onClick={() => setShowTail(!showTail)}
                                                    className={`w-10 h-5 rounded-full transition-colors relative ${showTail ? "bg-blue-500" : "bg-white/10"}`}
                                                >
                                                    <div className={`absolute top-1 w-3 h-3 bg-white rounded-full transition-all ${showTail ? "left-6" : "left-1"}`} />
                                                </button>
                                            </div>
                                        </div>
                                    </div>
                                </div>

                                <div className="p-4 bg-white/5 rounded-2xl border border-white/10 space-y-6">
                                    <div className="space-y-4">
                                        <div>
                                            <label className="block text-[10px] font-bold text-white/50 mb-3 uppercase tracking-widest">Chat Background Image</label>
                                            <div className="flex gap-2">
                                                <div className="relative flex-1">
                                                    <input
                                                        type="text"
                                                        placeholder="https://example.com/bg.png"
                                                        value={backgroundImage}
                                                        onChange={(e) => setBackgroundImage(e.target.value)}
                                                        className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2 text-xs outline-none focus:border-blue-500 transition-colors"
                                                    />
                                                </div>
                                                <button
                                                    onClick={() => {
                                                        const input = document.createElement('input');
                                                        input.type = 'file';
                                                        input.accept = 'image/*';
                                                        input.onchange = async (e: any) => {
                                                            const file = e.target.files?.[0];
                                                            if (file) {
                                                                setLogoLoading(true);
                                                                const formData = new FormData();
                                                                formData.append("file", file);
                                                                try {
                                                                    const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/bots/${id}/logo`, {
                                                                        method: "POST",
                                                                        body: formData,
                                                                    });
                                                                    const data = await res.json();
                                                                    if (res.ok && data.logo_url) setBackgroundImage(data.logo_url);
                                                                } catch (err) {
                                                                    console.error("Upload failed", err);
                                                                } finally {
                                                                    setLogoLoading(false);
                                                                }
                                                            }
                                                        };
                                                        input.click();
                                                    }}
                                                    className="p-2 bg-white/5 border border-white/10 rounded-xl hover:bg-white/10 transition-colors"
                                                    title="Upload Background"
                                                >
                                                    <Upload size={14} />
                                                </button>
                                            </div>
                                        </div>
                                        <div>
                                            <div className="flex justify-between items-center mb-2">
                                                <label className="block text-[10px] font-bold text-white/50 uppercase tracking-widest">Background Opacity</label>
                                                <span className="text-[10px] text-blue-400 font-mono">{Math.round(backgroundOpacity * 100)}%</span>
                                            </div>
                                            <input
                                                type="range"
                                                min="0"
                                                max="1"
                                                step="0.01"
                                                value={backgroundOpacity}
                                                onChange={(e) => setBackgroundOpacity(parseFloat(e.target.value))}
                                                className="w-full accent-blue-500 h-1.5 bg-white/10 rounded-lg appearance-none cursor-pointer"
                                            />
                                        </div>
                                    </div>

                                    <div className="pt-4 border-t border-white/5 grid grid-cols-4 gap-4">
                                        {[
                                            { label: "Header", value: textColor, setter: setTextColor },
                                            { label: "Chat BG", value: chatBgColor, setter: setChatBgColor },
                                            { label: "Input BG", value: inputBgColor, setter: setInputBgColor },
                                            { label: "Input Txt", value: inputTextColor, setter: setInputTextColor }
                                        ].map((item, idx) => (
                                            <div key={idx} className="flex flex-col items-center gap-2">
                                                <span className="text-[9px] font-bold text-white/30 uppercase tracking-tighter whitespace-nowrap">{item.label}</span>
                                                <div className="relative w-8 h-8 rounded-full border border-white/20 overflow-hidden cursor-pointer hover:scale-110 transition-transform shadow-sm">
                                                    <input type="color" value={item.value} className="absolute inset-0 w-[200%] h-[200%] -top-1/2 -left-1/2 cursor-pointer" onChange={(e) => item.setter(e.target.value)} />
                                                </div>
                                            </div>
                                        ))}
                                    </div>

                                    <div className="space-y-4 pt-4 border-t border-white/5">
                                        <div className="flex items-center justify-between">
                                            <span className="text-[10px] font-bold text-blue-400 uppercase tracking-widest">User Bubble</span>
                                            <div className="flex gap-4">
                                                <div className="flex items-center gap-2">
                                                    <span className="text-[9px] text-white/30 uppercase">BG</span>
                                                    <div className="relative w-6 h-6 rounded-full border border-white/20 overflow-hidden cursor-pointer hover:scale-110 transition-transform">
                                                        <input type="color" value={userBubbleBg} className="absolute inset-0 w-[200%] h-[200%] -top-1/2 -left-1/2 cursor-pointer" onChange={(e) => setUserBubbleBg(e.target.value)} />
                                                    </div>
                                                </div>
                                                <div className="flex items-center gap-2">
                                                    <span className="text-[9px] text-white/30 uppercase">Txt</span>
                                                    <div className="relative w-6 h-6 rounded-full border border-white/20 overflow-hidden cursor-pointer hover:scale-110 transition-transform">
                                                        <input type="color" value={userBubbleText} className="absolute inset-0 w-[200%] h-[200%] -top-1/2 -left-1/2 cursor-pointer" onChange={(e) => setUserBubbleText(e.target.value)} />
                                                    </div>
                                                </div>
                                            </div>
                                        </div>

                                        <div className="flex items-center justify-between">
                                            <span className="text-[10px] font-bold text-purple-400 uppercase tracking-widest">Bot Bubble</span>
                                            <div className="flex gap-4">
                                                <div className="flex items-center gap-2">
                                                    <span className="text-[9px] text-white/30 uppercase">BG</span>
                                                    <div className="relative w-6 h-6 rounded-full border border-white/20 overflow-hidden cursor-pointer hover:scale-110 transition-transform">
                                                        <input type="color" value={assistantBubbleBg} className="absolute inset-0 w-[200%] h-[200%] -top-1/2 -left-1/2 cursor-pointer" onChange={(e) => setAssistantBubbleBg(e.target.value)} />
                                                    </div>
                                                </div>
                                                <div className="flex items-center gap-2">
                                                    <span className="text-[9px] text-white/30 uppercase">Txt</span>
                                                    <div className="relative w-6 h-6 rounded-full border border-white/20 overflow-hidden cursor-pointer hover:scale-110 transition-transform">
                                                        <input type="color" value={assistantBubbleText} className="absolute inset-0 w-[200%] h-[200%] -top-1/2 -left-1/2 cursor-pointer" onChange={(e) => setAssistantBubbleText(e.target.value)} />
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </motion.div>
                        )}

                        {activeTab === "knowledge" && (
                            <motion.div key="knowledge" className="space-y-6">
                                <div className="p-6 bg-white/5 border border-white/10 rounded-3xl space-y-6">
                                    <div className="flex items-center gap-3 mb-2">
                                        <div className="p-2 bg-blue-500/10 rounded-lg">
                                            <Brain size={20} className="text-blue-400" />
                                        </div>
                                        <div>
                                            <h3 className="text-sm font-bold">AI Model & Provider</h3>
                                            <p className="text-[10px] text-white/40 uppercase tracking-widest font-bold">Configure your brain</p>
                                        </div>
                                    </div>

                                    <div className="grid grid-cols-2 gap-4">
                                        <div className="space-y-2">
                                            <label className="text-[10px] font-bold text-white/50 uppercase tracking-widest">Provider</label>
                                            <select
                                                value={aiProvider}
                                                onChange={(e) => {
                                                    const p = e.target.value;
                                                    setAiProvider(p);
                                                    if (p === "google") setAiModel("gemini-2.0-flash");
                                                    if (p === "openai") setAiModel("gpt-4o-mini");
                                                    if (p === "groq") setAiModel("llama3-8b-8192");
                                                }}
                                                className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-xs outline-none focus:border-blue-500 transition-colors"
                                            >
                                                <option value="google" className="bg-[#111]">Google (Gemini)</option>
                                                <option value="openai" className="bg-[#111]">OpenAI (ChatGPT)</option>
                                                <option value="groq" className="bg-[#111]">Llama 3 (via Groq)</option>
                                            </select>
                                        </div>

                                        <div className="space-y-2">
                                            <label className="text-[10px] font-bold text-white/50 uppercase tracking-widest">Model</label>
                                            <select
                                                value={aiModel}
                                                onChange={(e) => setAiModel(e.target.value)}
                                                className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-xs outline-none focus:border-blue-500 transition-colors"
                                            >
                                                {aiProvider === "google" && (
                                                    <>
                                                        <option value="gemini-2.0-flash" className="bg-[#111]">Gemini 2.0 Flash (Latest / Free)</option>
                                                        <option value="gemini-2.0-flash-lite" className="bg-[#111]">Gemini 2.0 Flash Lite (Fastest / Free)</option>
                                                        <option value="gemini-1.5-flash" className="bg-[#111]">Gemini 1.5 Flash (Free Tier)</option>
                                                        <option value="gemini-1.5-flash-8b" className="bg-[#111]">Gemini 1.5 Flash-8B (Fast / Free)</option>
                                                        <option value="gemini-1.5-pro" className="bg-[#111]">Gemini 1.5 Pro (Advanced)</option>
                                                    </>
                                                )}
                                                {aiProvider === "openai" && (
                                                    <>
                                                        <option value="gpt-4o-mini" className="bg-[#111]">GPT-4o Mini (Best Value / "Free")</option>
                                                        <option value="gpt-4o" className="bg-[#111]">GPT-4o (SOTA)</option>
                                                        <option value="gpt-4-turbo" className="bg-[#111]">GPT-4 Turbo</option>
                                                        <option value="gpt-3.5-turbo" className="bg-[#111]">GPT-3.5 Turbo</option>
                                                    </>
                                                )}
                                                {aiProvider === "groq" && (
                                                    <>
                                                        <option value="llama-3.3-70b-versatile" className="bg-[#111]">Llama 3.3 70B (Latest)</option>
                                                        <option value="llama-3.1-8b-instant" className="bg-[#111]">Llama 3.1 8B (Fast / Free Beta)</option>
                                                        <option value="llama-3.2-11b-vision-preview" className="bg-[#111]">Llama 3.2 11B (Vision / Free Beta)</option>
                                                        <option value="mixtral-8x7b-32768" className="bg-[#111]">Mixtral 8x7B</option>
                                                    </>
                                                )}
                                            </select>
                                        </div>

                                        <div className="col-span-2 space-y-2">
                                            <div className="flex justify-between items-center">
                                                <label className="text-[10px] font-bold text-white/50 uppercase tracking-widest">API Key (Leave blank to use system default)</label>
                                                {aiApiKey && <Check size={12} className="text-green-500" />}
                                            </div>
                                            <input
                                                type="password"
                                                value={aiApiKey}
                                                onChange={(e) => setAiApiKey(e.target.value)}
                                                placeholder={`Enter your ${aiProvider.toUpperCase()} API Key`}
                                                className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-xs outline-none focus:border-blue-500 transition-colors"
                                            />
                                        </div>
                                    </div>
                                </div>

                                <div className="space-y-4">
                                    <div className="p-5 bg-white/5 border border-white/10 rounded-3xl space-y-4">
                                        <div className="flex items-center gap-2">
                                            <Globe size={16} className="text-blue-400" />
                                            <h4 className="text-xs font-bold uppercase tracking-widest text-white/70">Website Crawler</h4>
                                        </div>
                                        <div className="space-y-2">
                                            <input
                                                type="text"
                                                placeholder="https://example.com"
                                                value={crawlUrl}
                                                onChange={(e) => setCrawlUrl(e.target.value)}
                                                className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-xs outline-none focus:border-blue-500"
                                            />
                                            <button
                                                onClick={handleCrawl}
                                                disabled={crawling}
                                                className="w-full py-2.5 bg-blue-600 rounded-xl text-xs font-bold hover:bg-blue-500 disabled:opacity-50 transition-all"
                                            >
                                                {crawling ? "Crawling..." : "Start Crawling"}
                                            </button>
                                        </div>
                                        <p className="text-[10px] text-white/30 leading-relaxed">Enter a URL to ingest its text content into the knowledge base.</p>
                                    </div>

                                    <div className="p-5 bg-white/5 border border-white/10 rounded-3xl space-y-4">
                                        <div className="flex items-center gap-2">
                                            <Video size={16} className="text-red-400" />
                                            <h4 className="text-xs font-bold uppercase tracking-widest text-white/70">YouTube Extract</h4>
                                        </div>
                                        <div className="space-y-2">
                                            <input
                                                type="text"
                                                placeholder="YouTube Video URL"
                                                value={youtubeUrl}
                                                onChange={(e) => setYoutubeUrl(e.target.value)}
                                                className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-xs outline-none focus:border-red-500"
                                            />
                                            <button
                                                onClick={handleYouTubeExtract}
                                                disabled={crawling}
                                                className="w-full py-2.5 bg-red-600 rounded-xl text-xs font-bold hover:bg-red-500 disabled:opacity-50 transition-all"
                                            >
                                                {crawling ? "Extracting..." : "Extract Transcript"}
                                            </button>
                                        </div>
                                        <p className="text-[10px] text-white/30 leading-relaxed">Extract transcripts from videos to teach your bot.</p>
                                    </div>
                                </div>

                                <div className="flex items-center justify-between p-5 bg-gradient-to-r from-blue-600/10 to-purple-600/10 border border-white/10 rounded-3xl">
                                    <div className="flex items-center gap-4">
                                        <div className="w-10 h-10 bg-white/5 rounded-2xl flex items-center justify-center">
                                            <Search size={20} className="text-blue-400" />
                                        </div>
                                        <div>
                                            <h4 className="font-bold text-sm">Live Web Search (RAG)</h4>
                                            <p className="text-xs text-white/40">Real-time search via Tavily & Perplexity</p>
                                        </div>
                                    </div>
                                    <button
                                        onClick={() => setLiveSearchEnabled(!liveSearchEnabled)}
                                        className={`w-12 h-6 rounded-full transition-all relative ${liveSearchEnabled ? 'bg-blue-600' : 'bg-white/10'}`}
                                    >
                                        <div className={`absolute top-1 w-4 h-4 rounded-full bg-white transition-all ${liveSearchEnabled ? 'right-1' : 'left-1'}`} />
                                    </button>
                                </div>

                                <div
                                    onClick={() => !knowledgeLoading && knowledgeInputRef.current?.click()}
                                    className={`border-2 border-dashed rounded-3xl p-8 text-center transition-all cursor-pointer group ${knowledgeLoading ? 'border-blue-500 bg-blue-500/5' : 'border-white/10 hover:border-blue-500/50 hover:bg-blue-500/5'}`}
                                >
                                    {knowledgeLoading ? (
                                        <div className="flex flex-col items-center">
                                            <div className="w-12 h-12 border-4 border-blue-500/20 border-t-blue-500 rounded-full animate-spin mb-4" />
                                            <p className="font-bold text-lg text-blue-400">Processing Knowledge...</p>
                                        </div>
                                    ) : (
                                        <>
                                            <Upload className="mx-auto mb-4 text-white/20 group-hover:text-blue-500 transition-colors" size={48} />
                                            <p className="font-bold text-lg mb-1">Upload PDF or TXT</p>
                                            <p className="text-white/40 text-sm">Bot will learn from the content of these files</p>
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

                                <div className="space-y-3">
                                    <h4 className="text-xs font-bold text-white/40 uppercase tracking-widest flex justify-between">
                                        Manual Knowledge Base
                                        <span className="text-[10px] text-blue-400 font-mono">{knowledgeBase.length} chars</span>
                                    </h4>
                                    <textarea
                                        rows={10}
                                        value={knowledgeBase}
                                        onChange={(e) => setKnowledgeBase(e.target.value)}
                                        placeholder="Type custom information here (e.g. company details, pricing, FAQs)..."
                                        className="w-full bg-white/5 border border-white/10 rounded-2xl px-4 py-4 outline-none focus:border-blue-500 transition-all resize-none text-sm leading-relaxed"
                                    />
                                    <p className="text-[10px] text-white/30 italic">
                                        The bot will prioritize this information when answering user questions.
                                    </p>
                                </div>
                            </motion.div>
                        )}

                        {activeTab === "personality" && (
                            <motion.div key="personality" className="space-y-6">
                                <div>
                                    <label className="block text-sm font-bold text-white/50 mb-3 uppercase tracking-wider">System Instruction</label>
                                    <textarea
                                        rows={6}
                                        value={systemPrompt}
                                        onChange={(e) => setSystemPrompt(e.target.value)}
                                        placeholder="e.g. You are a sassy assistant who loves puns..."
                                        className="w-full bg-white/5 border border-white/10 rounded-2xl px-4 py-4 outline-none focus:border-blue-500 transition-all resize-none"
                                    />
                                    <p className="text-[11px] text-white/30 mt-3 leading-relaxed">
                                        This defines how the AI behaves. Be specific about tone, level of detail, and constraints.
                                    </p>
                                </div>
                                <div className="p-5 bg-white/5 rounded-2xl border border-white/5">
                                    <h5 className="font-bold text-sm mb-2">Preset Moods</h5>
                                    <div className="flex flex-wrap gap-2">
                                        {["Professional", "Friendly", "Concise", "Sassy", "Expert"].map(m => (
                                            <button
                                                key={m}
                                                onClick={() => setSystemPrompt(`You are a ${m.toLowerCase()} assistant.`)}
                                                className="px-3 py-1.5 bg-white/5 rounded-full text-xs hover:bg-white/10"
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
                                <div className="flex justify-between items-center bg-white/5 p-6 rounded-3xl border border-white/10">
                                    <div>
                                        <h3 className="font-bold text-lg">Lead Storage</h3>
                                        <p className="text-white/40 text-xs">Capture data from your chatbot flows</p>
                                    </div>
                                    <div className="bg-blue-600/20 text-blue-400 px-4 py-2 rounded-xl text-sm font-bold flex items-center gap-2">
                                        <Inbox size={16} /> {leads.length} Leads
                                    </div>
                                </div>

                                <div className="bg-white/5 border border-white/10 rounded-3xl overflow-hidden min-h-[400px]">
                                    {leadsLoading ? (
                                        <div className="flex flex-col items-center justify-center h-[400px]">
                                            <div className="w-8 h-8 border-2 border-blue-500/20 border-t-blue-500 rounded-full animate-spin mb-4" />
                                            <p className="text-white/40 text-xs uppercase font-bold tracking-widest">Loading Leads...</p>
                                        </div>
                                    ) : leads.length === 0 ? (
                                        <div className="flex flex-col items-center justify-center h-[400px] text-center p-8">
                                            <div className="w-16 h-16 bg-white/5 rounded-2xl flex items-center justify-center mb-4">
                                                <List size={32} className="text-white/20" />
                                            </div>
                                            <h4 className="font-bold mb-2">No Leads Yet</h4>
                                            <p className="text-white/30 text-xs max-w-[250px] leading-relaxed">
                                                When users complete forms in your bot flow, their data will appear here.
                                            </p>
                                        </div>
                                    ) : (
                                        <div className="overflow-x-auto">
                                            <table className="w-full text-left border-collapse">
                                                <thead>
                                                    <tr className="border-b border-white/10 bg-white/5">
                                                        <th className="px-6 py-4 text-[10px] font-bold text-white/40 uppercase tracking-widest">Date</th>
                                                        <th className="px-6 py-4 text-[10px] font-bold text-white/40 uppercase tracking-widest">Captured Data</th>
                                                        <th className="px-6 py-4 text-[10px] font-bold text-white/40 uppercase tracking-widest text-right">Session</th>
                                                    </tr>
                                                </thead>
                                                <tbody className="divide-y divide-white/5">
                                                    {leads.map((lead) => (
                                                        <tr key={lead.id} className="hover:bg-white/5 transition-colors group">
                                                            <td className="px-6 py-4">
                                                                <p className="text-[10px] text-white/40 font-mono">
                                                                    {new Date(lead.created_at).toLocaleDateString()}
                                                                </p>
                                                                <p className="text-xs font-bold text-white/80">
                                                                    {new Date(lead.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                                                                </p>
                                                            </td>
                                                            <td className="px-6 py-4">
                                                                <div className="flex flex-wrap gap-2">
                                                                    {Object.entries(lead.data).map(([key, value]: [string, any]) => (
                                                                        <div key={key} className="bg-white/5 border border-white/10 rounded-lg px-2 py-1 flex items-center gap-2">
                                                                            <span className="text-[9px] font-bold text-blue-400 uppercase">{key}:</span>
                                                                            <span className="text-xs text-white/70">{value}</span>
                                                                        </div>
                                                                    ))}
                                                                </div>
                                                            </td>
                                                            <td className="px-6 py-4 text-right">
                                                                <span className="text-[10px] font-mono text-white/20 group-hover:text-white/40 transition-colors">
                                                                    {lead.session_id.slice(0, 8)}...
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
                </div >
            </aside >

            {/* Main Preview Area */}
            <main className="flex-1 bg-[#0a0a0a] relative flex items-center justify-center p-12 overflow-hidden">
                {/* Abstract Background for Preview */}
                <div className="absolute inset-0 z-0">
                    <div className="absolute top-1/4 left-1/4 w-[500px] h-[500px] bg-blue-600/10 blur-[150px] rounded-full" />
                    <div className="absolute bottom-1/4 right-1/4 w-[400px] h-[400px] bg-purple-600/5 blur-[120px] rounded-full" />
                </div>

                <div className="relative z-10 w-full h-full flex flex-col items-center justify-center">
                    <div className="flex bg-white/5 p-1 rounded-full mb-8 border border-white/10">
                        <button className="px-4 py-1.5 bg-white/10 rounded-full text-xs font-bold flex items-center gap-2">
                            <Monitor size={14} /> Desktop
                        </button>
                        <button className="px-4 py-1.5 text-white/30 text-xs font-bold flex items-center gap-2">
                            <Smartphone size={14} /> Mobile
                        </button>
                    </div>

                    {/* Widget Mockup */}
                    <div
                        className="w-[380px] h-[600px] bg-zinc-900 border-[8px] border-zinc-800 shadow-2xl flex flex-col overflow-hidden"
                        style={{ fontFamily: fontFamily, borderRadius: `${borderRadius * 1.5}px` }}
                    >
                        <div
                            className="p-6 font-bold flex items-center justify-between shrink-0"
                            style={{ backgroundColor: color, color: textColor, height: `${headerHeight}px` }}
                        >
                            <div className="flex items-center gap-3">
                                <div className="w-10 h-10 bg-white/20 rounded-xl flex items-center justify-center overflow-hidden">
                                    {botLogo ? (
                                        <img src={botLogo} alt="Bot" className="w-full h-full object-cover" />
                                    ) : (
                                        <Bot size={20} />
                                    )}
                                </div>
                                <span>{botName}</span>
                            </div>
                        </div>
                        <div className="flex-1 p-6 space-y-4 overflow-y-auto relative" style={{ backgroundColor: chatBgColor }}>
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
                            <div className="relative z-10 space-y-4 flex flex-col">
                                <div
                                    className="p-4 rounded-tl-none text-xs leading-relaxed max-w-[85%]"
                                    style={{ backgroundColor: assistantBubbleBg, color: assistantBubbleText, borderRadius: `${borderRadius}px` }}
                                >
                                    Hello! I'm trained on your company data. How can I help you today?
                                </div>
                                <div
                                    className="p-4 rounded-tr-none text-xs leading-relaxed max-w-[80%] self-end"
                                    style={{ backgroundColor: userBubbleBg, color: userBubbleText, borderRadius: `${borderRadius}px` }}
                                >
                                    What's the return policy?
                                </div>
                            </div>
                        </div>
                        <div className="p-4 bg-zinc-800/50 border-t border-white/5 flex gap-2">
                            <div
                                className="flex-1 rounded-xl border border-white/10 h-12 flex items-center px-4 text-sm"
                                style={{ backgroundColor: inputBgColor, color: inputTextColor }}
                            >
                                Type your message...
                            </div>
                            <button
                                className="w-12 h-12 rounded-xl flex items-center justify-center"
                                style={{ backgroundColor: color, color: textColor }}
                            >
                                <Send size={18} />
                            </button>
                        </div>
                    </div>

                    <div
                        className="fixed flex flex-col items-center justify-center pointer-events-none"
                        style={{
                            bottom: `${bottomPadding + 20}px`,
                            right: position === 'right' ? `${rightPadding + 20}px` : 'auto',
                            left: position === 'left' ? `${rightPadding + 20}px` : 'auto',
                            zIndex: 50
                        }}
                    >
                        <div
                            className="w-16 h-16 shadow-2xl flex items-center justify-center transition-all duration-300 relative"
                            style={{
                                backgroundColor: (showLauncherBg && launcherShape !== 'none') ? color : 'transparent',
                                borderRadius: launcherShape === 'square' ? '0' :
                                    launcherShape === 'rounded' ? '12px' :
                                        launcherShape === 'oval' ? '40px' : '50%',
                                width: launcherShape === 'oval' ? '80px' : '64px',
                                boxShadow: (showLauncherBg && launcherShape !== 'none') ? '0 4px 12px rgba(0,0,0,0.15)' : 'none'
                            }}
                        >
                            {botLogo ? (
                                <img src={botLogo} alt="Launcher" style={{ width: `${logoSize}px`, height: `${logoSize}px`, objectFit: 'contain' }} />
                            ) : (
                                <MessageSquare size={30} className="text-white" />
                            )}
                            {showTail && (
                                <div
                                    className="absolute -bottom-2 rotate-[-15deg]"
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
                        <p className="mt-8 text-white/20 text-[10px] uppercase tracking-[0.2em]">Launcher Preview</p>
                    </div>

                    <p className="mt-8 text-white/20 text-xs uppercase tracking-[0.2em]">Real-time Component Preview</p>
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
        </div >
    );
}

export default function Builder(props: any) {
    return (
        <Suspense fallback={<div className="h-screen bg-black flex items-center justify-center text-white">Loading...</div>}>
            <BuilderContent {...props} />
        </Suspense>
    );
}
