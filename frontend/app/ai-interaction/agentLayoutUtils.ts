/** Agent / 对话助手消息行布局（与 chatContentInnerClass 同列宽对齐）。 */

/** 助手消息行：Agent 占满内容列宽；普通对话仍 85% 气泡。 */
export function assistantMessageRowClass(isAgentView: boolean): string {
  return isAgentView
    ? "flex w-full min-w-0 gap-3"
    : "flex max-w-[85%] min-w-0 gap-3";
}

/** 头像右侧气泡区：Agent 用 flex-1 与正文、执行过程同宽。 */
export function assistantMessageBubbleWrapClass(isAgentView: boolean): string {
  return isAgentView ? "min-w-0 flex-1" : "min-w-0";
}
