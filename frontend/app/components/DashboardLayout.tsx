"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BarChart3,
  FileText,
  TrendingUp,
  Newspaper,
  User,
  Wrench,
  Settings,
  MessageCircle,
  Network,
  Trophy,
} from "lucide-react";
import { useAuth } from "../contexts/AuthContext";
import { BigpdfGlobalShell } from "./bigpdf/BigpdfGlobalShell";

/** 经营数据（/）需 view_business_dashboard：管理层 或 管理员 或 部门=财务部，见规划 2.a */
const businessDashboardNavItem = { href: "/", label: "经营数据", icon: BarChart3 };

const baseNavItems = [
  { href: "/ai-interaction", label: "AI内网", icon: MessageCircle },
  { href: "/policy-news", label: "新闻政策", icon: Newspaper },
  { href: "/exchange", label: "汇率趋势", icon: TrendingUp },
  { href: "/contracts", label: "合同台账", icon: FileText },
  { href: "/utils", label: "实用工具", icon: Wrench },
  { href: "/user", label: "用户管理", icon: User },
];

/** 竞品财报（/competitor）需 view_business_dashboard：管理层 / 财务部 / 管理员，见 specs 1.2.3.c */
const competitorNavItem = { href: "/competitor", label: "竞品财报", icon: Trophy };

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(true);
  const { is_admin, view_business_dashboard } = useAuth();
  const navItems = [
    ...(view_business_dashboard ? [businessDashboardNavItem, competitorNavItem] : []),
    ...baseNavItems,
    ...(is_admin ? [{ href: "/equity", label: "股权全景", icon: Network }] : []),
    ...(is_admin ? [{ href: "/admin", label: "管理后台", icon: Settings }] : []),
  ];

  return (
    <div className="flex h-screen min-h-0 overflow-hidden bg-zinc-950">
      <div
        className={
          "relative shrink-0 transition-[width] duration-200 " +
          (collapsed ? "w-16" : "w-40")
        }
      >
        <aside className="group/sidebar sticky top-0 flex h-screen w-full flex-col border-r border-zinc-800 bg-zinc-900">
          <button
            type="button"
            onClick={() => setCollapsed((c) => !c)}
            title={collapsed ? "展开侧边栏" : "收拢侧边栏"}
            aria-label={collapsed ? "展开侧边栏" : "收拢侧边栏"}
            aria-expanded={!collapsed}
            className="absolute left-1/2 top-1 z-10 flex h-5 w-5 -translate-x-1/2 items-center justify-center rounded text-zinc-600 opacity-0 transition-[opacity,color] duration-200 hover:text-zinc-400 group-hover/sidebar:opacity-100 focus:opacity-100 focus:outline-none focus-visible:ring-1 focus-visible:ring-blue-600/40 md:top-1.5"
          >
            <svg viewBox="0 0 16 16" fill="none" className="h-3.5 w-3.5" aria-hidden>
              {collapsed ? (
                <>
                  <path d="M5 4.5 8 8l-3 3.5" stroke="currentColor" strokeWidth="1.25" strokeLinecap="round" strokeLinejoin="round" />
                  <path d="M9 4.5 12 8l-3 3.5" stroke="currentColor" strokeWidth="1.25" strokeLinecap="round" strokeLinejoin="round" />
                </>
              ) : (
                <>
                  <path d="M11 4.5 8 8l3 3.5" stroke="currentColor" strokeWidth="1.25" strokeLinecap="round" strokeLinejoin="round" />
                  <path d="M7 4.5 4 8l3 3.5" stroke="currentColor" strokeWidth="1.25" strokeLinecap="round" strokeLinejoin="round" />
                </>
              )}
            </svg>
          </button>

          <nav className="flex flex-1 flex-col gap-1 overflow-y-auto p-2 pt-6 md:pt-8">
            {navItems.map((item) => {
              const isActive =
                pathname === item.href || (item.href !== "/" && pathname.startsWith(item.href));
              const Icon = item.icon;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  title={collapsed ? item.label : undefined}
                  className={
                    "flex items-center gap-3 rounded-md transition-colors " +
                    (collapsed ? "h-11 w-11 justify-center px-0" : "h-11 px-3") +
                    (isActive
                      ? " bg-zinc-700 text-zinc-100"
                      : " text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100")
                  }
                >
                  <Icon className="h-5 w-5 shrink-0" />
                  {!collapsed && <span className="truncate text-sm">{item.label}</span>}
                </Link>
              );
            })}
          </nav>

          {!collapsed ? (
            <p className="border-t border-zinc-800/80 px-2 py-2 text-center text-[10px] text-zinc-600">
              内网
            </p>
          ) : null}
        </aside>
      </div>

      <main className="relative min-h-0 flex-1 overflow-auto">{children}</main>
      <BigpdfGlobalShell />
    </div>
  );
}
