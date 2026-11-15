import type { NextConfig } from "next";

// Where Next.js forwards /api/* (same origin for the browser: no CORS, cookies just work, ADR 0004).
// Read at build time: the container image is built with API_INTERNAL_URL=http://api:8000.
const apiUrl = process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000";

// Content Security Policy (stage 9), third layer after OutputGuard and the safe Markdown: even if
// an answer carried an image or a link, the browser would not load anything from another site.
// script-src is not restricted here: Next.js needs inline scripts (nonces would be the next step).
const contentSecurityPolicy = [
  "img-src 'self' data: blob:",
  "connect-src 'self'",
  "worker-src 'self' blob:",
  "font-src 'self' data:",
  "media-src 'none'",
  "object-src 'none'",
  "frame-src 'none'",
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
].join("; ");

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  // Next.js gzips what it forwards, and gzip holds a streamed answer (Server-Sent Events) until
  // the end: the chat would show the whole text at once (stage 7). Compression is Caddy's job.
  compress: false,
  experimental: {
    // Next.js forwards at most 10 MB of a request body to the rewrite target and silently cuts
    // the rest. Uploads are up to 25 MB (MAX_UPLOAD_MB) plus the multipart envelope.
    proxyClientMaxBodySize: "30mb",
  },
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
          { key: "Content-Security-Policy", value: contentSecurityPolicy },
        ],
      },
    ];
  },
};

export default nextConfig;
