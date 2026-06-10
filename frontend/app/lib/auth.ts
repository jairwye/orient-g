/**
 * 登录态：token 存 sessionStorage，关闭标签页后清空，重新打开需重新登录。
 */
export const AUTH_TOKEN_KEY = "orient_g_token";

export function getAuthHeaders(): Record<string, string> {
  if (typeof window === "undefined") return {};
  const token = sessionStorage.getItem(AUTH_TOKEN_KEY);
  if (!token) return {};
  return {
    Authorization: `Bearer ${token}`,
    "X-Auth-Token": token, // 代理环境下若 Authorization 被丢弃，后端可从此头读取
  };
}

export function setAuthToken(token: string): void {
  if (typeof window === "undefined") return;
  sessionStorage.setItem(AUTH_TOKEN_KEY, token);
}

export function clearAuthToken(): void {
  if (typeof window === "undefined") return;
  sessionStorage.removeItem(AUTH_TOKEN_KEY);
}

/** HTTP 401：JWT 过期或未登录（60 分钟无活动滑动窗口） */
export function isSessionExpiredHttpStatus(status: number): boolean {
  return status === 401;
}

/** 清除本地 token 并跳转登录页；?expired=1 时登录页展示会话过期提示 */
export function redirectToLogin(expired = false): void {
  if (typeof window === "undefined") return;
  clearAuthToken();
  const q = expired ? "?expired=1" : "";
  window.location.replace(`/login${q}`);
}

export function hasAuthToken(): boolean {
  if (typeof window === "undefined") return false;
  return !!sessionStorage.getItem(AUTH_TOKEN_KEY);
}
