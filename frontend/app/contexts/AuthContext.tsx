"use client";

import { createContext, useContext } from "react";

export interface AuthContextValue {
  is_admin: boolean;
  view_business_dashboard: boolean;
  /** 财务后台入口路径（与 settings.finance_path 一致，默认 /finance） */
  finance_path: string;
}

const defaultValue: AuthContextValue = {
  is_admin: false,
  view_business_dashboard: false,
  finance_path: "/finance",
};

const AuthContext = createContext<AuthContextValue>(defaultValue);

export function useAuth(): AuthContextValue {
  return useContext(AuthContext);
}

export { AuthContext, defaultValue };
