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
