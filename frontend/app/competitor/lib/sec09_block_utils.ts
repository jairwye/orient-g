import type { AnchorBlock } from "./selectors";

/** 去掉最后一表之后的脚注/说明叙事（如 *注：…*） */
export function stripBlocksAfterLastTable(blocks: AnchorBlock[]): AnchorBlock[] {
  let lastTableIdx = -1;
  for (let i = blocks.length - 1; i >= 0; i--) {
    if (blocks[i]!.kind === "table") {
      lastTableIdx = i;
      break;
    }
  }
  if (lastTableIdx === -1) return blocks;
  return blocks.slice(0, lastTableIdx + 1);
}
