"use client";

import KnowledgePage from "../knowledge/page";

/**
 * 临时嵌入适配层（最小可用）：
 * - 先复用现有 KnowledgePage 的全部逻辑/UI
 * - 后续若需要“弹层只覆盖工作区/不 fixed 全屏”，再把 knowledge/page.tsx 拆分成可配置的 panel
 */
export type KnowledgeWorkspacePanelProps = {
  mode?: "embedded" | "page";
  initialFolderId?: string | null;
};

export function KnowledgeWorkspacePanel(_props: KnowledgeWorkspacePanelProps) {
  return <KnowledgePage />;
}

