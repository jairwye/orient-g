export type SourceFolderId = string | undefined | null;

export type DeleteSemantics =
  | { kind: "hard_delete" }
  | { kind: "unlink_from_folder"; folder_id: string };

// 兼容层：运行逻辑复用 .js 实现，确保 Node 测试可直接 import .js。
// eslint-disable-next-line @typescript-eslint/ban-ts-comment
// @ts-ignore - allow importing JS module
import {
  deleteSemanticsForContext as _deleteSemanticsForContext,
  isSameSelectionContext as _isSameSelectionContext,
  normalizeSourceFolderId as _normalizeSourceFolderId,
} from "./selection_context.js";

export const normalizeSourceFolderId: (sourceFolderId: SourceFolderId) => string | null =
  _normalizeSourceFolderId;

export const isSameSelectionContext: (a: SourceFolderId, b: SourceFolderId) => boolean =
  _isSameSelectionContext;

export const deleteSemanticsForContext: (sourceFolderId: SourceFolderId) => DeleteSemantics =
  _deleteSemanticsForContext;

