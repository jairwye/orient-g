"use client";

import { Minimize2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

const CATEGORIES = ["观点", "新闻", "AI"] as const;
type Category = (typeof CATEGORIES)[number];

const CATEGORY_LABELS: Record<Category, string> = {
  观点: "业界观点",
  新闻: "游戏新闻",
  AI: "AI资讯",
};

type NewsItem = {
  id: string;
  title: string;
  published: string;
  date: string;
  link: string;
  originTitle?: string;
  summary?: string;
  content?: string;
  thumbnail?: string;
};

type ListResponse = {
  categories: string[];
  itemsByCategory: Record<string, NewsItem[]>;
  lastSuccessAt?: number | null;
  lastError?: string | null;
};

function getSummaryText(it: NewsItem, maxChars: number = 200): string {
  const raw = it.summary || it.content || "";
  if (!raw) return "";
  const stripped = raw.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
  return stripped.length <= maxChars ? stripped : stripped.slice(0, maxChars) + "…";
}

export default function PolicyNewsPage() {
  const [category, setCategory] = useState<Category>("观点");
  const [data, setData] = useState<ListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [expandedItem, setExpandedItem] = useState<NewsItem | null>(null);
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [failedThumbnailIds, setFailedThumbnailIds] = useState<Set<string>>(() => new Set());

  const markThumbnailFailed = useCallback((id: string) => {
    setFailedThumbnailIds((prev) => (prev.has(id) ? prev : new Set(prev).add(id)));
  }, []);

  const fetchList = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/policy-news/list", { cache: "no-store" });
      const json = await res.json();
      setData(json as ListResponse);
    } catch {
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchList();
  }, [fetchList]);

  const items = data?.itemsByCategory?.[category] ?? [];
  const hasError = data?.lastError;

  return (
    <div className="p-6 md:p-8">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-zinc-100">
            新闻政策
          </h1>
          <p className="mt-1 text-sm text-zinc-500">
            按分类查看：业界观点、游戏新闻、AI资讯；数据来自自建RSS列表定时拉取。点击卡片展开全文。
          </p>
        </div>
        <div className="flex shrink-0 overflow-hidden rounded-lg border border-zinc-600">
          {CATEGORIES.map((c, i) => (
            <button
              key={c}
              type="button"
              onClick={() => setCategory(c)}
              className={`px-4 py-2 text-sm font-medium transition-all ${
                i === 0 ? "rounded-l-md" : i === CATEGORIES.length - 1 ? "rounded-r-md" : ""
              } ${
                category === c
                  ? "bg-[#2563eb] text-white"
                  : "bg-zinc-800/80 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-200"
              }`}
            >
              {CATEGORY_LABELS[c]}
            </button>
          ))}
        </div>
      </div>

      {hasError && (
        <p className="mb-3 text-sm text-amber-500">{data?.lastError}</p>
      )}

      {loading ? (
        <div className="flex min-h-[200px] items-center justify-center text-zinc-500">
          加载中…
        </div>
      ) : items.length === 0 ? (
        <div className="flex min-h-[200px] items-center justify-center rounded-lg border border-zinc-800 bg-zinc-900/50 text-zinc-500">
          暂无该分类条目；若已配置 FreshRSS，请稍后刷新。
        </div>
      ) : expandedItem ? (
        <div
          className="flex min-h-[80vh] flex-col overflow-hidden rounded-lg border border-zinc-700 bg-zinc-900 shadow-xl"
          role="dialog"
          aria-modal="true"
          aria-label="文章全文"
        >
          <div className="flex shrink-0 items-center justify-between gap-2 border-b border-zinc-800 bg-zinc-800/50 px-4 py-2">
            <h2 className="min-w-0 flex-1 truncate text-sm font-medium text-zinc-100">
              {expandedItem.title}
            </h2>
            <div className="flex shrink-0 items-center gap-1">
              <a
                href={expandedItem.link}
                target="_blank"
                rel="noopener noreferrer"
                className="rounded px-2 py-1 text-xs text-zinc-400 hover:bg-zinc-700 hover:text-zinc-200"
              >
                原文
              </a>
              <button
                type="button"
                onClick={() => setExpandedItem(null)}
                className="rounded p-1 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-100"
                title="缩回"
                aria-label="缩回"
              >
                <Minimize2 className="h-4 w-4" />
              </button>
            </div>
          </div>
          <div className="flex-1 overflow-auto p-4 md:p-6">
            <div className="mx-auto max-w-3xl">
              <div className="mb-3 text-xs text-zinc-500">
                {expandedItem.date}
                {expandedItem.originTitle && ` · ${expandedItem.originTitle}`}
              </div>
              {expandedItem.content ? (
                <div
                  className="policy-news-content text-zinc-300 prose prose-invert max-w-none prose-p:text-zinc-300 prose-a:text-zinc-200 prose-img:rounded-lg"
                  dangerouslySetInnerHTML={{ __html: expandedItem.content }}
                />
              ) : (
                <p className="text-zinc-500">暂无正文。</p>
              )}
            </div>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-8 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
          {items.map((it) => {
            const isHovered = hoveredId === it.id;
            const hasThumbnail = Boolean(it.thumbnail?.trim());
            const thumbnailFailed = failedThumbnailIds.has(it.id);
            const showThumbnail = hasThumbnail && !thumbnailFailed && !isHovered;
            const showSummary = !hasThumbnail || thumbnailFailed || isHovered;
            const summaryText = getSummaryText(it, 200);
            return (
              <button
                key={it.id}
                type="button"
                onClick={() => setExpandedItem(it)}
                onMouseEnter={() => setHoveredId(it.id)}
                onMouseLeave={() => setHoveredId(null)}
                className="flex min-h-[10rem] flex-col overflow-hidden rounded-md border border-zinc-800 bg-zinc-900/50 text-left transition-colors hover:border-zinc-700 hover:bg-zinc-800/50"
              >
                {showThumbnail && (
                  <div className="aspect-[2/1] w-full shrink-0 bg-zinc-800">
                    <img
                      src={it.thumbnail}
                      alt=""
                      className="h-full w-full object-cover"
                      onError={() => markThumbnailFailed(it.id)}
                    />
                  </div>
                )}
                <div className="flex flex-1 flex-col overflow-hidden p-3">
                  <div className="flex min-h-0 flex-[13] flex-col justify-center">
                    <div className="mb-1 flex items-center justify-between gap-2 text-xs text-zinc-500">
                      <span className="min-w-0 truncate">{it.originTitle || "—"}</span>
                      <span className="shrink-0">{it.date}</span>
                    </div>
                    <span className="line-clamp-2 text-lg font-semibold leading-snug text-zinc-100">
                      {it.title}
                    </span>
                  </div>
                  {showSummary && summaryText && (
                    <p className="mt-1.5 line-clamp-4 min-h-0 flex-[17] text-base leading-relaxed text-zinc-400">
                      {summaryText}
                    </p>
                  )}
                </div>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
