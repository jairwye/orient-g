export type PickDeptDefaultFolderNameArgs = {
  username: string | null | undefined;
  existingNames: string[];
  candidates: string[];
};

// 兼容层：运行逻辑复用 .js 实现，确保 Node 测试可直接 import .js。
// eslint-disable-next-line @typescript-eslint/ban-ts-comment
// @ts-ignore - allow importing JS module
import { pickDeptDefaultFolderName as _pick } from "./default_folders.js";

export const pickDeptDefaultFolderName: (args: PickDeptDefaultFolderNameArgs) => string | null = _pick;

