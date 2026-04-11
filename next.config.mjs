/** @type {import('next').NextConfig} */
const nextConfig = {
  // Proxy /api/* → backend so the browser never needs to know the backend URL
  // Set NEXT_PUBLIC_API_URL in Vercel env vars to your backend URL (Railway, Render, etc.)
  async rewrites() {
    const backendUrl = process.env.BACKEND_URL || 'http://localhost:3002'
    return [
      {
        source: '/api/:path*',
        destination: `${backendUrl}/:path*`,
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
