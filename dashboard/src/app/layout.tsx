import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Script from "next/script";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  metadataBase: new URL("https://nimmiai.in"),
  title: "Nimmi AI — Custom AI Chatbot Builder for Indian Businesses | Train on Your Data",
  description: "Nimmi AI lets you build and deploy custom AI chatbots for your website, WhatsApp, and app — no code needed. Start free. Made in India.",
  alternates: {
    canonical: "https://nimmiai.in",
  },
  verification: {
    google: "woQlFXLN9lakQBgXCghYGOoN5RNv7bQBFUr-bJZmlOk",
  },
  openGraph: {
    title: "Nimmi AI — Custom AI Chatbot Builder for Indian Businesses | Train on Your Data",
  description: "Nimmi AI lets you build and deploy custom AI chatbots for your website, WhatsApp, and app — no code needed. Start free. Made in India.",
    url: "https://nimmiai.in",
    siteName: "Nimmi AI",
    images: [
      {
        url: "/og-image.png",
        width: 1200,
        height: 630,
        alt: "Nimmi AI — Build Custom AI Chatbots",
      },
    ],
    locale: "en_IN",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "Nimmi AI — Build Custom AI Chatbots for Your Business",
    description: "Nimmi AI lets you build and deploy custom AI chatbots for your website, WhatsApp, and app — no code needed. Start free. Made in India.",
    images: ["/og-image.png"],
  },
  icons: {
    icon: "/favicon.png",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
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
