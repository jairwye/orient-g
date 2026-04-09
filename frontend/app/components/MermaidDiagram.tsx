"use client";

import { useEffect, useState } from "react";
import mermaid from "mermaid";

export function MermaidDiagram({ chart, id }: { chart: string; id: string }) {
  const [svg, setSvg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [scale, setScale] = useState(1);
  const [tx, setTx] = useState(0);
  const [ty, setTy] = useState(0);
  const [isPanning, setIsPanning] = useState(false);
  const [panStart, setPanStart] = useState<{ x: number; y: number; tx: number; ty: number } | null>(null);

  useEffect(() => {
    mermaid.initialize({
      startOnLoad: false,
      theme: "dark",
      flowchart: { curve: "basis", htmlLabels: true, padding: 12 },
      themeVariables: {
        fontFamily: "ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial",
        fontSize: "18px",
      } as any,
    });
  }, []);

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
          // 每次图更新，重置视图（避免沿用上一张的缩放导致“看不到图”）
          // 默认稍微放大，避免“大图文字太小看不清”
          setScale(1.15);
          setTx(0);
          setTy(0);
        }
      })
      .catch((e) => {
        if (!cancelled) setErr(e?.message || "流程图渲染失败");
      });
    return () => {
      cancelled = true;
    };
  }, [chart, id]);

  function clamp(n: number, a: number, b: number) {
    return Math.max(a, Math.min(b, n));
  }

  function onWheel(e: React.WheelEvent<HTMLDivElement>) {
    e.preventDefault();
    const next = clamp(scale * (e.deltaY > 0 ? 0.9 : 1.1), 0.4, 5);
    setScale(next);
  }

  function onMouseDown(e: React.MouseEvent<HTMLDivElement>) {
    if (e.button !== 0) return;
    setIsPanning(true);
    setPanStart({ x: e.clientX, y: e.clientY, tx, ty });
  }

  function onMouseMove(e: React.MouseEvent<HTMLDivElement>) {
    if (!isPanning || !panStart) return;
    setTx(panStart.tx + (e.clientX - panStart.x));
    setTy(panStart.ty + (e.clientY - panStart.y));
  }

  function onMouseUp() {
    setIsPanning(false);
    setPanStart(null);
  }

  if (err) return <div className="rounded-md border border-red-900/40 bg-red-950/40 p-3 text-sm text-red-200">{err}</div>;
  if (!svg) return <div className="text-sm text-zinc-500">加载中…</div>;
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center justify-end gap-2 text-xs text-zinc-500">
        <button
          type="button"
          className="rounded-md border border-zinc-800 bg-zinc-950 px-2 py-1 hover:bg-zinc-900"
          onClick={() => setScale((s) => clamp(s * 0.9, 0.4, 5))}
        >
          缩小
        </button>
        <button
          type="button"
          className="rounded-md border border-zinc-800 bg-zinc-950 px-2 py-1 hover:bg-zinc-900"
          onClick={() => setScale((s) => clamp(s * 1.1, 0.4, 5))}
        >
          放大
        </button>
        <button
          type="button"
          className="rounded-md border border-zinc-800 bg-zinc-950 px-2 py-1 hover:bg-zinc-900"
          onClick={() => {
            setScale(1);
            setTx(0);
            setTy(0);
          }}
        >
          复位
        </button>
      </div>

      <div
        className="mermaid-container relative h-[72vh] min-h-[520px] w-full overflow-hidden rounded-md border border-zinc-800 bg-zinc-950/40 [&_svg]:max-w-none [&_svg]:h-auto"
        style={{ cursor: isPanning ? "grabbing" : "grab" }}
        onWheel={onWheel}
        onMouseDown={onMouseDown}
        onMouseMove={onMouseMove}
        onMouseUp={onMouseUp}
        onMouseLeave={onMouseUp}
      >
        <div
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

