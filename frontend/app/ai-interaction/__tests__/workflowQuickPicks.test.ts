import {
  QUICK_WORKFLOW_PICK_DEFS,
  resolveQuickWorkflowPicks,
} from "../workflowQuickPicks";
import { WF_COMPETITOR_FINANCE_ID, WF_DATA_PARSE_EXCEL_ID } from "../constants";

describe("QUICK_WORKFLOW_PICK_DEFS", () => {
  it("puts competitor finance first and project accounting second", () => {
    expect(QUICK_WORKFLOW_PICK_DEFS[0]?.key).toBe(WF_COMPETITOR_FINANCE_ID);
    expect(QUICK_WORKFLOW_PICK_DEFS[1]?.key).toBe("wf.project_accounting_table.quick");
  });
});

describe("resolveQuickWorkflowPicks", () => {
  it("merges config labels and marks wip", () => {
    const picks = resolveQuickWorkflowPicks([
      {
        id: WF_COMPETITOR_FINANCE_ID,
        label: "竞品财报分析",
        description: "KB 分析",
        example_prompt: "对比应收账款",
      },
      {
        id: WF_DATA_PARSE_EXCEL_ID,
        label: "电子表数据解析",
        start_hint: "先上传 Excel",
        example_prompt: "解读表格",
      },
      {
        id: "wf.nl_finance_process.v1",
        label: "自然语言生成财务流程",
        description: "流程占位",
      },
    ]);
    expect(picks[0]?.title).toBe("竞品财报分析");
    expect(picks[0]?.wip).toBe(false);
    expect(picks[1]?.title).toBe("一键生成项目核算表");
    expect(picks[1]?.wip).toBe(true);
    expect(picks[2]?.title).toBe("电子表数据解析");
    expect(picks[2]?.wip).toBe(true);
    expect(picks[3]?.wip).toBe(true);
    expect(picks[4]?.wip).toBe(true);
  });
});
