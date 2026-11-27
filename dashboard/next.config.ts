import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Initial defaults only. The dashboard's Connection Settings drawer can
  // override these from localStorage on any device without a redeploy.
  env: {
    NEXT_PUBLIC_API_URL:
      "http://localhost:8000",
    NEXT_PUBLIC_WS_URL:
      "ws://localhost:8000/ws/live",
  },
};

export default nextConfig;
