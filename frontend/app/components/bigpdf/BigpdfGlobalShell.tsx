"use client";

import { GlobalNotification } from "./GlobalNotification";
import { useBigpdfCompletionFeed } from "../../hooks/useBigpdfCompletionFeed";

/** 全站挂载：大 PDF 完成/队列清空提醒（离开工具页也能收到） */
export function BigpdfGlobalShell() {
  useBigpdfCompletionFeed({ pollIntervalMs: 8000, enabled: true });
  return <GlobalNotification />;
}
