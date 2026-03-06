/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: "standalone",
  // /api/* 由 app/api/[[...path]]/route.ts 代理到后端并转发 Authorization 等头，不再用 rewrites
};

module.exports = nextConfig;
