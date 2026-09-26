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
  // Baseline hardening headers. CSP deliberately not set yet — needs a
  // nonce/hash pass so it doesn't break Next's inline scripts.
  async headers() {
    return [
      {
        source: '/:path*',
        headers: [
          { key: 'X-Frame-Options', value: 'DENY' },
          { key: 'X-Content-Type-Options', value: 'nosniff' },
          { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
          { key: 'Strict-Transport-Security', value: 'max-age=31536000; includeSubDomains' },
          { key: 'Permissions-Policy', value: 'camera=(), microphone=(), geolocation=()' },
        ],
      },
    ]
  },
  // Silence the "Module not found" noise for optional server-only packages
  // that aren't used in the frontend bundle
  webpack(config) {
    config.resolve.fallback = { ...config.resolve.fallback, fs: false }
    return config
  },
}

export default nextConfig;
