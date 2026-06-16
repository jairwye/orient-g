/** 根据 snap 锚点 offset 与 scrollTop 解析当前屏（纯函数，可单测） */
export function resolveActiveSnap(
  snapIds: readonly string[],
  offsets: ReadonlyMap<string, number>,
  scrollTop: number,
  probeOffset = 80,
): string {
  if (!snapIds.length) return "sec-01-a";
  const probe = scrollTop + probeOffset;
  let bestId = snapIds[0];
  for (const id of snapIds) {
    const top = offsets.get(id);
    if (top != null && top <= probe) bestId = id;
  }
  return bestId;
}

export type SnapMetric = { top: number; height: number };

export function collectSnapMetrics(
  root: HTMLElement,
  snapIds: readonly string[],
): Map<string, SnapMetric> {
  const map = new Map<string, SnapMetric>();
  for (const id of snapIds) {
    const el = root.querySelector<HTMLElement>(`[data-competitor-snap="${id}"]`);
    if (el) map.set(id, { top: snapOffsetTop(el, root), height: el.offsetHeight });
  }
  return map;
}

/** 屏底越过视口中线（0.5）时触发磁吸到下一屏 */
export const SNAP_CROSS_FRACTION = 0.5;

/**
 * 滚轮停止后磁吸（仅 scrollTop 增大 / 内容上滚时）：
 * 超高屏且屏底已越过阈值线 → 吸到下一屏；其余情况不强制吸附。
 */
export function resolveScrollEndTarget(
  snapIds: readonly string[],
  metrics: ReadonlyMap<string, SnapMetric>,
  scrollTop: number,
  viewportHeight: number,
  scrollDirection: "up" | "down" | null,
): { scrollTop: number; activeId: string; shouldSnap: boolean } {
  const activeId = resolveActiveSnapFromMetrics(snapIds, metrics, scrollTop);

  if (scrollDirection !== "up" || !snapIds.length || viewportHeight <= 0) {
    return { scrollTop, activeId, shouldSnap: false };
  }

  const crossLine = viewportHeight * SNAP_CROSS_FRACTION;

  for (let i = 0; i < snapIds.length; i++) {
    const id = snapIds[i];
    const m = metrics.get(id);
    if (!m) continue;

    const { top, height } = m;
    const bottom = top + height;
    const nextId = snapIds[i + 1];
    const nextTop = nextId ? metrics.get(nextId)?.top : undefined;

    if (scrollTop < top - 4) continue;
    if (nextTop != null && scrollTop >= nextTop - 4) continue;

    if (nextTop == null) {
      return { scrollTop, activeId: id, shouldSnap: false };
    }

    const bottomFromViewportTop = bottom - scrollTop;
    if (bottomFromViewportTop < crossLine) {
      return { scrollTop: nextTop, activeId: nextId!, shouldSnap: true };
    }
    return { scrollTop, activeId: id, shouldSnap: false };
  }

  return { scrollTop, activeId, shouldSnap: false };
}

function resolveActiveSnapFromMetrics(
  snapIds: readonly string[],
  metrics: ReadonlyMap<string, SnapMetric>,
  scrollTop: number,
): string {
  const offsets = new Map<string, number>();
  metrics.forEach((m, id) => offsets.set(id, m.top));
  return resolveActiveSnap(snapIds, offsets, scrollTop);
}

export function snapOffsetTop(el: HTMLElement, root: HTMLElement): number {
  return el.getBoundingClientRect().top - root.getBoundingClientRect().top + root.scrollTop;
}

export function collectSnapOffsets(
  root: HTMLElement,
  snapIds: readonly string[],
): Map<string, number> {
  const map = new Map<string, number>();
  for (const id of snapIds) {
    const el = root.querySelector<HTMLElement>(`[data-competitor-snap="${id}"]`);
    if (el) map.set(id, snapOffsetTop(el, root));
  }
  return map;
}
