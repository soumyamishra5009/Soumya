/** @type {import('next').NextConfig} */
const nextConfig = {
  transpilePackages: ["@syncforge/types"],
  images: {
    remotePatterns: [
      {
        protocol: "https",
        hostname: "**",
      },
    ],
  },
  webpack: (config) => {
    config.resolve.fallback = { fs: false };
    return config;
  },
};

export default nextConfig;
