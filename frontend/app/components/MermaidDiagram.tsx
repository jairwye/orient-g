"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import mermaid from "mermaid";

/** 印刷字号：默认 10 磅（pt）。传统号数制无独立「10号」时，排版/Word 数字栏「10」多指 10pt。 */
const DEFAULT_FOCUS_FONT_PT = 10;

/** pt → CSS 参考像素（假定 96px = 1in，1pt = 1/72in） */
function ptToCssPx(pt: number) {
  return (pt * 96) / 72;
}

type MermaidDiagramProps = {
  chart: string;
  id: string;
  /**
   * 渲染后在 SVG 内查找带该 class 的节点（如 `class … equityTarget`），
   * 将标的公司置于视口中心，并按 focusTargetFontPt（磅）换算为屏幕像素后估算缩放（全量 / 连路径均适用）。
   */
  initialFocusClassName?: string;
  /** 标的公司主文案目标：**磅 pt**（印刷常用），默认 10 磅 ≈ 13.33px（96dpi 下） */
  focusTargetFontPt?: number;
  /** 无法测量标签大小时的兜底缩放 */
  initialFocusScale?: number;
  /**
   * 若已知 Mermaid 节点 ID（例如 `N_xxx`），优先用它定位标的节点。
   * 这样可以避免全量大图里 class 选择器命中错误节点/父容器。
   */
  initialFocusNodeId?: string;
};

function clamp(n: number, a: number, b: number) {
  return Math.max(a, Math.min(b, n));
}

const LABEL_REF_CAP_PX = 36;

/**
 * 在 scale(1) 下估计「单行字」参考高度（px），封顶避免多行整块 span 当字高导致分母过大、缩放过小。
 */
function measureLabelEmPx(target: SVGGraphicsElement): number {
  let fsPx = 0;
  let minSpanLine = Infinity;
  target.querySelectorAll("foreignObject").forEach((fo) => {
    const div = fo.querySelector("div");
    if (!div) return;
    const fs = parseFloat(window.getComputedStyle(div).fontSize || "0");
    if (Number.isFinite(fs) && fs > 0) fsPx = Math.max(fsPx, fs);
    div.querySelectorAll("span").forEach((sp) => {
      const h = sp.getBoundingClientRect().height;
      if (h > 0.5 && h < 320) minSpanLine = Math.min(minSpanLine, h);
    });
  });
  let textH = 0;
  target.querySelectorAll("text").forEach((t) => {
    const h = (t as SVGTextElement).getBoundingClientRect().height;
    if (h > 0.5 && h < 320) textH = Math.max(textH, h);
  });
  const fromFs = fsPx > 0 ? Math.min(fsPx * 1.2, LABEL_REF_CAP_PX) : 0;
  const fromSpan =
    Number.isFinite(minSpanLine) && minSpanLine < Infinity ? Math.min(minSpanLine, LABEL_REF_CAP_PX) : 0;
  const fromText = textH > 0 ? Math.min(textH, LABEL_REF_CAP_PX) : 0;
  const candidates = [fromFs, fromSpan, fromText].filter((x) => x > 0.02);
  if (!candidates.length) return 0;
  return Math.min(...candidates);
}

export function MermaidDiagram({
  chart,
  id,
  initialFocusClassName,
  focusTargetFontPt = DEFAULT_FOCUS_FONT_PT,
  initialFocusScale = 2.45,
  initialFocusNodeId,
}: MermaidDiagramProps) {
  const [svg, setSvg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [scale, setScale] = useState(() => (initialFocusClassName ? initialFocusScale : 1));
  const [tx, setTx] = useState(0);
  const [ty, setTy] = useState(0);
  const [isPanning, setIsPanning] = useState(false);
  const [panStart, setPanStart] = useState<{ x: number; y: number; tx: number; ty: number } | null>(null);

  const containerRef = useRef<HTMLDivElement | null>(null);
  const innerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    mermaid.initialize({
      startOnLoad: false,
      theme: "dark",
      maxTextSize: 2_000_000,
      maxEdges: 15000,
      flowchart: {
        curve: "basis",
        htmlLabels: true,
        padding: 12,
      },
      themeVariables: {
        fontFamily: "ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial",
        fontSize: "18px",
      } as any,
    });
  }, []);

  function findTargetNode(svgEl: SVGSVGElement, cls: string, nodeId?: string): SVGGraphicsElement | null {
    // Mermaid flowchart 的节点通常是 g.node；只在节点层内找，避免误命中 <svg>/<style> 等导致 bbox 巨大
    if (nodeId) {
      const nodes = Array.from(svgEl.querySelectorAll<SVGGElement>("g.node"));
      for (const n of nodes) {
        const idAttr = (n.getAttribute("id") || "").trim();
        // Mermaid 常见：g#flowchart-N_xxx-<hash>，所以用 includes
        if (idAttr && idAttr.includes(nodeId)) return n as unknown as SVGGraphicsElement;
      }
    }
    const direct = svgEl.querySelector(`g.node.${cls}`);
    if (direct && "getBBox" in direct) return direct as SVGGraphicsElement;
    const nodes = Array.from(svgEl.querySelectorAll("g.node"));
    for (const n of nodes) {
      if (n.classList?.contains(cls)) return n as unknown as SVGGraphicsElement;
      const c = (n.getAttribute("class") || "").split(/\s+/g).filter(Boolean);
      if (c.includes(cls)) return n as unknown as SVGGraphicsElement;
    }
    return null;
  }

  function unionNodeVisualRect(node: SVGGraphicsElement): { cx: number; cy: number; w: number; h: number } | null {
    const parts = Array.from(node.querySelectorAll<SVGGraphicsElement>("rect, polygon, path, foreignObject"));
    let left = Infinity;
    let top = Infinity;
    let right = -Infinity;
    let bottom = -Infinity;
    let used = 0;
    for (const el of parts) {
      const r = el.getBoundingClientRect();
      if (!(r.width > 0.5 || r.height > 0.5)) continue;
      if (r.width > 5000 || r.height > 5000) continue;
      left = Math.min(left, r.left);
      top = Math.min(top, r.top);
      right = Math.max(right, r.right);
      bottom = Math.max(bottom, r.bottom);
      used++;
    }
    if (!used || !(right > left) || !(bottom > top)) return null;
    const w = right - left;
    const h = bottom - top;
    return { cx: left + w / 2, cy: top + h / 2, w, h };
  }

  const applyFocusViewport = useCallback(() => {
    const inner = innerRef.current;
    const outer = containerRef.current;
    if (!inner || !outer || !initialFocusClassName) return;
    const svgEl = inner.querySelector("svg");
    if (!svgEl) return;
    const target = findTargetNode(svgEl, initialFocusClassName, initialFocusNodeId);
    const cw = outer.clientWidth;
    const ch = outer.clientHeight;
    if (!target || cw < 8 || ch < 8) return;

    inner.style.transform = "translate(0px, 0px) scale(1)";
    inner.style.transformOrigin = "0 0";
    void inner.offsetHeight;

    const outerRect = outer.getBoundingClientRect();
    const outerContentLeft = outerRect.left + outer.clientLeft;
    const outerContentTop = outerRect.top + outer.clientTop;
    const tr = target.getBoundingClientRect();
    const vr = unionNodeVisualRect(target);
    const tcx = (vr ? vr.cx : tr.left + tr.width / 2) - outerContentLeft;
    const tcy = (vr ? vr.cy : tr.top + tr.height / 2) - outerContentTop;
    const nodeWpx = vr ? vr.w : tr.width;
    const nodeHpx = vr ? vr.h : tr.height;

    const labelPx = measureLabelEmPx(target);
    const targetCssPx = ptToCssPx(focusTargetFontPt);
    const sFont = labelPx > 0.02 ? targetCssPx / Math.max(labelPx, 6) : 0;
    const capN = Math.min(cw, ch) * 0.92;
    const trW = Math.min(Math.max(nodeWpx, 32), capN);
    const trH = Math.min(Math.max(nodeHpx, 26), capN);
    const nodeSpan = Math.max(Math.min(trW, trH), 26);
    const sBox = (Math.min(cw, ch) * 0.62) / nodeSpan;
    const s = clamp(Math.max(sBox, sFont, initialFocusScale * 0.92), 1.2, 40);
    const txNext = cw / 2 - tcx * s;
    const tyNext = ch / 2 - tcy * s;

    // 立即生效，避免等待 React state 刷新时出现“只放大不平移”
    inner.style.transform = `translate(${txNext}px, ${tyNext}px) scale(${s})`;
    inner.style.transformOrigin = "0 0";

    setScale(s);
    setTx(txNext);
    setTy(tyNext);
  }, [initialFocusClassName, initialFocusScale, focusTargetFontPt, initialFocusNodeId]);

  useEffect(() => {
    if (!chart.trim()) {
      setSvg(null);
      setErr(null);
      return;
    }
    let cancelled = false;
    const uid = `mermaid-${id}-${Date.now()}`;
    mermaid
      .render(uid, chart)
      .then((result) => {
        if (!cancelled) {
          setSvg(result.svg);
          setErr(null);
          if (!initialFocusClassName) {
            setScale(1.15);
            setTx(0);
            setTy(0);
          }
        }
      })
      .catch((e) => {
        if (!cancelled) setErr(e?.message || "流程图渲染失败");
      });
    return () => {
      cancelled = true;
    };
  }, [chart, id, initialFocusClassName]);

  useLayoutEffect(() => {
    if (!svg || !initialFocusClassName) return;
    let raf1 = 0;
    let raf2 = 0;
    let tid: ReturnType<typeof setTimeout> | undefined;
    let tid2: ReturnType<typeof setTimeout> | undefined;
    raf1 = requestAnimationFrame(() => {
      applyFocusViewport();
      raf2 = requestAnimationFrame(() => applyFocusViewport());
      tid = setTimeout(() => applyFocusViewport(), 120);
      tid2 = setTimeout(() => applyFocusViewport(), 320);
    });
    return () => {
      cancelAnimationFrame(raf1);
      cancelAnimationFrame(raf2);
      if (tid) clearTimeout(tid);
      if (tid2) clearTimeout(tid2);
    };
  }, [svg, initialFocusClassName, applyFocusViewport]);

  useEffect(() => {
    if (!initialFocusClassName) return;
    const el = containerRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(() => applyFocusViewport());
    ro.observe(el);
    return () => ro.disconnect();
  }, [initialFocusClassName, applyFocusViewport]);

  function onWheel(e: React.WheelEvent<HTMLDivElement>) {
    e.preventDefault();
    const next = clamp(scale * (e.deltaY > 0 ? 0.9 : 1.1), 0.25, 40);
    setScale(next);
  }

  function onMouseDown(e: React.MouseEvent<HTMLDivElement>) {
    if (e.button !== 0) return;
    setIsPanning(true);
    setPanStart({ x: e.clientX, y: e.clientY, tx, ty });
  }

  function onMouseMove(e: React.MouseEvent<HTMLDivElement>) {
    if (!isPanning || !panStart) return;
    const dx = e.clientX - panStart.x;
    const dy = e.clientY - panStart.y;
    setTx(panStart.tx + dx);
    setTy(panStart.ty + dy);
  }

  function onMouseUp() {
    setIsPanning(false);
    setPanStart(null);
  }

  if (err) return <div className="rounded-md border border-red-900/40 bg-red-950/40 p-3 text-sm text-red-200">{err}</div>;
  if (!svg) return <div className="text-sm text-zinc-500">加载中…</div>;

  const hasFocusMode = Boolean(initialFocusClassName);

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-zinc-500">
        {hasFocusMode ? (
          <span className="text-[11px] leading-snug text-zinc-500">
            标的公司（蓝底）对齐视口中心；缩放取「字约{" "}
            <span className="font-mono text-zinc-400">{focusTargetFontPt}</span> 磅」与「节点框（短边约占视口短边 62%，异常大框会封顶）」二者中较大者。其余节点可在画外，拖移查看。
          </span>
        ) : (
          <span />
        )}
        <div className="flex flex-wrap items-center justify-end gap-2">
          <button
            type="button"
            className="rounded-md border border-zinc-800 bg-zinc-950 px-2 py-1 hover:bg-zinc-900"
            onClick={() => setScale((s) => clamp(s * 0.9, 0.25, 40))}
          >
            缩小
          </button>
          <button
            type="button"
            className="rounded-md border border-zinc-800 bg-zinc-950 px-2 py-1 hover:bg-zinc-900"
            onClick={() => setScale((s) => clamp(s * 1.1, 0.25, 40))}
          >
            放大
          </button>
          <button
            type="button"
            className="rounded-md border border-zinc-800 bg-zinc-950 px-2 py-1 hover:bg-zinc-900"
            onClick={() => {
              if (hasFocusMode) applyFocusViewport();
              else {
                setScale(1.15);
                setTx(0);
                setTy(0);
              }
            }}
          >
            {hasFocusMode ? "回中心" : "复位"}
          </button>
        </div>
      </div>

      <div
        ref={containerRef}
        className="mermaid-container relative flex h-[72vh] min-h-[520px] w-full items-start justify-start overflow-hidden rounded-md border border-zinc-800 bg-zinc-950/40 [&_svg]:max-w-none [&_svg]:h-auto"
        style={{ cursor: isPanning ? "grabbing" : "grab" }}
        onWheel={onWheel}
        onMouseDown={onMouseDown}
        onMouseMove={onMouseMove}
        onMouseUp={onMouseUp}
        onMouseLeave={onMouseUp}
      >
        <div
          ref={innerRef}
          className="block w-max max-w-none"
          style={{
            transform: `translate(${tx}px, ${ty}px) scale(${scale})`,
            transformOrigin: "0 0",
          }}
          dangerouslySetInnerHTML={{ __html: svg }}
        />
      </div>
    </div>
  );
}
