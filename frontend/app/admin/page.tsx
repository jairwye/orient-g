"use client";

import { useRef, useState } from "react";
import Link from "next/link";

export default function AdminPage() {
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [month, setMonth] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

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
        throw new Error(typeof err.detail === "string" ? err.detail : "上传失败");
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

  return (
    <div className="p-6 md:p-8">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-100">经营数据上传（后台）</h1>
        <p className="mt-1 text-sm text-zinc-500">仅供财务人员使用。上传 Excel 后，展示页将读取该数据。表格每月更新，可填写月份便于后续按月份展示。</p>
        <p className="mt-2">
          <Link href="/" className="text-sm text-zinc-400 hover:text-zinc-300">
            返回经营数据展示页
          </Link>
        </p>
      </div>

      <div className="max-w-md rounded-lg border border-zinc-800 bg-zinc-900/50 p-6">
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
    </div>
  );
}
