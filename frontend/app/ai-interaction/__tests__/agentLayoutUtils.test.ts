import {
  assistantMessageBubbleWrapClass,
  assistantMessageRowClass,
} from "../agentLayoutUtils";

describe("assistantMessageRowClass", () => {
  it("uses full column width on agent view", () => {
    expect(assistantMessageRowClass(true)).toContain("w-full");
    expect(assistantMessageRowClass(true)).not.toContain("max-w-[85%]");
  });

  it("keeps 85% cap on chat view", () => {
    expect(assistantMessageRowClass(false)).toContain("max-w-[85%]");
  });
});

describe("assistantMessageBubbleWrapClass", () => {
  it("grows to fill row on agent view", () => {
    expect(assistantMessageBubbleWrapClass(true)).toContain("flex-1");
  });
});
