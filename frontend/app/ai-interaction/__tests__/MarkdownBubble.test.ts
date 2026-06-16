import { normalizeAssistantMarkdown } from "../markdownNormalize";

describe("normalizeAssistantMarkdown", () => {
  it("inserts newline before heading glued to table row", () => {
    const raw = "|-15.14%|##二、管理费用分项明细对比\n|分项|2025|";
    const out = normalizeAssistantMarkdown(raw);
    expect(out).toContain("|-15.14%|\n\n##二、管理费用分项明细对比");
  });

  it("fixes broken formula pipe row", () => {
    const raw = "变动幅度 = (本期 - 上期) / |上期金额|\n\n| ×100%";
    const out = normalizeAssistantMarkdown(raw);
    expect(out).toContain(" ×100%");
    expect(out).not.toMatch(/\n\|\s*×100%/);
  });

  it("promotes leading 结论 to heading", () => {
    const raw = "结论2025年度管理费用合计为4493万元。";
    const out = normalizeAssistantMarkdown(raw);
    expect(out.startsWith("## 结论")).toBe(true);
  });

  it("splits glued bold heading and bullet list", () => {
    const raw = "**任务执行**-编写、调试-执行终端命令";
    const out = normalizeAssistantMarkdown(raw);
    expect(out).toContain("**任务执行**");
    expect(out).toContain("- 编写");
  });
});
