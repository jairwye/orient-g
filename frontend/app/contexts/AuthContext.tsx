"use client";

import { createContext, useContext } from "react";

export interface AuthContextValue {
  is_admin: boolean;
  view_business_dashboard: boolean;
}

const defaultValue: AuthContextValue = { is_admin: false, view_business_dashboard: false };

const AuthContext = createContext<AuthContextValue>(defaultValue);

export function useAuth(): AuthContextValue {
  return useContext(AuthContext);
}

export { AuthContext, defaultValue };
