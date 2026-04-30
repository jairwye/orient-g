"use client";

import { deleteSemanticsForContext } from "../lib/selection_context";

export function BulkPanel(props: {
  count: number;
  source_folder_id: string | null | undefined;
  onMove: () => void;
  onCopy: () => void;
  onDelete: () => void;
  onClear: () => void;
}) {
  const semantics = deleteSemanticsForContext(props.source_folder_id);
  const deleteLabel = semantics.kind === "unlink_from_folder" ? "批量从文件夹移除" : "批量删除";

  return (
    <section className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-6">
      <h2 className="text-lg font-medium text-zinc-200">批量操作</h2>
      <div className="mt-2 text-sm text-zinc-400">已选 {props.count} 条</div>

      <div className="mt-4 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={props.onMove}
          className="rounded border border-zinc-700 bg-zinc-900 px-3 py-1.5 text-xs text-zinc-200 hover:bg-zinc-800"
        >
          移动到…
        </button>
        <button
          type="button"
          onClick={props.onCopy}
          className="rounded border border-zinc-700 bg-zinc-900 px-3 py-1.5 text-xs text-zinc-200 hover:bg-zinc-800"
        >
          复制到…
        </button>
        <button
          type="button"
          onClick={props.onDelete}
          className="rounded border border-red-900/50 bg-red-950/30 px-3 py-1.5 text-xs text-red-300/90 hover:bg-red-950/50"
        >
          {deleteLabel}
        </button>
        <button
          type="button"
          onClick={props.onClear}
          className="rounded border border-zinc-700 bg-zinc-900 px-3 py-1.5 text-xs text-zinc-200 hover:bg-zinc-800"
        >
          清空选择
        </button>
      </div>
    </section>
  );
}

