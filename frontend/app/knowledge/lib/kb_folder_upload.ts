/** 与 backend.services.kb_documents.MY_DOC_UPLOAD_MAX_BYTES 保持一致 */
export const KB_MY_DOC_MAX_BYTES = 20 * 1024 * 1024;
export const KB_UPLOAD_CONCURRENCY = 3;
const ENQUEUE_RETRY_DELAYS_MS = [1000, 2000, 4000, 8000];

export type FolderUploadProgress = {
  phase: "hashing" | "checking" | "uploading";
  current: number;
  total: number;
  pct: number;
  label: string;
};

export type FolderUploadOutcome =
  | { status: "created"; filename: string; doc_id: string }
  | { status: "skipped"; filename: string; doc_id: string; reason: string }
  | { status: "rejected"; filename: string; reason: string }
  | { status: "failed"; filename: string; reason: string };

export async function sha256HexFromFile(file: File): Promise<string> {
  const buf = await file.arrayBuffer();
  const hash = await crypto.subtle.digest("SHA-256", buf);
  return [...new Uint8Array(hash)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function parseUploadError(status: number, bodyText: string): string {
  try {
    const data = JSON.parse(bodyText) as { detail?: unknown };
    if (typeof data.detail === "string" && data.detail.trim()) return data.detail;
  } catch {
    /* ignore */
  }
  if (status === 503) return "解析队列已满，请稍后重试";
  if (status === 400) return "文件不符合要求";
  if (status === 403) return "无权限上传到该文件夹";
  return `HTTP ${status}`;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export async function fetchExistingSourceHashes(
  folderId: string,
  sourceHashes: string[],
  headers: Record<string, string>,
): Promise<Record<string, string>> {
  if (!sourceHashes.length) return {};
  const res = await fetch(`/api/knowledge/folders/${encodeURIComponent(folderId)}/existing-source-hashes`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...headers },
    credentials: "include",
    body: JSON.stringify({ source_hashes: sourceHashes }),
  });
  const data = (await res.json().catch(() => ({}))) as { detail?: string; items?: Record<string, string> };
  if (!res.ok) {
    throw new Error(typeof data.detail === "string" ? data.detail : "预检失败");
  }
  return data.items || {};
}

async function uploadOneFile(
  folderId: string,
  file: File,
  sourceHash: string,
  headers: Record<string, string>,
): Promise<FolderUploadOutcome> {
  for (let attempt = 0; attempt <= ENQUEUE_RETRY_DELAYS_MS.length; attempt++) {
    const outcome = await new Promise<FolderUploadOutcome | "__retry__">((resolve) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", "/api/knowledge/my-documents/upload");
      for (const [k, v] of Object.entries(headers)) xhr.setRequestHeader(k, v);
      const form = new FormData();
      form.append("file", file);
      form.append("folder_id", folderId);
      form.append("source_hash", sourceHash);
      xhr.onload = () => {
        const text = xhr.responseText || "";
        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            const d = JSON.parse(text) as {
              doc_id?: string;
              skipped?: boolean;
              skip_reason?: string;
            };
            const docId = String(d.doc_id || "").trim();
            if (d.skipped && docId) {
              resolve({
                status: "skipped",
                filename: file.name,
                doc_id: docId,
                reason: d.skip_reason === "duplicate_hash" ? "内容相同" : "已存在",
              });
              return;
            }
            if (docId) {
              resolve({ status: "created", filename: file.name, doc_id: docId });
              return;
            }
            resolve({ status: "failed", filename: file.name, reason: "缺少 doc_id" });
          } catch {
            resolve({ status: "failed", filename: file.name, reason: "响应解析失败" });
          }
          return;
        }
        if (xhr.status === 503 && attempt < ENQUEUE_RETRY_DELAYS_MS.length) {
          resolve("__retry__");
          return;
        }
        resolve({ status: "failed", filename: file.name, reason: parseUploadError(xhr.status, text) });
      };
      xhr.onerror = () => resolve({ status: "failed", filename: file.name, reason: "网络错误" });
      xhr.send(form);
    });
    if (outcome === "__retry__") {
      await sleep(ENQUEUE_RETRY_DELAYS_MS[attempt] ?? 4000);
      continue;
    }
    return outcome;
  }
  return { status: "failed", filename: file.name, reason: "解析队列已满，请稍后重试" };
}

async function mapPool<T, R>(
  items: T[],
  concurrency: number,
  worker: (item: T, index: number) => Promise<R>,
  onProgress?: (done: number, total: number) => void,
): Promise<R[]> {
  const out: R[] = new Array(items.length);
  let next = 0;
  let done = 0;
  const run = async () => {
    while (next < items.length) {
      const i = next++;
      out[i] = await worker(items[i], i);
      done++;
      onProgress?.(done, items.length);
    }
  };
  const n = Math.max(1, Math.min(concurrency, items.length || 1));
  await Promise.all(Array.from({ length: n }, () => run()));
  return out;
}

export function formatFolderUploadSummary(outcomes: FolderUploadOutcome[]): string {
  const created = outcomes.filter((o) => o.status === "created").length;
  const skipped = outcomes.filter((o) => o.status === "skipped").length;
  const rejected = outcomes.filter((o) => o.status === "rejected").length;
  const failed = outcomes.filter((o) => o.status === "failed").length;
  const parts: string[] = [];
  if (created) parts.push(`新增 ${created}`);
  if (skipped) parts.push(`跳过 ${skipped}（内容相同）`);
  if (rejected) parts.push(`未传 ${rejected}（超过 20MB）`);
  if (failed) parts.push(`失败 ${failed}`);
  if (!parts.length) return "未处理任何文件";
  let text = parts.join("，");
  const failSamples = outcomes
    .filter((o) => o.status === "failed" || o.status === "rejected")
    .slice(0, 3)
    .map((o) => `${o.filename}: ${o.reason}`);
  if (failSamples.length) {
    text += ` — ${failSamples.join("；")}`;
    const more = failed + rejected - failSamples.length;
    if (more > 0) text += ` 等 ${more} 个`;
  }
  return text;
}

export async function runFolderIncrementalUpload(
  folderId: string,
  files: File[],
  headers: Record<string, string>,
  onProgress: (p: FolderUploadProgress | null) => void,
): Promise<FolderUploadOutcome[]> {
  const outcomes: FolderUploadOutcome[] = [];
  const validFiles: File[] = [];
  for (const file of files) {
    if (file.size > KB_MY_DOC_MAX_BYTES) {
      outcomes.push({
        status: "rejected",
        filename: file.name,
        reason: "超过 20MB，请使用实用工具 · PDF 知识库",
      });
    } else {
      validFiles.push(file);
    }
  }
  if (!validFiles.length) {
    onProgress(null);
    return outcomes;
  }

  const hashByName = new Map<string, string>();
  onProgress({
    phase: "hashing",
    current: 0,
    total: validFiles.length,
    pct: 0,
    label: "正在计算文件指纹…",
  });
  await mapPool(
    validFiles,
    KB_UPLOAD_CONCURRENCY,
    async (file) => {
      const h = await sha256HexFromFile(file);
      hashByName.set(file.name, h);
    },
    (done, total) => {
      onProgress({
        phase: "hashing",
        current: done,
        total,
        pct: Math.round((done / total) * 100),
        label: "正在计算文件指纹…",
      });
    },
  );

  onProgress({
    phase: "checking",
    current: validFiles.length,
    total: validFiles.length,
    pct: 100,
    label: "正在检查文件夹内是否已有相同内容…",
  });
  const uniqueHashes = [...new Set(hashByName.values())];
  const existingMap = await fetchExistingSourceHashes(folderId, uniqueHashes, headers);

  const toUpload: { file: File; hash: string }[] = [];
  for (const file of validFiles) {
    const h = hashByName.get(file.name) || "";
    const existingId = existingMap[h];
    if (existingId) {
      outcomes.push({
        status: "skipped",
        filename: file.name,
        doc_id: existingId,
        reason: "内容相同",
      });
    } else {
      toUpload.push({ file, hash: h });
    }
  }

  if (!toUpload.length) {
    onProgress(null);
    return outcomes;
  }

  let uploadDone = 0;
  const uploadResults = await mapPool(
    toUpload,
    KB_UPLOAD_CONCURRENCY,
    async ({ file, hash }) => uploadOneFile(folderId, file, hash, headers),
    (done, total) => {
      uploadDone = done;
      onProgress({
        phase: "uploading",
        current: done,
        total,
        pct: Math.round((done / total) * 100),
        label: "正在上传新文件…",
      });
    },
  );
  outcomes.push(...uploadResults);
  onProgress(null);
  return outcomes;
}
