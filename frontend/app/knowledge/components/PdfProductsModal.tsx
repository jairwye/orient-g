"use client";

import { useEffect, useMemo, useState } from "react";

type RagPackage = {
  package_id: string;
  name: string;
  manifest_json?: string | null;
  created_at?: string | null;
  created_by_task_id?: string | null;
};

export function PdfProductsModal({
  open,
  items,
  onClose,
  onDownload,
  onDelete,
  busyPackageId,
}: {
  open: boolean;
  items: RagPackage[];
  onClose: () => void;
  onDownload: (packageId: string, kind: "openwebui" | "cn_kb" | "standard") => void | Promise<void>;
  onDelete: (packageId: string) => void | Promise<void>;
  busyPackageId?: string | null;
}) {
  const [exportKindById, setExportKindById] = useState<Record<string, "openwebui" | "cn_kb" | "standard">>({});
  const [openMenuId, setOpenMenuId] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setOpenMenuId(null);
  }, [open]);

  const sorted = useMemo(() => {
    return [...items].sort((a, b) => (b.created_at || "").localeCompare(a.created_at || ""));
  }, [items]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" role="dialog" aria-modal="true">
      <div className="w-full max-w-4xl rounded-xl border border-zinc-800 bg-zinc-950 shadow-2xl">
        <div className="flex items-center justify-between border-b border-zinc-800 px-5 py-4">
          <div>
            <div className="text-base font-medium text-zinc-100">大 PDF 产物</div>
            <div className="mt-1 text-xs text-zinc-500">这里展示由大 PDF 流程生成的“包”，可按目标平台导出。</div>
          </div>
          <button type="button" onClick={onClose} className="rounded-md border border-zinc-800 bg-zinc-900 px-3 py-1.5 text-sm text-zinc-200 hover:bg-zinc-800">
            关闭
          </button>
        </div>

        <div className="max-h-[70vh] overflow-auto p-5">
          {sorted.length === 0 ? (
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/30 p-6 text-sm text-zinc-400">暂无产物。完成“大 PDF 上传流程”后，这里会出现导出包。</div>
          ) : (
            <div className="space-y-2">
              {sorted.map((it) => {
                const exportKind = exportKindById[it.package_id] || "cn_kb";
                const busy = Boolean(busyPackageId && busyPackageId === it.package_id);
                return (
                  <div key={it.package_id} className="relative rounded-lg border border-zinc-800 bg-zinc-900/30 px-3 py-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="min-w-[220px]">
                        <div className="text-sm font-medium text-zinc-100">{it.name || "未命名包"}</div>
                        <div className="mt-1 text-xs text-zinc-500">
                          <span>package_id: {it.package_id}</span>
                          {it.created_at ? <span className="ml-2">创建: {String(it.created_at).replace("T", " ").slice(0, 19)}</span> : null}
                        </div>
                      </div>

                      <div className="flex items-center gap-2">
                        <select
                          value={exportKind}
                          onChange={(e) => setExportKindById((m) => ({ ...m, [it.package_id]: e.target.value as any }))}
                          className="rounded-md border border-zinc-800 bg-zinc-950 px-2 py-1.5 text-sm text-zinc-200"
                          disabled={busy}
                        >
                          <option value="cn_kb">中文知识库（推荐）</option>
                          <option value="standard">标准（通用）</option>
                          <option value="openwebui">OpenWebUI</option>
                        </select>

                        <button
                          type="button"
                          onClick={() => setOpenMenuId((cur) => (cur === it.package_id ? null : it.package_id))}
                          className="rounded-md border border-zinc-800 bg-zinc-950 px-2 py-1.5 text-sm text-zinc-200 hover:bg-zinc-900"
                          disabled={busy}
                          aria-label="更多操作"
                        >
                          …
                        </button>
                      </div>
                    </div>

                    {openMenuId === it.package_id ? (
                      <div className="absolute right-3 top-[52px] z-10 w-48 overflow-hidden rounded-md border border-zinc-800 bg-zinc-950 shadow-xl">
                        <button
                          type="button"
                          className="block w-full px-3 py-2 text-left text-sm text-zinc-200 hover:bg-zinc-900"
                          onClick={() => {
                            setOpenMenuId(null);
                            void onDownload(it.package_id, exportKind);
                          }}
                          disabled={busy}
                        >
                          下载导出包
                        </button>
                        <button
                          type="button"
                          className="block w-full px-3 py-2 text-left text-sm text-red-300 hover:bg-zinc-900"
                          onClick={() => {
                            setOpenMenuId(null);
                            void onDelete(it.package_id);
                          }}
                          disabled={busy}
                        >
                          删除产物
                        </button>
                      </div>
                    ) : null}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

