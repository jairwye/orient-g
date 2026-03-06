"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { setAuthToken } from "../lib/auth";

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const justChangedPassword = searchParams.get("changed") === "1";
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ username: username.trim(), password }),
      });
      const data = await res.json().catch(() => ({}));
      if (res.ok && data.ok && data.token) {
        setAuthToken(data.token);
        // 短暂延迟再跳转，避免刚打开页面时代理/后端冷启动导致紧接着的 /me 失败、被误判未登录而跳回登录页
        setError("");
        await new Promise((r) => setTimeout(r, 200));
        router.replace(data.must_change_password ? "/change-password" : "/");
        return;
      }
      setError(typeof data.detail === "string" ? data.detail : "登录失败，请重试");
    } catch {
      setError("网络错误，请确认后端已启动");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-zinc-950">
      <div className="w-full max-w-sm rounded-lg border border-zinc-800 bg-zinc-900/80 p-6 shadow-xl">
        <h1 className="text-center text-lg font-medium text-zinc-100">登录</h1>
        <p className="mt-1 text-center text-sm text-zinc-500">请输入后台设置的用户名和密码</p>
        {justChangedPassword && (
          <p className="mt-2 text-center text-sm text-emerald-400">密码已修改，请使用新密码登录。</p>
        )}
        <form onSubmit={handleSubmit} className="mt-6 space-y-4">
          <div>
            <label className="mb-1 block text-xs text-zinc-500">用户名</label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
              className="w-full rounded-md border border-zinc-600 bg-zinc-800 px-3 py-2 text-sm text-zinc-200 placeholder-zinc-500"
              placeholder="admin"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-zinc-500">密码</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              className="w-full rounded-md border border-zinc-600 bg-zinc-800 px-3 py-2 text-sm text-zinc-200 placeholder-zinc-500"
              placeholder=""
            />
          </div>
          {error && <p className="text-sm text-red-400">{error}</p>}
          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-md border border-zinc-600 bg-zinc-700 py-2 text-sm font-medium text-zinc-100 hover:bg-zinc-600 disabled:opacity-50"
          >
            {loading ? "登录中…" : "登录"}
          </button>
        </form>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<div className="flex min-h-screen items-center justify-center bg-zinc-950 text-zinc-500">加载中…</div>}>
      <LoginForm />
    </Suspense>
  );
}
