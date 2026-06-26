import type { WorkflowConfig } from "./types";
import { WF_COMPETITOR_FINANCE_ID, WF_DATA_PARSE_EXCEL_ID } from "./constants";
import {
  WORKFLOW_PLANNED_CLASS,
  WORKFLOW_TESTING_CLASS,
  WORKFLOW_WIP_CLASS,
} from "../lib/business_chart_colors";

/** 常用工作流角标：开发中 | 测试中 | 规划中 */
export type QuickWorkflowLabelStatus = "wip" | "testing" | "planned";

export const WORKFLOW_STATUS_LABEL: Record<QuickWorkflowLabelStatus, string> = {
  wip: "开发中",
  testing: "测试中",
  planned: "规划中",
};

export type QuickWorkflowPickDef = {
  key: string;
  /** 不在 workflowConfigs 中的快捷项（静态文案） */
  title?: string;
  subtitle?: string;
  prompt?: string;
  status?: QuickWorkflowLabelStatus;
};

export type ResolvedQuickWorkflowPick = {
  key: string;
  title: string;
  subtitle: string;
  prompt: string;
  status: QuickWorkflowLabelStatus | null;
};

export type WorkflowStatusUiClass =
  | typeof WORKFLOW_WIP_CLASS
  | typeof WORKFLOW_TESTING_CLASS
  | typeof WORKFLOW_PLANNED_CLASS;

export function workflowStatusUiClass(
  status: QuickWorkflowLabelStatus | null,
): WorkflowStatusUiClass | null {
  if (status === "wip") return WORKFLOW_WIP_CLASS;
  if (status === "testing") return WORKFLOW_TESTING_CLASS;
  if (status === "planned") return WORKFLOW_PLANNED_CLASS;
  return null;
}

/** 常用工作流展示顺序（首页、新对话、智能体视图共用） */
export const QUICK_WORKFLOW_PICK_DEFS: QuickWorkflowPickDef[] = [
  { key: WF_COMPETITOR_FINANCE_ID, status: "testing" },
  {
    key: "wf.project_accounting_table.quick",
    title: "一键生成项目核算表",
    subtitle: "根据项目与期间生成项目核算表；勾选对应技能后发送。",
    prompt: "请一键生成项目核算表：项目=，期间=YYYY-MM",
    status: "wip",
  },
  { key: WF_DATA_PARSE_EXCEL_ID, status: "planned" },
  { key: "wf.nl_finance_process.v1", status: "planned" },
  {
    key: "wf.contracts_ledger.write",
    title: "写入合同台账",
    subtitle: "把当前对话/文本整理为合同台账记录并写入。",
    prompt: "写入合同台账：请从以下信息生成台账记录并写入：",
    status: "planned",
  },
];

export function resolveQuickWorkflowPicks(workflowConfigs: WorkflowConfig[]): ResolvedQuickWorkflowPick[] {
  const byId = new Map(workflowConfigs.map((w) => [w.id, w]));
  return QUICK_WORKFLOW_PICK_DEFS.map((def) => {
    const wf = byId.get(def.key);
    return {
      key: def.key,
      title: def.title ?? wf?.label ?? def.key,
      subtitle: (def.subtitle ?? wf?.start_hint ?? wf?.description ?? "").trim(),
      prompt: (def.prompt ?? wf?.example_prompt ?? "").trim(),
      status: def.status ?? null,
    };
  });
}

/** 对话框上方胶囊：末尾若干项收进「更多…」；有对话历史时多收 1 项避免横向滚动 */
export function resolveQuickWorkflowChipPicks(
  workflowConfigs: WorkflowConfig[],
  options?: { compact?: boolean },
): ResolvedQuickWorkflowPick[] {
  const all = resolveQuickWorkflowPicks(workflowConfigs);
  const omitFromEnd = options?.compact ? 2 : 1;
  return all.length > omitFromEnd ? all.slice(0, -omitFromEnd) : all;
}

/** 侧栏历史会话默认展示条数 */
export const SIDEBAR_HISTORY_PREVIEW = 8;
