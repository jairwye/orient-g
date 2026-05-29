import { formatEvidencePackStatusLine, parseEvidencePackSummary } from "../agentTraceUtils";

describe("chat evidence pack", () => {
  it("parses API evidence_pack for message bubble", () => {
    const pack = parseEvidencePackSummary({
      task_type: "breakdown",
      coverage_score: 0.72,
      retrieval_queries: ["主问", "销售费用 附注"],
      gaps: ["未命中研发费用"],
    });
    const line = formatEvidencePackStatusLine(pack);
    expect(line).toContain("breakdown");
    expect(line).toContain("72%");
    expect(line).toContain("子检索 2 条");
  });
});
