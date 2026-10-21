import type { NextConfig } from "next";

// Sent with every page. The chat widget is the one page other websites may embed.
const security = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains" },
  { key: "Permissions-Policy", value: "camera=(), geolocation=(), microphone=(self)" },
];

const nextConfig: NextConfig = {
  // Lets a second dev server (e.g. for testing) run without sharing .next
  distDir: process.env.NEXT_DIST_DIR || ".next",
  poweredByHeader: false,
  async headers() {
    return [
      {
        // Everything except the widget: no framing by other sites (clickjacking), no plugins, no <base> tricks.
        source: "/:path((?!widget/).*)",
        headers: [
          ...security,
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Content-Security-Policy", value: "frame-ancestors 'none'; base-uri 'self'; object-src 'none'; form-action 'self'" },
        ],
      },
      {
        // The chat widget is embedded on customers' websites.
        source: "/widget/:path*",
        headers: [
          ...security,
          { key: "Content-Security-Policy", value: "frame-ancestors *; base-uri 'self'; object-src 'none'; form-action 'self'" },
        ],
      },
    ];
  },
  images: {
    remotePatterns: [
      {
        protocol: "https",
        hostname: "**.razorpay.com",
      },
    ],
  },
  eslint: {
    ignoreDuringBuilds: true,
  },
  typescript: {
    ignoreBuildErrors: true,
  },
  async redirects() {
    return [
      {
        source: '/:path*',
        has: [
          {
            type: 'host',
            value: 'www.nimmiai.in',
          },
        ],
        destination: 'https://nimmiai.in/:path*',
        permanent: true,
      },
    ];
  },
};

export default nextConfig;
