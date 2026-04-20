/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: "standalone",
  images: {
    remotePatterns: [
      {
        protocol: "https",
        hostname: "res.youxituoluo.com",
        pathname: "/**",
      },
      {
        protocol: "https",
        hostname: "img.huxiucdn.com",
        pathname: "/**",
      },
      {
        protocol: "https",
        hostname: "img1.gamersky.com",
        pathname: "/**",
      },
      {
        protocol: "https",
        hostname: "img.3dmgame.com",
        pathname: "/**",
      },
      {
        protocol: "https",
        hostname: "img1.mydrivers.com",
        pathname: "/**",
      },
      {
        protocol: "https",
        hostname: "upload.chinaz.com",
        pathname: "/**",
      },
      {
        protocol: "https",
        hostname: "p9-xtjj-sign.byteimg.com",
        pathname: "/**",
      },
      {
        protocol: "https",
        hostname: "p6-xtjj-sign.byteimg.com",
        pathname: "/**",
      },
    ],
  },
  // /api/* 由 app/api/[[...path]]/route.ts 代理到后端并转发 Authorization 等头，不再用 rewrites
};

module.exports = nextConfig;
