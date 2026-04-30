/**
 * 将接口失败格式化为可诊断的中文错误信息（不依赖 Response，便于单测）。
 *
 * @param {{ status: number, detail?: string|null, text?: string|null, fallback?: string }} args
 * @returns {string}
 */
export function formatHttpError(args) {
  const status = Number(args?.status || 0) || 0;
  const detail = typeof args?.detail === "string" ? args.detail.trim() : "";
  const txt = typeof args?.text === "string" ? args.text.trim() : "";
  const fallback = String(args?.fallback || "").trim() || "请求失败";
  if (detail) return `HTTP ${status}：${detail}`;
  if (txt) return `HTTP ${status}：${txt.slice(0, 200)}`;
  return status ? `HTTP ${status}：${fallback}` : fallback;
}

