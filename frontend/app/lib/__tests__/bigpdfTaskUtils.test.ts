import {
  isActiveBigpdfStatus,
  isTerminalBigpdfStatus,
  mapListItemToSummary,
  normalizeBigpdfStatus,
  normalizeBigpdfTaskStage,
} from "../bigpdfTaskUtils";

describe("bigpdfTaskUtils", () => {
  it("normalizes done status to completed", () => {
    expect(normalizeBigpdfStatus("done")).toBe("completed");
  });

  it("detects active and terminal statuses", () => {
    expect(isActiveBigpdfStatus("queued")).toBe(true);
    expect(isActiveBigpdfStatus("running")).toBe(true);
    expect(isTerminalBigpdfStatus("completed")).toBe(true);
    expect(isTerminalBigpdfStatus("running")).toBe(false);
  });

  it("maps running stage to parsing for display", () => {
    expect(normalizeBigpdfTaskStage("running", "running")).toBe("parsing");
  });

  it("maps list item to summary with file name fallback", () => {
    const summary = mapListItemToSummary({
      task_id: "t_1",
      status: "queued",
      stage: "queued",
      progress: 0,
      detail: "report.pdf",
    });
    expect(summary.fileName).toBe("report.pdf");
    expect(summary.stage).toBe("queued");
  });
});
