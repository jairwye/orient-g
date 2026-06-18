import {
  PEEK_CAROUSEL_START_DELAY_MAX_MS,
  PEEK_CAROUSEL_START_DELAY_MIN_MS,
} from "./carousel_timing";

/** 焦点屏首主体停留：行数略增时略延长，整体约 0.9–1.6s */
export function peekCarouselDwellMs(rowCount: number): number {
  return Math.max(
    PEEK_CAROUSEL_START_DELAY_MIN_MS,
    Math.min(PEEK_CAROUSEL_START_DELAY_MAX_MS, 700 + rowCount * 15),
  );
}
