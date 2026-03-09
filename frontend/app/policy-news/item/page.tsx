"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

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

export default function PolicyNewsItemPage() {
  const searchParams = useSearchParams();
  const id = searchParams.get("id") ?? "";
  const [item, setItem] = useState<NewsItem | null>(null);
  const [loading, setLoading] = useState(!!id);
  const [error, setError] = useState<string | null>(null);

  const fetchItem = useCallback(async () => {
    if (!id) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/policy-news/item?id=${encodeURIComponent(id)}`, {
        cache: "no-store",
      });
      if (!res.ok) {
        setError(res.status === 404 ? "未找到该条目" : "加载失败");
        setItem(null);
        return;
      }
      const json = await res.json();
      setItem(json as NewsItem);
    } catch {
      setError("加载失败");
      setItem(null);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    fetchItem();
  }, [fetchItem]);

  if (!id) {
    return (
      <div className="p-6 md:p-8">
        <p className="text-zinc-500">缺少 id 参数。</p>
        <Link href="/policy-news" className="mt-2 inline-block text-zinc-400 hover:text-zinc-100">
          返回列表
        </Link>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="p-6 md:p-8">
        <div className="text-zinc-500">加载中…</div>
      </div>
    );
  }

  if (error || !item) {
    return (
      <div className="p-6 md:p-8">
        <p className="text-amber-500">{error || "未找到该条目"}</p>
        <Link href="/policy-news" className="mt-2 inline-block text-zinc-400 hover:text-zinc-100">
          返回列表
        </Link>
      </div>
    );
  }

  const html = item.content || item.summary || "";

  return (
    <div className="p-6 md:p-8">
      <div className="mb-4">
        <Link
          href="/policy-news"
          className="text-sm text-zinc-500 hover:text-zinc-300"
        >
          返回列表
        </Link>
      </div>
      <article className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-6">
        <h1 className="text-xl font-semibold text-zinc-100">
          <a
            href={item.link}
            target="_blank"
            rel="noopener noreferrer"
            className="hover:underline"
          >
            {item.title}
          </a>
        </h1>
        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-0 text-sm text-zinc-500">
          <span>{item.date}</span>
          {item.originTitle && <span>{item.originTitle}</span>}
          <a
            href={item.link}
            target="_blank"
            rel="noopener noreferrer"
            className="text-zinc-400 hover:text-zinc-200"
          >
            阅读原文
          </a>
        </div>
        {html ? (
          <div
            className="policy-news-content mt-4 border-t border-zinc-800 pt-4 text-zinc-300 prose prose-invert max-w-none prose-p:text-zinc-300 prose-a:text-zinc-200 prose-img:rounded-lg"
            dangerouslySetInnerHTML={{ __html: html }}
          />
        ) : (
          <p className="mt-4 text-zinc-500">暂无正文。</p>
        )}
      </article>
    </div>
  );
}
