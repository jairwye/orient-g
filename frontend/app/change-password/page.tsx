"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { clearAuthToken, getAuthHeaders } from "../lib/auth";

export default function ChangePasswordPage() {
  const router = useRouter();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    const newP = newPassword.trim();
    if (!newP) {
      setError("新密码不能为空");
      return;
    }
    if (newP === "123456") {
      setError("新密码不能为默认密码 123456，请设置其他密码");
      return;
    }
    if (newP !== confirmPassword.trim()) {
      setError("两次输入的新密码不一致");
      return;
    }
    setLoading(true);
    try {
      const res = await fetch("/api/auth/change-password", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        credentials: "include",
        body: JSON.stringify({
          current_password: currentPassword,
          new_password: newP,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (res.ok && data.ok) {
        clearAuthToken();
        await fetch("/api/auth/logout", { method: "POST", credentials: "include" });
        router.replace("/login?changed=1");
        return;
      }
      setError(typeof data.detail === "string" ? data.detail : "修改失败，请重试");
    } catch {
      setError("网络错误，请确认后端已启动");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-zinc-950">
      <div className="w-full max-w-sm rounded-lg border border-zinc-800 bg-zinc-900/80 p-6 shadow-xl">
        <h1 className="text-center text-lg font-medium text-zinc-100">修改密码</h1>
        <p className="mt-1 text-center text-sm text-zinc-500">首次登录或使用默认密码后需修改密码</p>
        <form onSubmit={handleSubmit} className="mt-6 space-y-4">
          <div>
            <label className="mb-1 block text-xs text-zinc-500">当前密码</label>
            <input
              type="password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              autoComplete="current-password"
              className="w-full rounded-md border border-zinc-600 bg-zinc-800 px-3 py-2 text-sm text-zinc-200 placeholder-zinc-500"
              placeholder=""
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-zinc-500">新密码</label>
            <input
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              autoComplete="new-password"
              className="w-full rounded-md border border-zinc-600 bg-zinc-800 px-3 py-2 text-sm text-zinc-200 placeholder-zinc-500"
              placeholder=""
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-zinc-500">确认新密码</label>
            <input
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              autoComplete="new-password"
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
            {loading ? "提交中…" : "确认修改"}
          </button>
        </form>
      </div>
    </div>
  );
}
