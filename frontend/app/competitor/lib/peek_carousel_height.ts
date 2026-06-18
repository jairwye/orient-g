/** 轮播区固定高度：刻度 + 面板标题 + 内边距（不含表格本体） */
export const PEEK_CAROUSEL_CHROME_PX = 48 + 45 + 32;

/** 按最大行数估算轮播总高度（无上限截断，保证明细可完整展示） */
export function peekCarouselHeightPx(maxRowCount: number, compact = true): number {
  const rowH = compact ? 34 : 40;
  const tableHead = 38;
  const tableBody = tableHead + Math.max(maxRowCount, 1) * rowH;
  return carouselHeightFromTableBody(tableBody);
}

export function carouselHeightFromTableBody(tableBodyPx: number): number {
  return PEEK_CAROUSEL_CHROME_PX + Math.max(tableBodyPx, 120);
}
