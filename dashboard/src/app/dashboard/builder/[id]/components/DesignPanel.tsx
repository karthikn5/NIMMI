"use client";

import { useRef, useState } from "react";
import { ImageIcon, Upload } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { Button, Input, PhraseInput, Segmented, Select, Textarea, cn, useToast } from "@/components/ui";
import { ChoiceRow, ColorField, Field, RangeField, Section, ToggleRow } from "./controls";
import { FONTS, THEMES, assetUrl, themeMatches, type Visual } from "./design";

// What the server accepts (it checks the file itself). An SVG is stored as a cleaned copy: no scripts or links.
const IMAGE_TYPES = "image/png,image/jpeg,image/webp,image/gif,image/svg+xml,.svg";

type Props = {
    botId: string;
    visual: Visual;
    set: (patch: Partial<Visual>) => void;
    botName: string;
    setBotName: (v: string) => void;
};

export default function DesignPanel({ botId, visual: v, set, botName, setBotName }: Props) {
    const toast = useToast();
    const logoInput = useRef<HTMLInputElement>(null);
    const bgInput = useRef<HTMLInputElement>(null);
    const [uploading, setUploading] = useState<"logo" | "background" | null>(null);

    const upload = async (kind: "logo" | "background", file: File | undefined) => {
        if (!file) return;
        const svg = file.type === "image/svg+xml" || /\.svg$/i.test(file.name);
        if (svg && file.size > 1024 * 1024) return toast("SVG images up to 1 MB, please.");
        if (file.size > 5 * 1024 * 1024) return toast("Images up to 5 MB, please.");
        setUploading(kind);
        const form = new FormData();
        form.append("file", file);
        try {
            const res = await apiFetch(`/api/bots/${botId}/${kind}`, { method: "POST", body: form });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(data.detail || "Upload failed");
            if (kind === "logo") set({ logo_url: assetUrl(data.logo_url) });
            else set({ background_image: data.bg_url });
        } catch (e) {
            toast((e as Error).message || "Upload failed. Try another image.");
        } finally {
            setUploading(null);
        }
    };

    const fontKnown = FONTS.some((f) => f.value === v.font_family);

    return (
        <div>
            <Section title="Theme" description="Start from a palette, then fine-tune any colour below.">
                <div className="grid grid-cols-3 gap-2">
                    {THEMES.map((t) => {
                        const active = themeMatches(v, t.palette);
                        const p = t.palette;
                        return (
                            <button key={t.id} type="button" onClick={() => set(p)} aria-pressed={active}
                                    className={cn("rounded-md border p-1.5 text-left transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-plum",
                                                  active ? "border-plum ring-1 ring-plum" : "border-line-strong hover:border-stone-400")}>
                                <div className="rounded overflow-hidden border border-black/5" style={{ background: p.chat_bg_color }} aria-hidden>
                                    <div className="h-3" style={{ background: p.color }} />
                                    <div className="p-1.5 space-y-1">
                                        <div className="h-1.5 w-3/4 rounded-full" style={{ background: p.assistant_bubble_bg }} />
                                        <div className="h-1.5 w-1/2 rounded-full ml-auto" style={{ background: p.user_bubble_bg }} />
                                    </div>
                                </div>
                                <span className="block text-[12px] text-stone-700 mt-1.5 px-0.5">{t.name}</span>
                            </button>
                        );
                    })}
                </div>
            </Section>

            <Section title="Brand">
                <Field label="Assistant name" htmlFor="bot-name">
                    <Input id="bot-name" value={botName} maxLength={60} onChange={(e) => setBotName(e.target.value)} placeholder="e.g. Green Park Homes" />
                </Field>
                <Field label="Avatar" hint="Shown in the chat header and on the launcher. PNG, JPG, WebP, GIF or SVG; square images work best.">
                    <div className="flex items-center gap-3">
                        <div className="h-12 w-12 shrink-0 rounded-full border border-line bg-stone-50 overflow-hidden flex items-center justify-center">
                            {v.logo_url ? <img src={assetUrl(v.logo_url)} alt="" className="h-full w-full object-cover object-top" /> : <ImageIcon size={18} className="text-stone-400" />}
                        </div>
                        <Button size="sm" onClick={() => logoInput.current?.click()} disabled={uploading === "logo"}>
                            <Upload size={14} /> {uploading === "logo" ? "Uploading…" : "Upload"}
                        </Button>
                        {v.logo_url && <Button size="sm" variant="ghost" onClick={() => set({ logo_url: "" })}>Remove</Button>}
                        <input ref={logoInput} type="file" accept={IMAGE_TYPES} className="hidden" onChange={(e) => { upload("logo", e.target.files?.[0]); e.target.value = ""; }} />
                    </div>
                    <Input className="mt-2" value={v.logo_url} onChange={(e) => set({ logo_url: e.target.value })} placeholder="Or paste an image link" />
                </Field>
                <div className="grid grid-cols-2 gap-3">
                    <ColorField label="Brand colour" value={v.color} onChange={(c) => set({ color: c })} hint="Header, send button and launcher." />
                    <ColorField label="Header text" value={v.text_color} onChange={(c) => set({ text_color: c })} against={v.color} />
                </div>
            </Section>

            <Section title="Header">
                <Field label="Status line" htmlFor="subtitle" hint="Under the name. Leave empty for “Usually replies instantly”.">
                    <Input id="subtitle" value={v.subtitle} maxLength={60} onChange={(e) => set({ subtitle: e.target.value })} placeholder="Usually replies instantly" />
                </Field>
                <ToggleRow label="Let visitors switch to a person" hint="Shows a small AI / Person switch at the top right of the chat. Your team replies from Live chat."
                           checked={v.show_human_toggle} onChange={(c) => set({ show_human_toggle: c })} />
                <RangeField label="Header height" value={v.header_height} min={56} max={120} onChange={(n) => set({ header_height: n })} />
            </Section>

            <Section title="Messages">
                <Field label="Welcome message" htmlFor="welcome" hint="The first thing visitors see. If you have a flow, the flow speaks first instead.">
                    <Textarea id="welcome" rows={2} maxLength={300} value={v.welcome_message} onChange={(e) => set({ welcome_message: e.target.value })}
                              placeholder={`Hi! I'm ${botName || "your assistant"}. How can I help you today?`} />
                </Field>
                <Field label="Suggested questions" hint="Up to 4 buttons, shown from the start until the visitor asks their own question. If your flow is waiting for an answer, the assistant answers the button first and the flow then asks again. Press Enter after each.">
                    <PhraseInput label="Suggested questions" keepCase value={v.starters} placeholder="e.g. What are your prices?"
                                 onChange={(q) => set({ starters: q.map((s) => s.slice(0, 60)).slice(0, 4) })} />
                </Field>
                <Field label="Message box placeholder" htmlFor="placeholder">
                    <Input id="placeholder" value={v.input_placeholder} maxLength={60} onChange={(e) => set({ input_placeholder: e.target.value })} placeholder="Type a message..." />
                </Field>
            </Section>

            <Section title="Colours">
                <div className="grid grid-cols-2 gap-3">
                    <ColorField label="Visitor message" value={v.user_bubble_bg} onChange={(c) => set({ user_bubble_bg: c })} />
                    <ColorField label="Visitor text" value={v.user_bubble_text} onChange={(c) => set({ user_bubble_text: c })} against={v.user_bubble_bg} />
                    <ColorField label="Assistant message" value={v.assistant_bubble_bg} onChange={(c) => set({ assistant_bubble_bg: c })} />
                    <ColorField label="Assistant text" value={v.assistant_bubble_text} onChange={(c) => set({ assistant_bubble_text: c })} against={v.assistant_bubble_bg} />
                    <ColorField label="Chat background" value={v.chat_bg_color} onChange={(c) => set({ chat_bg_color: c })} />
                    <ColorField label="Footer" value={v.footer_bg_color} placeholder="Dark (default)" onChange={(c) => set({ footer_bg_color: c })}
                                onClear={() => set({ footer_bg_color: "" })} />
                    <ColorField label="Message box" value={v.input_bg_color} onChange={(c) => set({ input_bg_color: c })} />
                    <ColorField label="Message box text" value={v.input_text_color} onChange={(c) => set({ input_text_color: c })} against={v.input_bg_color} />
                </div>
            </Section>

            <Section title="Text and shape">
                <Field label="Font" htmlFor="font" hint="Mukta, Hind and Noto Sans also cover Hindi, Tamil and other Indian scripts.">
                    <Select id="font" value={v.font_family} onChange={(e) => set({ font_family: e.target.value })}>
                        {!fontKnown && <option value={v.font_family}>{v.font_family.replace(/'/g, "").split(",")[0]}</option>}
                        {FONTS.map((f) => <option key={f.value} value={f.value}>{f.label}</option>)}
                    </Select>
                </Field>
                <RangeField label="Corner roundness" value={v.border_radius} min={0} max={28} onChange={(n) => set({ border_radius: n })} />
            </Section>

            <Section title="Background image" description="Optional. A subtle pattern or photo behind the messages (PNG, JPG, WebP, GIF or SVG).">
                <div className="flex gap-2">
                    <Input value={v.background_image} onChange={(e) => set({ background_image: e.target.value })} placeholder="Paste an image link" />
                    <Button size="md" onClick={() => bgInput.current?.click()} disabled={uploading === "background"}>
                        <Upload size={14} /> {uploading === "background" ? "Uploading…" : "Upload"}
                    </Button>
                    <input ref={bgInput} type="file" accept={IMAGE_TYPES} className="hidden" onChange={(e) => { upload("background", e.target.files?.[0]); e.target.value = ""; }} />
                </div>
                {v.background_image && (
                    <>
                        <RangeField label="Visibility" value={Math.round(v.background_opacity * 100)} min={5} max={100} unit="%"
                                    onChange={(n) => set({ background_opacity: n / 100 })} />
                        <Button size="sm" variant="ghost" className="-ml-3" onClick={() => set({ background_image: "" })}>Remove image</Button>
                    </>
                )}
            </Section>

            <Section title="Launcher" description="The button that opens the chat on your website.">
                <ChoiceRow label="Position" value={v.position} onChange={(p) => set({ position: p })}
                           options={[{ value: "left", label: "Bottom left" }, { value: "right", label: "Bottom right" }]} />
                <ChoiceRow label="Shape" value={v.launcher_shape} onChange={(s) => set({ launcher_shape: s })}
                           options={[
                               ...([["circle", "Circle", "50%", 20], ["rounded", "Rounded", "6px", 20], ["square", "Square", "1px", 20], ["oval", "Pill", "999px", 28]] as const)
                                   .map(([value, label, r, w]) => ({ value, label, icon: <span className="block h-5 bg-stone-700" style={{ borderRadius: r, width: w }} /> })),
                               { value: "character" as const, label: "Character", icon: (
                                   <svg viewBox="0 0 12 20" className="h-5 w-3 fill-stone-700" aria-hidden><circle cx="6" cy="3.2" r="3" /><path d="M1.5 20v-9.5a4.5 4.5 0 0 1 9 0V20z" /></svg>
                               ) },
                           ]} />
                {v.launcher_shape === "character" ? (
                    <>
                        <Field label="Character">
                            <Segmented label="Character" value={v.character_animation === "violet" ? "violet" : "picture"}
                                       onChange={(c) => set({ character_animation: c === "violet" ? "violet" : "" })}
                                       options={[{ value: "picture", label: "Your picture" }, { value: "violet", label: "Violet, animated" }]} />
                        </Field>
                        {v.character_animation === "violet" ? (
                            <p className="text-[12px] leading-relaxed text-stone-500">
                                Violet, Nimmi&apos;s animated assistant, stands in the corner. She blinks, looks at a visitor&apos;s cursor when it comes near, breathes and waves now and then, and keeps still for visitors who turn on reduced motion. The chat header shows your avatar.
                            </p>
                        ) : (
                            <>
                                <p className="text-[12px] leading-relaxed text-stone-500">
                                    Your avatar stands at full height in the corner of your website. Upload a standing figure with a transparent background; the chat header shows the top of it.
                                </p>
                                {!v.logo_url && <p className="text-[12px] text-amber-700">Upload an avatar above. Until then, visitors see the round chat button.</p>}
                            </>
                        )}
                        <RangeField label="Character height" value={v.character_height} min={80} max={220} onChange={(n) => set({ character_height: n })} />
                    </>
                ) : (
                    <>
                        <Field label="Text on the launcher" htmlFor="launcher-label" hint="Optional. A short label such as “Chat with us” gets more clicks than an icon alone.">
                            <Input id="launcher-label" value={v.launcher_label} maxLength={30} onChange={(e) => set({ launcher_label: e.target.value })} placeholder="Icon only" />
                        </Field>
                        <ToggleRow label="Filled background" checked={v.show_launcher_bg} onChange={(c) => set({ show_launcher_bg: c })} />
                        {!v.launcher_label.trim() && <ToggleRow label="Speech-bubble tail" checked={v.show_tail} onChange={(c) => set({ show_tail: c })} />}
                        <RangeField label="Icon size" value={v.logo_size} min={20} max={56} onChange={(n) => set({ logo_size: n })} />
                    </>
                )}
                <div className="grid grid-cols-2 gap-4">
                    <RangeField label="From the side" value={v.right_padding} min={0} max={80} onChange={(n) => set({ right_padding: n })} />
                    <RangeField label="From the bottom" value={v.bottom_padding} min={0} max={80} onChange={(n) => set({ bottom_padding: n })} />
                </div>
            </Section>

            <Section title="Where it appears" description="Keep the chat off pages where it gets in the way, like checkout or login.">
                <Field label="Show the chat on">
                    <Segmented label="Show the chat on" value={v.page_rule} onChange={(r) => set({ page_rule: r })}
                               options={[{ value: "all", label: "Every page" }, { value: "only", label: "Only these" }, { value: "except", label: "All except" }]} />
                </Field>
                {v.page_rule !== "all" && (
                    <Field label={v.page_rule === "only" ? "Pages to show it on" : "Pages to hide it on"}
                           hint="Page paths, like /pricing. End with * for a whole section, like /blog/*. Press Enter after each.">
                        <PhraseInput label="Page paths" keepCase value={v.page_paths} placeholder="/checkout"
                                     onChange={(paths) => set({ page_paths: paths.map((x) => x.trim()).filter(Boolean).slice(0, 30) })} />
                    </Field>
                )}
                {v.page_rule === "only" && !v.page_paths.length && (
                    <p className="text-[12px] text-amber-700">Add at least one page, or the chat won&apos;t show anywhere.</p>
                )}
                <ToggleRow label="Hide on phones" hint="Shows the chat on computers and tablets only."
                           checked={v.hide_on_mobile} onChange={(c) => set({ hide_on_mobile: c })} />
            </Section>

            <Section title="On your website" description="How the chat introduces itself to visitors.">
                <Field label="Greeting beside the launcher" htmlFor="greeting" hint="A short line that pops up next to the button. Visitors can dismiss it.">
                    <Input id="greeting" value={v.launcher_greeting} maxLength={90} onChange={(e) => set({ launcher_greeting: e.target.value })}
                           placeholder="e.g. Questions about our homes? Ask me." />
                </Field>
                {v.launcher_greeting.trim() && (
                    <RangeField label="Show it after" value={v.greeting_delay} min={0} max={30} unit=" s" onChange={(n) => set({ greeting_delay: n })} />
                )}
                <ToggleRow label="Open the chat automatically" hint="Once per visit, on computers only. It never opens by itself on phones."
                           checked={v.auto_open_delay > 0} onChange={(c) => set({ auto_open_delay: c ? 15 : 0 })} />
                {v.auto_open_delay > 0 && (
                    <RangeField label="Open after" value={v.auto_open_delay} min={3} max={60} unit=" s" onChange={(n) => set({ auto_open_delay: n })} />
                )}
                <div className="grid grid-cols-2 gap-4">
                    <RangeField label="Window width" value={v.window_width} min={320} max={480} step={10} onChange={(n) => set({ window_width: n })} />
                    <RangeField label="Window height" value={v.window_height} min={460} max={760} step={10} onChange={(n) => set({ window_height: n })} />
                </div>
            </Section>
        </div>
    );
}
