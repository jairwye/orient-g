"use client";

import { useMemo, useState } from "react";

type FolderItem = { folder_id: string; name: string; kind?: string | null };

export function MoveCopyModal(props: {
  open: boolean;
  mode: "move" | "copy";
  docId: string;
  count: number;
  foldersByKind: Map<string, FolderItem[]>;
  kbKindLabelById: Map<string, string>;
  kbKind: string;
  folderId: string;
  onChangeKbKind: (v: string) => void;
  onChangeFolderId: (v: string) => void;
  onClose: () => void;
  onConfirm: (targetFolderId: string) => void | Promise<void>;
}) {
  const {
    open,
    mode,
    docId,
    count,
    foldersByKind,
    kbKindLabelById,
    kbKind,
    folderId,
    onChangeKbKind,
    onChangeFolderId,
    onClose,
    onConfirm,
  } = props;

  const [query, setQuery] = useState("");

  const kindFolders = useMemo(() => {
    const arr = foldersByKind.get(kbKind) || [];
    const q = query.trim().toLowerCase();
    if (!q) return arr;
    return arr.filter((f) => String(f.name || "").toLowerCase().includes(q) || String(f.folder_id || "").toLowerCase().includes(q));
  }, [foldersByKind, kbKind, query]);

  const folderName = useMemo(() => {
    if (!kbKind || !folderId) return "";
    const arr = foldersByKind.get(kbKind) || [];
    const hit = arr.find((x) => x.folder_id === folderId);
    return (hit?.name || "").trim() || folderId;
  }, [folderId, foldersByKind, kbKind]);

  if (!open) return null;

  const title = mode === "move" ? "移动到…" : "复制到…";
  const hint = folderId ? `将把 ${Math.max(1, count)} 条文档${mode === "move" ? "移动" : "复制"}到「${folderName}」。` : "";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="w-full max-w-md rounded-xl border border-zinc-800 bg-zinc-950 p-4 shadow-[0_30px_90px_rgba(0,0,0,0.6)]">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="text-sm font-medium text-zinc-200">{title}</div>
            <div className="mt-1 text-xs text-zinc-500 font-mono">{docId}</div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-zinc-800 bg-zinc-950/40 px-3 py-1 text-xs text-zinc-200 hover:bg-zinc-900/60"
          >
            关闭
          </button>
        </div>

        <div className="mt-3 space-y-3 text-sm">
          <div>
            <div className="mb-1 text-xs text-zinc-500">目标知识库</div>
            <select
              className="w-full rounded border border-zinc-700 bg-zinc-900 px-2 py-2 text-sm text-zinc-200"
              value={kbKind}
              onChange={(e) => {
                onChangeKbKind(e.target.value);
                setQuery("");
              }}
            >
              <option value="">请选择…</option>
              {Array.from(foldersByKind.keys()).map((kid) => (
                <option key={kid} value={kid}>
                  {kbKindLabelById.get(kid) || kid}
                </option>
              ))}
            </select>
          </div>

          <div>
            <div className="mb-1 text-xs text-zinc-500">目标文件夹</div>
            <input
              className="mb-2 w-full rounded border border-zinc-700 bg-zinc-900 px-2 py-2 text-sm text-zinc-200 placeholder:text-zinc-600"
              placeholder={kbKind ? "搜索文件夹…" : "请先选择知识库"}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              disabled={!kbKind}
            />
            <select
              className="w-full rounded border border-zinc-700 bg-zinc-900 px-2 py-2 text-sm text-zinc-200"
              value={folderId}
              onChange={(e) => onChangeFolderId(e.target.value)}
              disabled={!kbKind}
            >
              <option value="">{kbKind ? "请选择…" : "请先选择知识库"}</option>
              {kindFolders.map((f) => (
                <option key={f.folder_id} value={f.folder_id}>
                  {f.name}
                </option>
              ))}
            </select>
            {hint ? <div className="mt-2 text-xs text-zinc-500">{hint}</div> : null}
          </div>

          <div className="flex items-center justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-zinc-800 bg-zinc-950/40 px-3 py-1.5 text-xs text-zinc-200 hover:bg-zinc-900/60"
            >
              取消
            </button>
            <button
              type="button"
              disabled={!folderId}
              onClick={() => {
                const target = folderId;
                if (!target) return;
                void onConfirm(target);
              }}
              className="rounded-lg bg-zinc-200 px-3 py-1.5 text-xs font-medium text-zinc-900 hover:bg-white disabled:opacity-50"
            >
              确认
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

