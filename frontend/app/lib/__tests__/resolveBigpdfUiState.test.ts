import { resolveBigpdfUiState } from "../bigpdfTaskUtils";

describe("resolveBigpdfUiState", () => {
  it("shows queue when another task is running", () => {
    const ui = resolveBigpdfUiState({
      taskId: "t_new",
      status: "queued",
      stage: "queued",
      runningTaskId: "t_old",
      queuePosition: 1,
    });
    expect(ui.isProcessing).toBe(false);
    expect(ui.isWaitingForSlot).toBe(true);
    expect(ui.displayLabel).toContain("排队中");
  });

  it("shows parsing when this task is the running one", () => {
    const ui = resolveBigpdfUiState({
      taskId: "t_mine",
      status: "running",
      stage: "parsing",
      runningTaskId: "t_mine",
    });
    expect(ui.isProcessing).toBe(true);
    expect(ui.displayLabel).toBe("解析中");
    expect(ui.displayStage).toBe("parsing");
  });

  it("shows docling label when docling task id exists", () => {
    const ui = resolveBigpdfUiState({
      taskId: "t1",
      status: "running",
      stage: "queued",
      doclingTaskId: "dl_1",
      runningTaskId: "t1",
    });
    expect(ui.displayLabel).toBe("解析中（Docling）");
  });
});
