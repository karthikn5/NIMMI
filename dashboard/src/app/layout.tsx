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
  title: "Nimmi AI — Custom AI Chatbot Builder for Indian Businesses | Train on Your Data",
  description: "Build a custom AI chatbot trained on your business data in minutes. No-code platform built for Indian SMEs. Try Nimmi AI free today.",
  alternates: {
    canonical: "/",
  },
  verification: {
    google: "woQlFXLN9lakQBgXCghYGOoN5RNv7bQBFUr-bJZmlOk",
  },
  openGraph: {
    title: "Nimmi AI — Custom AI Chatbot Builder for Indian Businesses | Train on Your Data",
  description: "Build a custom AI chatbot trained on your business data in minutes. No-code platform built for Indian SMEs. Try Nimmi AI free today.",
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
    description: "Build a custom AI chatbot trained on your business data in minutes. No-code platform built for Indian SMEs. Try Nimmi AI free today.",
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
