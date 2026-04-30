import os

filepath = os.path.join(os.path.dirname(__file__), "src", "app", "dashboard", "builder", "[id]", "page.tsx")

with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

# Color replacements: blue -> purple (#9d55ac)
replacements = [
    # Backgrounds
    ("bg-blue-600", "bg-[#9d55ac]"),
    ("bg-blue-500", "bg-[#b06abf]"),
    ("bg-blue-700", "bg-[#8a4a97]"),
    ("bg-blue-400", "bg-[#c080cc]"),
    ("bg-blue-100", "bg-[#f0e0f4]"),
    ("bg-blue-50", "bg-[#f8f0fa]"),
    # Hover backgrounds
    ("hover:bg-blue-700", "hover:bg-[#8a4a97]"),
    ("hover:bg-blue-600", "hover:bg-[#9d55ac]"),
    ("hover:bg-blue-500", "hover:bg-[#b06abf]"),
    # Text colors
    ("text-blue-600", "text-[#9d55ac]"),
    ("text-blue-700", "text-[#8a4a97]"),
    ("text-blue-500", "text-[#b06abf]"),
    ("text-blue-400", "text-[#c080cc]"),
    # Hover text
    ("hover:text-blue-600", "hover:text-[#9d55ac]"),
    ("hover:text-blue-500", "hover:text-[#b06abf]"),
    # Borders
    ("border-blue-500", "border-[#b06abf]"),
    ("border-blue-400", "border-[#c080cc]"),
    ("border-blue-200", "border-[#e0c8e6]"),
    ("border-blue-100", "border-[#f0e0f4]"),
    ("border-t-blue-600", "border-t-[#9d55ac]"),
    ("border-t-blue-500", "border-t-[#b06abf]"),
    # Hover borders
    ("hover:border-blue-400", "hover:border-[#c080cc]"),
    ("hover:border-blue-500", "hover:border-[#b06abf]"),
    # Focus rings
    ("ring-blue-500", "ring-[#b06abf]"),
    ("ring-blue-600", "ring-[#9d55ac]"),
    # Shadows
    ("shadow-blue-500", "shadow-[#b06abf]"),
    ("shadow-blue-600", "shadow-[#9d55ac]"),
    # Accents
    ("accent-blue-600", "accent-[#9d55ac]"),
    # Gradients
    ("from-blue-50", "from-[#f8f0fa]"),
    ("from-blue-600", "from-[#9d55ac]"),
    # RGBA shadows  
    ("rgba(37,99,235", "rgba(157,85,172"),
    # Focus states
    ("focus:border-blue-500", "focus:border-[#b06abf]"),
    ("focus:border-blue-400", "focus:border-[#c080cc]"),
    ("focus:ring-blue-500", "focus:ring-[#b06abf]"),
    # Preview area bg blurs
    ("bg-blue-600/5", "bg-purple-600/5"),
]

for old, new in replacements:
    content = content.replace(old, new)

# Also replace the default model
content = content.replace(
    'const [aiModel, setAiModel] = useState("gemini-2.0-flash")',
    'const [aiModel, setAiModel] = useState("gemini-3-flash-preview")'
)
content = content.replace(
    'setAiModel(data.ai_model || "gemini-2.0-flash")',
    'setAiModel(data.ai_model || "gemini-3-flash-preview")'
)
content = content.replace(
    'aiModel: data.ai_model || "gemini-2.0-flash"',
    'aiModel: data.ai_model || "gemini-3-flash-preview"'
)
# Reorder dropdown options
content = content.replace(
    '<option value="gemini-2.0-flash">Gemini 2.0 Flash</option>\r\n                                                        <option value="gemini-3-flash-preview">gemini-3-flash-preview</option>',
    '<option value="gemini-3-flash-preview">Gemini 3 Flash Preview</option>\r\n                                                        <option value="gemini-2.0-flash">Gemini 2.0 Flash</option>'
)

# Desktop preview scaling changes
# 1. Add previewContainerRef and previewScale state
content = content.replace(
    '    const [previewMode, setPreviewMode] = useState<\'desktop\' | \'mobile\'>(\'mobile\');\r\n    const router = useRouter();\r\n',
    '    const [previewMode, setPreviewMode] = useState<\'desktop\' | \'mobile\'>(\'mobile\');\r\n    const router = useRouter();\r\n    const previewContainerRef = useRef<HTMLDivElement>(null);\r\n    const [previewScale, setPreviewScale] = useState(1);\r\n\r\n    // Dynamically calculate scale for desktop preview\r\n    useEffect(() => {\r\n        if (previewMode !== \'desktop\' || !previewContainerRef.current) return;\r\n        const container = previewContainerRef.current;\r\n        const calculateScale = () => {\r\n            const availableWidth = container.clientWidth - 32;\r\n            const availableHeight = container.clientHeight - 120;\r\n            const scaleX = Math.min(availableWidth / 900, 1);\r\n            const scaleY = Math.min(availableHeight / 562, 1);\r\n            setPreviewScale(Math.min(scaleX, scaleY, 1));\r\n        };\r\n        calculateScale();\r\n        const observer = new ResizeObserver(calculateScale);\r\n        observer.observe(container);\r\n        return () => observer.disconnect();\r\n    }, [previewMode]);\r\n\r\n'
)

# 2. Add ref to preview container
content = content.replace(
    '<div className="relative z-10 w-full h-full flex flex-col items-center justify-center">',
    '<div ref={previewContainerRef} className="relative z-10 w-full h-full flex flex-col items-center justify-center">'
)

# 3. Replace desktop preview with scaling wrapper
old_desktop = '''                    {previewMode === 'desktop' ? (
                        <div className="w-full max-w-[1200px] aspect-video bg-white rounded-2xl overflow-hidden shadow-2xl border border-slate-200 relative flex flex-col transition-all duration-500 animate-in fade-in zoom-in-95">
                            <div className="h-10 bg-slate-100 border-b border-slate-200 flex items-center px-4 gap-2 shrink-0">'''

new_desktop = '''                    {previewMode === 'desktop' ? (
                        <div className="w-full flex items-center justify-center" style={{ maxHeight: 'calc(100vh - 200px)' }}>
                            <div className="origin-center transition-transform duration-300" style={{ transform: `scale(${previewScale})` }}>
                                <div
                                    className="bg-white rounded-2xl overflow-hidden shadow-2xl border border-slate-200 relative flex flex-col transition-all duration-500 animate-in fade-in zoom-in-95"
                                    style={{ width: '900px', height: '562px' }}
                                >
                            <div className="h-10 bg-slate-100 border-b border-slate-200 flex items-center px-4 gap-2 shrink-0">'''

content = content.replace(old_desktop, new_desktop)

# 4. Fix chat widget size and closing divs
content = content.replace(
    "                                        width: '350px',\r\n                                        height: '500px',\r\n                                        bottom: `${bottomPadding + 80}px`,",
    "                                        width: '300px',\r\n                                        height: '350px',\r\n                                        bottom: `${bottomPadding + 70}px`,"
)

# 5. Fix closing divs for the desktop preview wrapper
old_close = '''                                    </LauncherPreview>
                                </div>
                            </div>
                        </div>'''
new_close = '''                                    </LauncherPreview>
                                </div>
                            </div>
                                </div>
                            </div>
                        </div>'''
content = content.replace(old_close, new_close)

# 6. Add Nimmi AI logo to header
old_header = '''                    <div className="flex items-center gap-1.5 font-bold uppercase text-[10px] tracking-widest text-slate-400 truncate">
                        Bot Builder <span className="text-slate-900 font-black">#{id.slice(0, 8)}</span>
                    </div>'''

new_header = '''                    <div className="flex items-center gap-3">
                        <Image src="/nimmi-logo-new.png" alt="Nimmi AI" width={36} height={36} className="rounded-lg" />
                        <div className="flex items-center gap-1.5 font-bold uppercase text-[10px] tracking-widest text-slate-400 truncate">
                            Bot Builder <span className="text-[#9d55ac] font-black">#{id.slice(0, 8)}</span>
                        </div>
                    </div>'''

content = content.replace(old_header, new_header)

with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)

print("Done! All changes applied successfully.")
