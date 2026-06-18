"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { PageDevInProgressNotice } from "../components/PageDevInProgressNotice";
import { getAuthHeaders } from "../lib/auth";

type ContractListItem = {
  contract_id: string;
  doc_id: string;
  original_filename: string;
  status: string;
  created_at?: string | null;
};

export default function ContractsPage() {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ type: "info" | "success" | "error"; text: string } | null>(null);
  const [items, setItems] = useState<ContractListItem[]>([]);

  const load = async () => {
    try {
      const res = await fetch("/api/contracts/list", { credentials: "include", headers: getAuthHeaders() });
      const data = (await res.json().catch(() => ({}))) as { items?: ContractListItem[] };
      if (res.ok) setItems(Array.isArray(data.items) ? data.items : []);
    } catch {
      // ignore
    }
  };

  useEffect(() => {
    load();
  }, []);

  const upload = async (f: File) => {
    setBusy(true);
    setMsg(null);
    try {
      const fd = new FormData();
      fd.append("file", f);
      const res = await fetch("/api/contracts/upload", {
        method: "POST",
        credentials: "include",
        headers: getAuthHeaders(),
        body: fd,
      });
      const data = (await res.json().catch(() => ({}))) as { detail?: string };
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "上传失败");
      setMsg({ type: "success", text: "已上传并生成台账（字段后续细化）。" });
      await load();
    } catch (e) {
      setMsg({ type: "error", text: e instanceof Error ? e.message : "上传失败" });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="p-6 md:p-8">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-100">合同台账</h1>
        <p className="mt-1 text-sm text-zinc-500">上传 PDF 合同（含图片/扫描件），系统会解析并生成台账记录，同时归入“合同管理”知识库文件夹供 AI 问答。</p>
        <div className="mt-3 max-w-3xl">
          <PageDevInProgressNotice>
            台账字段解析、检索与 AI 写入链路仍在完善。
          </PageDevInProgressNotice>
        </div>
      </div>

      <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-6">
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,application/pdf"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            e.target.value = "";
            if (f) upload(f);
          }}
        />

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            disabled={busy}
            onClick={() => fileInputRef.current?.click()}
            className="rounded border border-zinc-600 bg-zinc-800 px-3 py-2 text-sm text-zinc-200 hover:bg-zinc-700 disabled:opacity-50"
          >
            {busy ? "上传中…" : "上传合同 PDF"}
          </button>
          {msg && (
            <span className={msg.type === "error" ? "text-red-400 text-sm" : msg.type === "success" ? "text-emerald-400 text-sm" : "text-zinc-400 text-sm"}>
              {msg.text}
            </span>
          )}
          <Link href="/ai-interaction" className="ml-auto rounded border border-zinc-600 bg-zinc-800 px-3 py-2 text-sm text-zinc-200 hover:bg-zinc-700">
            去 AI内网
          </Link>
        </div>

        <div className="mt-6">
          <h2 className="mb-2 text-sm font-medium text-zinc-200">我的台账</h2>
          {items.length === 0 ? (
            <p className="text-sm text-zinc-500">暂无记录。</p>
          ) : (
            <div className="divide-y divide-zinc-800 rounded border border-zinc-800">
              {items.map((it) => (
                <div key={it.contract_id} className="flex flex-wrap items-center justify-between gap-2 p-3">
                  <div className="min-w-0">
                    <div className="truncate text-sm text-zinc-200">{it.original_filename || it.contract_id}</div>
                    <div className="text-xs text-zinc-500">
                      {it.created_at ? it.created_at : ""} · doc: <span className="font-mono">{it.doc_id}</span>
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <Link href={`/contracts/${encodeURIComponent(it.contract_id)}`} className="rounded border border-zinc-700 bg-zinc-800 px-3 py-1.5 text-xs text-zinc-200 hover:bg-zinc-700">
                      详情
                    </Link>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

