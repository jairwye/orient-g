"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { KeyRound, LogOut } from "lucide-react";
import { clearAuthToken } from "../lib/auth";

export default function UserPage() {
  const router = useRouter();
  const [loggingOut, setLoggingOut] = useState(false);

  const handleLogout = async () => {
    setLoggingOut(true);
    try {
      clearAuthToken();
      await fetch("/api/auth/logout", { method: "POST", credentials: "include" });
      router.replace("/login");
    } finally {
      setLoggingOut(false);
    }
  };

  return (
    <div className="p-6 md:p-8">
      <h1 className="text-2xl font-semibold tracking-tight text-zinc-100">用户管理</h1>
      <p className="mt-1 text-sm text-zinc-500">修改密码或退出当前账号</p>
      <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:gap-4">
        <Link
          href="/change-password"
          className="inline-flex items-center gap-2 rounded-lg border border-zinc-600 bg-zinc-800 px-4 py-3 text-sm font-medium text-zinc-200 hover:bg-zinc-700"
        >
          <KeyRound className="h-4 w-4 shrink-0" />
          修改密码
        </Link>
        <button
          type="button"
          onClick={handleLogout}
          disabled={loggingOut}
          className="inline-flex items-center gap-2 rounded-lg border border-zinc-600 bg-zinc-800 px-4 py-3 text-sm font-medium text-zinc-200 hover:bg-zinc-700 disabled:opacity-50"
        >
          <LogOut className="h-4 w-4 shrink-0" />
          {loggingOut ? "退出中…" : "退出登录"}
        </button>
      </div>
    </div>
  );
}
