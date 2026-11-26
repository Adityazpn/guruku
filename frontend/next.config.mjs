// The browser only talks to this origin; /api is proxied to the FastAPI backend,
// so the HttpOnly refresh cookie stays same-origin and no CORS is needed.
const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

/** @type {import('next').NextConfig} */
export default {
  async rewrites() {
    return [{ source: "/api/v1/:path*", destination: `${BACKEND_URL}/api/v1/:path*` }];
  },
};
