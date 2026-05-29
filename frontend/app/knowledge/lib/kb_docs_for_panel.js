/**
 * 知识库右栏文档列表：按选中上下文（文件夹 / 知识库 kind）解析应展示的文档行。
 */
import { isUnfiledPrivateDoc } from "./private_root_docs.js";

const KB_KIND_PRIVATE = "Private";

/**
 * @param {Array<{ doc_id: string; original_filename?: string; title?: string; created_at?: string | null; folder_ids?: string[]; status?: string }>} myDocs
 * @param {Set<string>} visibleFolderIds
 * @param {{ includeRunning?: boolean; docDedupeKey?: (d: object) => string; parseTimeMs?: (iso?: string | null) => number }} [opts]
 */
export function pickPrivateRootDocs(myDocs, visibleFolderIds, opts = {}) {
  const includeRunning = opts.includeRunning !== false;
  const docDedupeKey =
    opts.docDedupeKey ||
    ((d) => {
      const n = String(d.original_filename || d.title || "").trim();
      return n || String(d.doc_id || "");
    });
  const parseTimeMs =
    opts.parseTimeMs ||
    ((iso) => {
      if (!iso) return 0;
      const t = Date.parse(iso);
      return Number.isFinite(t) ? t : 0;
    });

  const candidates = (myDocs || []).filter((d) =>
    isUnfiledPrivateDoc(d, visibleFolderIds, { includeRunning }),
  );
  const best = new Map();
  for (const d of candidates) {
    const k = docDedupeKey(d);
    const prev = best.get(k);
    if (!prev) {
      best.set(k, d);
      continue;
    }
    if (parseTimeMs(d.created_at) >= parseTimeMs(prev.created_at)) best.set(k, d);
  }
  return Array.from(best.values()).sort(
    (a, b) => parseTimeMs(b.created_at) - parseTimeMs(a.created_at),
  );
}

/**
 * @param {Array<{ doc_id: string; title?: string; original_filename?: string; size_bytes?: number; status?: string; last_error?: string | null; created_at?: string | null }>} docs
 */
export function toFolderDetailDocRows(docs) {
  return (docs || []).map((d) => ({
    doc_id: String(d.doc_id || ""),
    title: String(d.title || ""),
    original_filename: d.original_filename,
    size_bytes: d.size_bytes,
    status: d.status,
    last_error: d.last_error ?? null,
    created_at: d.created_at ?? null,
  }));
}

/**
 * @param {{
 *   selectionKind: "kb" | "folder";
 *   activeKbKind: string;
 *   folderDocs?: Array<object>;
 *   privateRootDocs?: Array<object>;
 *   myDocs?: Array<object>;
 *   folders?: Array<{ folder_id?: string; kind?: string | null }>;
 *   docIsActive?: (status?: string) => boolean;
 *   docIsRunning?: (d: { status?: string }) => boolean;
 * }} input
 */
export function resolveDocsForActiveKb(input) {
  const {
    selectionKind,
    activeKbKind,
    folderDocs = [],
    privateRootDocs = [],
    myDocs = [],
    folders = [],
    docIsActive = (s) => String(s || "").toLowerCase() === "active",
    docIsRunning = () => false,
  } = input;

  if (selectionKind === "folder") return folderDocs || [];

  const kind = String(activeKbKind || KB_KIND_PRIVATE).trim() || KB_KIND_PRIVATE;
  if (kind === KB_KIND_PRIVATE) {
    return toFolderDetailDocRows(privateRootDocs);
  }

  const folderKindById = new Map();
  for (const f of folders || []) {
    folderKindById.set(String(f.folder_id || ""), String(f.kind || KB_KIND_PRIVATE).trim() || KB_KIND_PRIVATE);
  }

  const out = [];
  for (const d of myDocs || []) {
    const docId = String(d.doc_id || "").trim();
    if (!docId) continue;
    const status = String(d.status || "");
    if (!docIsActive(status) && !docIsRunning({ status })) continue;
    const fids = Array.isArray(d.folder_ids) ? d.folder_ids : [];
    const inKind = fids.some((fid) => (folderKindById.get(String(fid)) || KB_KIND_PRIVATE) === kind);
    if (!inKind) continue;
    out.push({
      doc_id: docId,
      title: String(d.title || ""),
      original_filename: d.original_filename,
      size_bytes: d.size_bytes,
      status: d.status,
      last_error: d.last_error ?? null,
      created_at: d.created_at ?? null,
    });
  }
  out.sort((a, b) => {
    const ta = Date.parse(String(a.created_at || "")) || 0;
    const tb = Date.parse(String(b.created_at || "")) || 0;
    return tb - ta;
  });
  return out;
}

export function isPrivateKbRootSelection(selectionKind, activeKbKind) {
  return selectionKind === "kb" && String(activeKbKind || "").trim() === KB_KIND_PRIVATE;
}
