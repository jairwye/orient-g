"use client";

export type DocDetailPanelDoc = {
  doc_id: string;
  title?: string;
  original_filename?: string;
  statusText?: string;
};

export function DocDetailPanel(props: {
  doc: DocDetailPanelDoc;
  onMove: () => void;
  onCopy: () => void;
  onDelete: () => void;
}) {
  const name = (props.doc.original_filename || props.doc.title || "").trim() || "(无文件名)";
  const shortId = props.doc.doc_id.length > 12 ? `${props.doc.doc_id.slice(0, 12)}…` : props.doc.doc_id;

  return (
    <section className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-6">
      <h2 className="text-lg font-medium text-zinc-200">文档详情</h2>

      <div className="mt-3 space-y-2 text-sm">
        <div className="text-zinc-200 truncate" title={name}>
          {name}
        </div>
        <div className="text-xs text-zinc-500 font-mono" title={props.doc.doc_id}>
          {shortId}
        </div>
        <div className="text-xs text-zinc-500">{props.doc.statusText || "—"}</div>
      </div>

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
          删除
        </button>
      </div>
    </section>
  );
}

