"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { BarChart3, FileText, TrendingUp, Newspaper, PanelLeftClose, PanelLeftOpen, User } from "lucide-react";

const navItems = [
  { href: "/", label: "经营数据", icon: BarChart3 },
  { href: "/competitor", label: "竞品财报", icon: FileText },
  { href: "/exchange", label: "汇率趋势", icon: TrendingUp },
  { href: "/policy-news", label: "政策新闻", icon: Newspaper },
  { href: "/user", label: "用户管理", icon: User },
];

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(true);

  return (
    <div className="flex min-h-screen bg-zinc-950">
      <div
        className={
          "relative shrink-0 transition-[width] duration-200 " +
          (collapsed ? "w-16" : "w-40")
        }
      >
        <aside className="flex h-full min-h-screen w-full flex-col border-r border-zinc-800 bg-zinc-900">
          <nav className="flex flex-col gap-1 p-2 pt-6 md:pt-8">
          {navItems.map((item) => {
            const isActive = pathname === item.href || (item.href !== "/" && pathname.startsWith(item.href));
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
        <div className="mt-auto border-t border-zinc-800 p-2 text-center text-[10px] text-zinc-500">
          {collapsed ? "" : "内网"}
        </div>
        </aside>
      </div>

      <main className="relative flex-1 overflow-auto">
        <button
          type="button"
          onClick={() => setCollapsed((c) => !c)}
          className="absolute left-0 top-3 z-10 flex h-6 w-6 translate-x-1/2 -translate-y-1/2 items-center justify-center text-zinc-400 hover:text-zinc-200"
          title={collapsed ? "展开侧边栏" : "收拢侧边栏"}
          aria-label={collapsed ? "展开侧边栏" : "收拢侧边栏"}
        >
          {collapsed ? (
            <PanelLeftOpen className="h-4 w-4" />
          ) : (
            <PanelLeftClose className="h-4 w-4" />
          )}
        </button>
        {children}
      </main>
    </div>
  );
}
