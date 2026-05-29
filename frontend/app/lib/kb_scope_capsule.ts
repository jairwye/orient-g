/**
 * 跨页统一：知识库范围「胶囊」—— AI 互动 / 知识库 / 工具页通过同一 key 与 URL 参数互通。
 * 约定：仅当用户显式选择了 folder/collection/table 之一时，后端才走 RAG（方案 B）。
 */

export const KB_SCOPE_CAPSULE_KEY = "orientg.kb_scope_capsule.v1";

export type KbScopeCapsule = {
  folder_ids: string[];
  collection_ids: string[];
  table_ids: string[];
  updated_at?: number;
};

export function emptyKbScopeCapsule(): KbScopeCapsule {
  return { folder_ids: [], collection_ids: [], table_ids: [] };
}

function uniq(ids: string[]): string[] {
  const s = new Set<string>();
  for (const x of ids) {
    const t = (x || "").trim();
    if (t) s.add(t);
  }
  return Array.from(s);
}

export function readKbScopeCapsule(): KbScopeCapsule | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(KB_SCOPE_CAPSULE_KEY);
    if (!raw) return null;
    const o = JSON.parse(raw) as unknown;
    if (!o || typeof o !== "object") return null;
    const rec = o as Record<string, unknown>;
    return {
      folder_ids: uniq(Array.isArray(rec.folder_ids) ? (rec.folder_ids as string[]) : []),
      collection_ids: uniq(Array.isArray(rec.collection_ids) ? (rec.collection_ids as string[]) : []),
      table_ids: uniq(Array.isArray(rec.table_ids) ? (rec.table_ids as string[]) : []),
      updated_at: typeof rec.updated_at === "number" ? rec.updated_at : Date.now(),
    };
  } catch {
    return null;
  }
}

export function writeKbScopeCapsule(next: KbScopeCapsule): void {
  if (typeof window === "undefined") return;
  const payload: KbScopeCapsule = {
    folder_ids: uniq(next.folder_ids),
    collection_ids: uniq(next.collection_ids),
    table_ids: uniq(next.table_ids),
    updated_at: Date.now(),
  };
  try {
    localStorage.setItem(KB_SCOPE_CAPSULE_KEY, JSON.stringify(payload));
  } catch {
    // ignore
  }
}

/** 从 URL 解析范围（支持 folder_id 单参或 folders、collections、tables 逗号分隔） */
export function parseKbScopeFromSearchParams(sp: URLSearchParams): Partial<KbScopeCapsule> {
  const out: Partial<KbScopeCapsule> = {};
  const fid = (sp.get("folder_id") || "").trim();
  const foldersRaw = (sp.get("folders") || "").trim();
  if (fid) out.folder_ids = [fid];
  else if (foldersRaw) out.folder_ids = uniq(foldersRaw.split(","));
  const cols = (sp.get("collections") || "").trim();
  if (cols) out.collection_ids = uniq(cols.split(","));
  const tabs = (sp.get("tables") || "").trim();
  if (tabs) out.table_ids = uniq(tabs.split(","));
  return out;
}

export function mergeKbScopeCapsule(base: KbScopeCapsule, patch: Partial<KbScopeCapsule>): KbScopeCapsule {
  return {
    folder_ids: uniq([...(base.folder_ids || []), ...(patch.folder_ids || [])]),
    collection_ids: uniq([...(base.collection_ids || []), ...(patch.collection_ids || [])]),
    table_ids: uniq([...(base.table_ids || []), ...(patch.table_ids || [])]),
  };
}

/** URL 显式范围优先，否则回退 localStorage 胶囊（parse 返回 Partial，避免 undefined.length） */
export function resolveKbScopeFromUrlAndCapsule(sp: URLSearchParams): KbScopeCapsule {
  const fromUrl = parseKbScopeFromSearchParams(sp);
  const capsule = readKbScopeCapsule() || emptyKbScopeCapsule();
  return {
    folder_ids: fromUrl.folder_ids?.length ? fromUrl.folder_ids : capsule.folder_ids,
    collection_ids: fromUrl.collection_ids?.length ? fromUrl.collection_ids : capsule.collection_ids,
    table_ids: fromUrl.table_ids?.length ? fromUrl.table_ids : capsule.table_ids,
    updated_at: capsule.updated_at,
  };
}

export function buildAgentHref(scope?: Partial<KbScopeCapsule>): string {
  const q = new URLSearchParams();
  q.set("view", "agent");
  if (scope?.folder_ids?.length === 1) q.set("folder_id", scope.folder_ids[0]);
  else if ((scope?.folder_ids?.length || 0) > 1) q.set("folders", (scope.folder_ids || []).join(","));
  if (scope?.collection_ids?.length) q.set("collections", (scope.collection_ids || []).join(","));
  if (scope?.table_ids?.length) q.set("tables", (scope.table_ids || []).join(","));
  return `/ai-interaction?${q.toString()}`;
}

export function buildAiInteractionHref(scope: Partial<KbScopeCapsule>): string {
  const q = new URLSearchParams();
  if (scope.folder_ids?.length === 1) q.set("folder_id", scope.folder_ids[0]);
  else if ((scope.folder_ids?.length || 0) > 1) q.set("folders", (scope.folder_ids || []).join(","));
  if (scope.collection_ids?.length) q.set("collections", (scope.collection_ids || []).join(","));
  if (scope.table_ids?.length) q.set("tables", (scope.table_ids || []).join(","));
  const qs = q.toString();
  return qs ? `/ai-interaction?${qs}` : "/ai-interaction";
}

export function buildKnowledgeHref(folderId?: string | null): string {
  if (folderId) return `/knowledge?folder_id=${encodeURIComponent(folderId)}`;
  return "/knowledge";
}
