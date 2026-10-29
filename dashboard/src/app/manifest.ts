import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
    return {
        name: "Nimmi AI",
        short_name: "Nimmi AI",
        description: "AI voice agent and chatbot for website chat, WhatsApp and phone calls, in 11 Indian languages.",
        start_url: "/dashboard",
        display: "standalone",
        background_color: "#faf9f7",
        theme_color: "#550a64",
        icons: [{ src: "/favicon.png", sizes: "any", type: "image/png" }],
    };
}
