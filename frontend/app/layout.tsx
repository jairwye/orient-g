import type { Metadata } from "next";
import { Geist } from "next/font/google";
import "./globals.css";
import DashboardLayout from "./components/DashboardLayout";

const geistSans = Geist({
  subsets: ["latin"],
  variable: "--font-sans",
});

export const metadata: Metadata = {
  title: "财务信息内网",
  description: "经营数据、竞品财报、汇率趋势、政策新闻与财务 AI",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN" className={geistSans.variable}>
      <body className="min-h-screen antialiased">
        <DashboardLayout>{children}</DashboardLayout>
      </body>
    </html>
  );
}
