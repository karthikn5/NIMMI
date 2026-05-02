import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
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
  title: "Nimmi AI — Build Custom AI Chatbots for Your Business | India",
  description: "Build custom AI chatbots for your business with Nimmi AI. Train on your data in minutes & embed anywhere. Boost leads and engagement. Get started for free today!",
  alternates: {
    canonical: "/",
  },
  verification: {
    google: "woQlFXLN9lakQBgXCghYGOoN5RNv7bQBFUr-bJZmlOk",
  },
  openGraph: {
    title: "Nimmi AI — Build Custom AI Chatbots for Your Business | India",
    description: "Build custom AI chatbots for your business with Nimmi AI. Train on your data in minutes & embed anywhere. Boost leads and engagement.",
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
    description: "Build custom AI chatbots for your business with Nimmi AI. Train on your data in minutes & embed anywhere.",
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
        {children}
      </body>
    </html>
  );
}
