import type { WorkflowConfig } from "./types";
import { WF_COMPETITOR_FINANCE_ID, WF_DATA_PARSE_EXCEL_ID } from "./constants";

export type QuickWorkflowPickDef = {
  key: string;
  /** 不在 workflowConfigs 中的快捷项（静态文案） */
  title?: string;
  subtitle?: string;
  prompt?: string;
  /** 半成品 / 开发中 */
  wip?: boolean;
};

export type ResolvedQuickWorkflowPick = {
  key: string;
  title: string;
  subtitle: string;
  prompt: string;
  wip: boolean;
};

/** 常用工作流展示顺序（首页、新对话、智能体视图共用） */
export const QUICK_WORKFLOW_PICK_DEFS: QuickWorkflowPickDef[] = [
  { key: WF_COMPETITOR_FINANCE_ID },
  {
    key: "wf.project_accounting_table.quick",
    title: "一键生成项目核算表",
    subtitle: "根据项目与期间生成项目核算表；勾选对应技能后发送。",
    prompt: "请一键生成项目核算表：项目=，期间=YYYY-MM",
    wip: true,
  },
  { key: WF_DATA_PARSE_EXCEL_ID, wip: true },
  { key: "wf.nl_finance_process.v1", wip: true },
  {
    key: "wf.contracts_ledger.write",
    title: "写入合同台账",
    subtitle: "把当前对话/文本整理为合同台账记录并写入。",
    prompt: "写入合同台账：请从以下信息生成台账记录并写入：",
    wip: true,
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
      wip: def.wip ?? false,
    };
  });
}

/** 对话框上方胶囊：省略列表最后一项（在「更多…」中查看） */
export function resolveQuickWorkflowChipPicks(workflowConfigs: WorkflowConfig[]): ResolvedQuickWorkflowPick[] {
  const all = resolveQuickWorkflowPicks(workflowConfigs);
  return all.length > 1 ? all.slice(0, -1) : all;
}
