import type { Metadata } from "next";
import { headers } from "next/headers";
import { Geist } from "next/font/google";
import "./globals.css";
import AuthGuard from "./components/AuthGuard";

const geistSans = Geist({
  subsets: ["latin"],
  variable: "--font-sans",
});

export async function generateMetadata(): Promise<Metadata> {
  const headersList = await headers();
  const host = headersList.get("host") || "localhost:3000";
  const proto = headersList.get("x-forwarded-proto") || "http";
  const baseUrl = `${proto}://${host}`;

  const title = "财务信息内网";
  const description = "经营数据、新闻政策、汇率趋势、竞品财报与财务AI应用、探索";

  return {
    metadataBase: new URL(baseUrl),
    title,
    description,
    openGraph: {
      title,
      description,
      url: baseUrl,
      siteName: title,
      images: [
        {
          url: "/og-image.png",
          width: 1200,
          height: 630,
        },
      ],
      type: "website",
    },
    twitter: {
      card: "summary_large_image",
      title,
      description,
    },
  };
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN" className={geistSans.variable}>
      <body className="min-h-screen antialiased">
        <AuthGuard>{children}</AuthGuard>
      </body>
    </html>
  );
}
