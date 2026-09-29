const isDev = process.env.NODE_ENV !== 'production'

// Origins the browser talks to directly (only set in "direct" mode; the
// default /api proxy is same-origin and covered by 'self').
const origin = (u) => { try { return new URL(u).origin } catch { return '' } }
const apiOrigin = origin(process.env.NEXT_PUBLIC_API_URL)
const wsOrigin = origin(process.env.NEXT_PUBLIC_WS_URL)

// Static CSP. Scripts keep 'unsafe-inline' because App Router injects inline
// bootstrap scripts; a nonce-based policy would force every page to render
// dynamically. This still blocks third-party scripts, eval (prod), plugins,
// <base> hijacking, framing and cross-origin form posts.
const csp = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${isDev ? " 'unsafe-eval'" : ''} https://checkout.razorpay.com`,
  "style-src 'self' 'unsafe-inline'",
  "font-src 'self' data:",
  "img-src 'self' data: blob: https:",
  ['connect-src', "'self'", apiOrigin, wsOrigin, 'https://*.razorpay.com',
    ...(isDev ? ['http://localhost:*', 'ws://localhost:*'] : [])].filter(Boolean).join(' '),
  'frame-src https://api.razorpay.com https://checkout.razorpay.com',
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
  ...(isDev ? [] : ['upgrade-insecure-requests']),
].join('; ')

/** @type {import('next').NextConfig} */
const nextConfig = {
  // Server-side proxy: /api/* → Railway backend
  //
  // PRODUCTION (Vercel):  set BACKEND_URL = your Railway service URL
  //                       e.g. https://web-production-xxxx.up.railway.app
  //                       This is a PRIVATE server-only var (no NEXT_PUBLIC_ prefix).
  //                       The browser only ever calls /api/* on its own origin —
  //                       zero CORS, SSL from Vercel, Railway never exposed.
  //
  // LOCAL DEV:            BACKEND_URL defaults to http://localhost:3002
  //                       Set NEXT_PUBLIC_API_URL=http://localhost:8000 in
  //                       frontend/.env.local to bypass the proxy entirely.
  async rewrites() {
    const backendUrl = process.env.BACKEND_URL || 'http://localhost:3002'
    if (!process.env.BACKEND_URL && process.env.NODE_ENV === 'production') {
      console.warn(
        '[next.config] BACKEND_URL is not set — /api/* will proxy to localhost:3002 ' +
        'which will fail in production. Set BACKEND_URL in Vercel environment variables.'
      )
    }
    return [
      {
        source: '/api/:path*',
        destination: `${backendUrl}/:path*`,
      },
    ]
  },
  // Baseline hardening headers + CSP (see `csp` above).
  async headers() {
    return [
      {
        source: '/:path*',
        headers: [
          { key: 'Content-Security-Policy', value: csp },
          { key: 'X-Frame-Options', value: 'DENY' },
          { key: 'X-Content-Type-Options', value: 'nosniff' },
          { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
          { key: 'Strict-Transport-Security', value: 'max-age=31536000; includeSubDomains' },
          { key: 'Permissions-Policy', value: 'camera=(), microphone=(), geolocation=()' },
        ],
      },
    ]
  },
}

export default nextConfig;
