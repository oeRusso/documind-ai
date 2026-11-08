import type { NextConfig } from "next";

// Where Next.js forwards /api/* (same origin for the browser: no CORS, cookies just work, ADR 0004).
// Read at build time: the container image is built with API_INTERNAL_URL=http://api:8000.
const apiUrl = process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiUrl}/api/:path*` }];
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          // The invitation token lives after "#" and is never sent; still, no Referer leaves the app.
          { key: "Referrer-Policy", value: "no-referrer" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
        ],
      },
    ];
  },
};

export default nextConfig;
