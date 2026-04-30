export type KbTaskStatus = string | undefined | null;

// 兼容层：Next/TS 侧使用 .ts 导出；运行逻辑复用 .js 实现，避免重复维护。
// eslint-disable-next-line @typescript-eslint/ban-ts-comment
// @ts-ignore - allow importing JS module
import { kbTaskIsActive as _kbTaskIsActive, kbTaskIsTerminal as _kbTaskIsTerminal } from "./kb_polling_utils.js";

export const kbTaskIsTerminal: (status: KbTaskStatus) => boolean = _kbTaskIsTerminal;
export const kbTaskIsActive: (status: KbTaskStatus) => boolean = _kbTaskIsActive;

