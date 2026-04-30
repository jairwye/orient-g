export type ComputeDefaultScopeKindsArgs = {
  availableKinds: string[];
  hasProjectAccess: boolean;
};

// 兼容层：运行逻辑复用 .js 实现，确保 Node 测试可直接 import .js。
// eslint-disable-next-line @typescript-eslint/ban-ts-comment
// @ts-ignore - allow importing JS module
import { computeDefaultScopeKinds as _compute } from "./kb_default_scope.js";

export const computeDefaultScopeKinds: (args: ComputeDefaultScopeKindsArgs) => string[] = _compute;

