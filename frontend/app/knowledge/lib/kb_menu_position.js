/**
 * 计算菜单弹出方向：下方空间足够就下弹，否则上弹。
 *
 * @param {{
 *  anchorTop: number,
 *  anchorLeft: number,
 *  anchorBottom: number,
 *  anchorWidth: number,
 *  menuWidth: number,
 *  menuHeight: number,
 *  viewportWidth: number,
 *  viewportHeight: number,
 *  gap?: number
 * }} a
 * @returns {{ placement: "down"|"up", top: number, left: number }}
 */
export function computeMenuPosition(a) {
  const gap = Number(a?.gap ?? 8);
  const vw = Number(a?.viewportWidth || 0);
  const vh = Number(a?.viewportHeight || 0);
  const menuW = Number(a?.menuWidth || 0);
  const menuH = Number(a?.menuHeight || 0);
  const top = Number(a?.anchorTop || 0);
  const left = Number(a?.anchorLeft || 0);
  const bottom = Number(a?.anchorBottom || 0);
  const anchorW = Number(a?.anchorWidth || 0);

  const spaceBelow = Math.max(0, vh - bottom - gap);
  const placeDown = spaceBelow >= menuH;
  const placement = placeDown ? "down" : "up";
  const rawTop = placeDown ? bottom + gap : top - gap - menuH;

  // 横向：默认右对齐按钮；同时 clamp 到 viewport 内
  const rawLeft = left + anchorW - menuW;
  const clampedLeft = Math.max(gap, Math.min(rawLeft, vw - gap - menuW));
  const clampedTop = Math.max(gap, Math.min(rawTop, vh - gap - menuH));

  return { placement, top: clampedTop, left: clampedLeft };
}

