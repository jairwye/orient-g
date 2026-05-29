import { normalizeAgentDisplayText, UI_AGENT } from "../ui_labels";

describe("UI_AGENT", () => {
  it("uses 智能体 as product label", () => {
    expect(UI_AGENT.label).toBe("智能体");
    expect(UI_AGENT.newSessionTitle).toBe("新智能体对话");
  });
});

describe("normalizeAgentDisplayText", () => {
  it("migrates legacy session titles", () => {
    expect(normalizeAgentDisplayText("新 Agent 对话")).toBe("新智能体对话");
    expect(normalizeAgentDisplayText("Agent 对话")).toBe("智能体对话");
  });
});
