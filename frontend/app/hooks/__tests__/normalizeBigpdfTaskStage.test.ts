import { normalizeBigpdfTaskStage } from "../../lib/bigpdfTaskUtils";

describe("normalizeBigpdfTaskStage", () => {
  it("maps running status to parsing stage", () => {
    expect(normalizeBigpdfTaskStage("running", "running")).toBe("parsing");
    expect(normalizeBigpdfTaskStage("running", "queued")).toBe("parsing");
  });

  it("maps docling submission to parsing even if stage still queued", () => {
    expect(normalizeBigpdfTaskStage("queued", "queued", "docling-123")).toBe("parsing");
  });

  it("keeps genuine queue state", () => {
    expect(normalizeBigpdfTaskStage("queued", "queued")).toBe("queued");
  });
});
