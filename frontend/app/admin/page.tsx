"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";

const DEFAULT_ADMIN_PATH = "/admin";

export default function AdminPage() {
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [month, setMonth] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [adminPath, setAdminPath] = useState(DEFAULT_ADMIN_PATH);
  const [adminPathEdit, setAdminPathEdit] = useState(DEFAULT_ADMIN_PATH);
  const [pathSaving, setPathSaving] = useState(false);
  const [pathMessage, setPathMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  const [users, setUsers] = useState<{ username: string }[]>([]);
  const [newUsername, setNewUsername] = useState("");
  const [userAddLoading, setUserAddLoading] = useState(false);
  const [userAddMessage, setUserAddMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [resettingUser, setResettingUser] = useState<string | null>(null);
  const [deletingUser, setDeletingUser] = useState<string | null>(null);

  const [authEnabled, setAuthEnabled] = useState(false);
  const [authEnabledEdit, setAuthEnabledEdit] = useState(false);
  const [authSaveLoading, setAuthSaveLoading] = useState(false);
  const [authSaveMessage, setAuthSaveMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  useEffect(() => {
    fetch("/api/settings", { credentials: "include" })
      .then((r) => r.ok ? r.json() : { admin_path: DEFAULT_ADMIN_PATH, users: [{ username: "admin" }], auth_enabled: false })
      .then((data: { admin_path?: string; users?: { username: string }[]; auth_enabled?: boolean }) => {
        const p = data.admin_path ?? DEFAULT_ADMIN_PATH;
        setAdminPath(p);
        setAdminPathEdit(p);
        setUsers(data.users ?? [{ username: "admin" }]);
        const ae = !!data.auth_enabled;
        setAuthEnabled(ae);
        setAuthEnabledEdit(ae);
      })
      .catch(() => {});
  }, []);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = "";
    setMessage(null);
    setUploading(true);
    try {
      const form = new FormData();
      form.append("file", file);
      if (month) form.append("month", month);
      const res = await fetch("/api/business/upload", {
        method: "POST",
        body: form,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        const msg = (Array.isArray(err.detail) ? err.detail[0]?.msg : undefined) ?? (typeof err.detail === "string" ? err.detail : undefined);
        throw new Error(msg ?? "上传失败");
      }
      setMessage({ type: "success", text: "已上传，经营数据展示页将显示最新数据。" });
    } catch (err) {
      setMessage({
        type: "error",
        text: err instanceof Error ? err.message : "上传失败，请重试",
      });
    } finally {
      setUploading(false);
    }
  };

  const handleSaveAdminPath = async () => {
    let path = adminPathEdit.trim();
    if (!path.startsWith("/")) path = "/" + path;
    if (!/^\/[a-zA-Z0-9_]+$/.test(path)) {
      setPathMessage({ type: "error", text: "路径须为单段，仅含字母、数字、下划线，如 /admin" });
      return;
    }
    setPathSaving(true);
    setPathMessage(null);
    try {
      const res = await fetch("/api/settings", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ admin_path: path }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const msg = (Array.isArray(data.detail) ? data.detail[0]?.msg : undefined) ?? (typeof data.detail === "string" ? data.detail : undefined);
        throw new Error(msg ?? `保存失败（${res.status}）`);
      }
      setAdminPath(data.admin_path);
      setAdminPathEdit(data.admin_path);
      setPathMessage({ type: "success", text: "后台路径已保存。新路径生效后，请使用新地址访问本页。" });
    } catch (err) {
      const text = err instanceof Error ? err.message : "保存失败，请重试";
      setPathMessage({
        type: "error",
        text: text.startsWith("Failed to fetch") || text === "NetworkError when fetching resource" ? "无法连接后端，请确认后端已启动（uvicorn backend.main:app --reload）" : text,
      });
    } finally {
      setPathSaving(false);
    }
  };

  const handleSaveAuthEnabled = async () => {
    setAuthSaveLoading(true);
    setAuthSaveMessage(null);
    try {
      const res = await fetch("/api/settings", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ auth_enabled: authEnabledEdit }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const msg = (Array.isArray(data.detail) ? data.detail[0]?.msg : undefined) ?? (typeof data.detail === "string" ? data.detail : undefined);
        throw new Error(msg ?? "保存失败");
      }
      setAuthEnabled(data.auth_enabled ?? authEnabledEdit);
      setAuthEnabledEdit(data.auth_enabled ?? authEnabledEdit);
      setAuthSaveMessage({ type: "success", text: data.auth_enabled ? "已启用页面登录，未登录用户将跳转至登录页。" : "已关闭页面登录。" });
    } catch (err) {
      setAuthSaveMessage({
        type: "error",
        text: err instanceof Error ? err.message : "保存失败，请重试",
      });
    } finally {
      setAuthSaveLoading(false);
    }
  };

  const handleAddUser = async () => {
    const username = newUsername.trim();
    if (!username) {
      setUserAddMessage({ type: "error", text: "请输入用户名" });
      return;
    }
    if (!/^[a-zA-Z0-9_]+$/.test(username)) {
      setUserAddMessage({ type: "error", text: "用户名仅允许字母、数字、下划线" });
      return;
    }
    setUserAddLoading(true);
    setUserAddMessage(null);
    try {
      const res = await fetch("/api/settings/users", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ username }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const msg = typeof data.detail === "string" ? data.detail : "添加失败";
        throw new Error(msg);
      }
      setUsers((prev) => [...prev, { username: data.username ?? username }]);
      setNewUsername("");
      setUserAddMessage({ type: "success", text: "已添加用户，默认密码为 123456，首次登录须修改密码。" });
    } catch (err) {
      setUserAddMessage({
        type: "error",
        text: err instanceof Error ? err.message : "添加失败，请重试",
      });
    } finally {
      setUserAddLoading(false);
    }
  };

  const handleResetPassword = async (username: string) => {
    setResettingUser(username);
    try {
      const res = await fetch("/api/settings/users/reset-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ username }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const msg = typeof data.detail === "string" ? data.detail : "重设失败";
        throw new Error(msg);
      }
      setUserAddMessage({ type: "success", text: `已将用户「${username}」的密码重设为 123456，该用户下次登录须修改密码。` });
    } catch (err) {
      setUserAddMessage({
        type: "error",
        text: err instanceof Error ? err.message : "重设失败，请重试",
      });
    } finally {
      setResettingUser(null);
    }
  };

  const handleDeleteUser = async (username: string) => {
    if (!confirm(`确定要删除用户「${username}」吗？`)) return;
    setDeletingUser(username);
    setUserAddMessage(null);
    try {
      const res = await fetch("/api/settings/users", {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ username }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const msg = typeof data.detail === "string" ? data.detail : "删除失败";
        throw new Error(msg);
      }
      setUsers((prev) => prev.filter((u) => u.username.toLowerCase() !== username.toLowerCase()));
      setUserAddMessage({ type: "success", text: `已删除用户「${username}」。` });
    } catch (err) {
      setUserAddMessage({
        type: "error",
        text: err instanceof Error ? err.message : "删除失败，请重试",
      });
    } finally {
      setDeletingUser(null);
    }
  };

  return (
    <div className="p-6 md:p-8">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-100">管理后台</h1>
        <p className="mt-1 text-sm text-zinc-500">上传经营数据、管理用户与登录设置。</p>
        <p className="mt-2">
          <Link href="/" className="text-sm text-zinc-400 hover:text-zinc-300">
            返回经营数据展示页
          </Link>
        </p>
      </div>

      {/* 1. 上传经营数据 Excel */}
      <div className="mb-6 max-w-md rounded-lg border border-zinc-800 bg-zinc-900/50 p-6">
        <h2 className="mb-3 text-sm font-medium text-zinc-300">上传经营数据</h2>
        <p className="mb-3 text-xs text-zinc-500">上传 Excel 后，展示页将读取该数据。可填写月份便于后续按月份展示。</p>
        <div className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium text-zinc-400">月份（可选，格式 YYYY-MM）</label>
            <input
              type="text"
              placeholder="如 2025-03"
              value={month}
              onChange={(e) => setMonth(e.target.value)}
              className="w-full rounded-md border border-zinc-600 bg-zinc-800 px-3 py-2 text-sm text-zinc-200 placeholder-zinc-500"
            />
          </div>
          <div>
            <input
              ref={fileInputRef}
              type="file"
              accept=".xlsx,.xls"
              className="hidden"
              onChange={handleUpload}
              disabled={uploading}
            />
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading}
              className="rounded-md border border-zinc-600 bg-zinc-800 px-4 py-2 text-sm text-zinc-200 hover:bg-zinc-700 disabled:opacity-50"
            >
              {uploading ? "上传中…" : "选择并上传 Excel"}
            </button>
          </div>
          {message && (
            <p className={message.type === "success" ? "text-sm text-emerald-400" : "text-sm text-red-400"}>
              {message.text}
            </p>
          )}
        </div>
      </div>

      {/* 2. 用户管理 */}
      <div className="mb-6 max-w-md rounded-lg border border-zinc-800 bg-zinc-900/50 p-6">
        <h2 className="mb-3 text-sm font-medium text-zinc-300">用户管理</h2>
        <p className="mb-3 text-xs text-zinc-500">新增用户仅需填写用户名，默认密码为 123456；首次登录须修改密码。忘记密码可重设为默认密码；删除后该用户无法再登录。</p>
        <div className="space-y-4">
          <div>
            <h3 className="mb-2 text-xs font-medium text-zinc-500">现有用户</h3>
            {users.length === 0 ? (
              <p className="text-sm text-zinc-500">暂无用户</p>
            ) : (
              <ul className="space-y-2">
                {users.map((u) => (
                  <li key={u.username} className="flex items-center justify-between gap-2 rounded-md border border-zinc-700 bg-zinc-800/50 px-3 py-2">
                    <span className="text-sm text-zinc-200">{u.username}</span>
                    <div className="flex items-center gap-1">
                      <button
                        type="button"
                        onClick={() => handleResetPassword(u.username)}
                        disabled={resettingUser !== null}
                        className="rounded border border-zinc-600 bg-zinc-700 px-2 py-1 text-xs text-zinc-200 hover:bg-zinc-600 disabled:opacity-50"
                      >
                        {resettingUser === u.username ? "处理中…" : "重设为默认密码"}
                      </button>
                      <button
                        type="button"
                        onClick={() => handleDeleteUser(u.username)}
                        disabled={deletingUser !== null || users.length <= 1}
                        title={users.length <= 1 ? "至少保留一名用户" : "删除该用户"}
                        className="rounded border border-red-900/60 bg-red-900/30 px-2 py-1 text-xs text-red-300 hover:bg-red-900/50 disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        {deletingUser === u.username ? "删除中…" : "删除"}
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div>
            <h3 className="mb-2 text-xs font-medium text-zinc-500">新增用户</h3>
            <div className="flex flex-wrap items-end gap-2">
              <div className="min-w-[140px]">
                <label className="mb-1 block text-xs text-zinc-500">用户名</label>
                <input
                  type="text"
                  value={newUsername}
                  onChange={(e) => setNewUsername(e.target.value)}
                  placeholder="字母、数字、下划线"
                  className="w-full rounded-md border border-zinc-600 bg-zinc-800 px-3 py-2 text-sm text-zinc-200 placeholder-zinc-500"
                />
              </div>
              <button
                type="button"
                onClick={handleAddUser}
                disabled={userAddLoading}
                className="rounded-md border border-zinc-600 bg-zinc-800 px-4 py-2 text-sm text-zinc-200 hover:bg-zinc-700 disabled:opacity-50"
              >
                {userAddLoading ? "添加中…" : "添加用户"}
              </button>
            </div>
          </div>
        </div>
        {userAddMessage && (
          <p className={`mt-2 text-sm ${userAddMessage.type === "success" ? "text-emerald-400" : "text-red-400"}`}>
            {userAddMessage.text}
          </p>
        )}
      </div>

      {/* 3. 设置后台路径 */}
      <div className="mb-6 max-w-md rounded-lg border border-zinc-800 bg-zinc-900/50 p-6">
        <h2 className="mb-3 text-sm font-medium text-zinc-300">设置后台路径</h2>
        <p className="mb-3 text-xs text-zinc-500">默认路径为 /admin，可修改为仅含字母、数字、下划线的单段路径。修改保存后，请使用新路径访问本页。</p>
        <div className="flex flex-wrap items-end gap-2">
          <div className="min-w-[120px]">
            <label className="mb-1 block text-xs text-zinc-500">当前路径</label>
            <input
              type="text"
              value={adminPathEdit}
              onChange={(e) => setAdminPathEdit(e.target.value)}
              placeholder="/admin"
              className="w-full rounded-md border border-zinc-600 bg-zinc-800 px-3 py-2 text-sm text-zinc-200 placeholder-zinc-500"
            />
          </div>
          <button
            type="button"
            onClick={handleSaveAdminPath}
            disabled={pathSaving}
            className="rounded-md border border-zinc-600 bg-zinc-800 px-4 py-2 text-sm text-zinc-200 hover:bg-zinc-700 disabled:opacity-50"
          >
            {pathSaving ? "保存中…" : "保存路径"}
          </button>
        </div>
        {pathMessage && (
          <p className={`mt-2 text-sm ${pathMessage.type === "success" ? "text-emerald-400" : "text-red-400"}`}>
            {pathMessage.text}
          </p>
        )}
      </div>

      {/* 4. 启用登录 */}
      <div className="max-w-md rounded-lg border border-zinc-800 bg-zinc-900/50 p-6">
        <h2 className="mb-3 text-sm font-medium text-zinc-300">启用页面登录</h2>
        <p className="mb-3 text-xs text-zinc-500">开启后，访问本项目任意页面均需先使用上述用户管理中的账号登录。</p>
        <div className="flex flex-wrap items-center gap-3">
          <label className="flex cursor-pointer items-center gap-2">
            <input
              type="checkbox"
              checked={authEnabledEdit}
              onChange={(e) => setAuthEnabledEdit(e.target.checked)}
              className="h-4 w-4 rounded border-zinc-600 bg-zinc-800 text-zinc-200"
            />
            <span className="text-sm text-zinc-300">启用本项目页面需要用户名密码登录</span>
          </label>
          <button
            type="button"
            onClick={handleSaveAuthEnabled}
            disabled={authSaveLoading}
            className="rounded-md border border-zinc-600 bg-zinc-800 px-4 py-2 text-sm text-zinc-200 hover:bg-zinc-700 disabled:opacity-50"
          >
            {authSaveLoading ? "保存中…" : "保存"}
          </button>
        </div>
        {authSaveMessage && (
          <p className={`mt-2 text-sm ${authSaveMessage.type === "success" ? "text-emerald-400" : "text-red-400"}`}>
            {authSaveMessage.text}
          </p>
        )}
      </div>
    </div>
  );
}
