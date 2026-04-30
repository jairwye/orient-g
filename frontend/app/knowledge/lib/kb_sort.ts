export type SortKbKindsPinned = (kinds: string[]) => string[];

// 兼容层：运行逻辑复用 .js 实现，确保 Node 测试可直接 import .js。
// eslint-disable-next-line @typescript-eslint/ban-ts-comment
// @ts-ignore - allow importing JS module
import { sortKbKindsPinned as _sortKbKindsPinned } from "./kb_sort.js";

export const sortKbKindsPinned: SortKbKindsPinned = _sortKbKindsPinned;

