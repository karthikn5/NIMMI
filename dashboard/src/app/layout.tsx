import type { Metadata } from "next";
import Script from "next/script";
import { preload } from "react-dom";
import "./globals.css";
import "./fonts.css";

// Defaults for every page. Each public page sets its own title, description and canonical address (lib/site/seo.ts);
// there is deliberately no site-wide canonical here: inherited, it told search engines every page was the home page.
export const metadata: Metadata = {
  metadataBase: new URL("https://nimmiai.in"),
  title: {
    default: "AI Voice Agent, WhatsApp & Website Chatbot | Nimmi AI",
    template: "%s | Nimmi AI",
  },
  description: "AI voice agent and chatbot that answers calls, WhatsApp and website chat in 11 Indian languages, captures leads, follows up and books meetings. Start free.",
  applicationName: "Nimmi AI",
  authors: [{ name: "Nimmi AI", url: "https://nimmiai.in" }],
  creator: "Nimmi AI",
  publisher: "Nimmi AI",
  category: "Business software",
  robots: {
    index: true,
    follow: true,
    googleBot: { index: true, follow: true, "max-image-preview": "large", "max-snippet": -1, "max-video-preview": -1 },
  },
  verification: {
    google: "woQlFXLN9lakQBgXCghYGOoN5RNv7bQBFUr-bJZmlOk",
  },
  openGraph: {
    siteName: "Nimmi AI",
    images: [{ url: "/og/home.png", width: 1200, height: 630, alt: "Nimmi AI: AI voice agent and chatbot for Indian businesses" }],
    locale: "en_IN",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    images: ["/og/home.png"],
  },
  icons: {
    icon: "/favicon.png",
    apple: "/favicon.png", // Google often uses the apple-touch-icon for search snippets
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  // The fonts (fonts.css) start loading with the page, as next/font did: their Latin files only.
  preload("/fonts/geist-v5-latin.woff2", { as: "font", type: "font/woff2" });
  preload("/fonts/geist-mono-v6-latin.woff2", { as: "font", type: "font/woff2" });
  return (
    <html lang="en-IN">
      <body
        className="antialiased"
        suppressHydrationWarning
      >
        {/* Google Tag Manager (noscript) */}
        <noscript>
          <iframe
            src="https://www.googletagmanager.com/ns.html?id=GTM-MVJ58RGC"
            height="0"
            width="0"
            style={{ display: 'none', visibility: 'hidden' }}
          ></iframe>
        </noscript>
        {/* End Google Tag Manager (noscript) */}

        {/* Google Tag Manager */}
        <Script id="gtm-script" strategy="afterInteractive">
          {`(function(w,d,s,l,i){w[l]=w[l]||[];w[l].push({'gtm.start':
          new Date().getTime(),event:'gtm.js'});var f=d.getElementsByTagName(s)[0],
          j=d.createElement(s),dl=l!='dataLayer'?'&l='+l:'';j.async=true;j.src=
          'https://www.googletagmanager.com/gtm.js?id='+i+dl;f.parentNode.insertBefore(j,f);
          })(window,document,'script','dataLayer','GTM-MVJ58RGC');`}
        </Script>
        {/* End Google Tag Manager */}

        {children}
      </body>
    </html>
  );
}
