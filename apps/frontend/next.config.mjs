/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    // Proxy API calls to the backend during development.
    const backend = process.env.BACKEND_URL || "http://localhost:8000";
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
};
export default nextConfig;
