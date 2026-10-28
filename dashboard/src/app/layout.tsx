import type { Metadata } from "next";
import Script from "next/script";
import { preload } from "react-dom";
import "./globals.css";
import "./fonts.css";

export const metadata: Metadata = {
  metadataBase: new URL("https://nimmiai.in"),
  title: "Nimmi AI | AI assistant for website chat, WhatsApp and phone calls",
  description: "AI assistants for website chat, WhatsApp and phone calls in 11 Indian languages. Trained on your business, they answer customers, capture leads and hand over to your team. Free to build and test.",
  alternates: {
    canonical: "https://nimmiai.in",
  },
  verification: {
    google: "woQlFXLN9lakQBgXCghYGOoN5RNv7bQBFUr-bJZmlOk",
  },
  openGraph: {
    title: "Nimmi AI | AI assistant for website chat, WhatsApp and phone calls",
  description: "AI assistants for website chat, WhatsApp and phone calls in 11 Indian languages. Trained on your business, they answer customers, capture leads and hand over to your team. Free to build and test.",
    url: "https://nimmiai.in",
    siteName: "Nimmi AI",
    images: [
      {
        url: "/og-image.png",
        width: 1200,
        height: 630,
        alt: "Nimmi AI",
      },
    ],
    locale: "en_IN",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "Nimmi AI | AI assistant for website chat, WhatsApp and phone calls",
    description: "AI assistants for website chat, WhatsApp and phone calls in 11 Indian languages. Trained on your business, they answer customers, capture leads and hand over to your team. Free to build and test.",
    images: ["/og-image.png"],
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
    <html lang="en">
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
