export type KbSelection =
  | { kind: "kb"; kb_kind: string }
  | { kind: "folder"; kb_kind: string; folder_id: string };

// 兼容层：运行逻辑复用 .js 实现，确保 Node 测试可直接 import .js。
// eslint-disable-next-line @typescript-eslint/ban-ts-comment
// @ts-ignore - allow importing JS module
import { normalizeSelection as _normalize } from "./kb_selection.js";

export const normalizeSelection: (sel: unknown) => KbSelection = _normalize;

