"use client";

import { useEffect, useMemo, useState } from "react";
import {
  generateDaily,
  downloadBlob,
  getGenerationRecords,
  type GenerationRecord,
  type WeeklyPlan,
} from "@/lib/api";
import {
  formatRelativeTime,
  getRecentHistory,
  recentHistoryEventName,
  recentItemToText,
  type RecentHistoryItem,
} from "@/lib/recent-history";
import { Tag } from "./ui/Tag";
import { Button } from "./ui/Button";
import type { Tone } from "@/lib/workbench-data";

const toneMap: Record<RecentHistoryItem["type"], Tone> = {
  daily: "info",
  weekly: "brand",
  document: "success",
};

const labelMap: Record<RecentHistoryItem["type"], string> = {
  daily: "日教案",
  weekly: "周计划",
  document: "Word",
};

function getStoredUserToken(): string {
  if (typeof window === "undefined") return "";
  try {
    return localStorage.getItem("zj_user_token") || "";
  } catch {
    return "";
  }
}

function safeFilename(value: string, suffix: string): string {
  const name = value.replace(/[^\u4e00-\u9fa5a-zA-Z0-9]/g, "_").replace(/_+/g, "_");
  return `${name || "纸笺记录"}${suffix}`;
}

function isWeeklyPlan(value: unknown): value is WeeklyPlan {
  return Boolean(value && typeof value === "object" && Array.isArray((value as WeeklyPlan).days));
}

function mapRecordToRecent(record: GenerationRecord): RecentHistoryItem {
  const content = record.content_json && typeof record.content_json === "object"
    ? record.content_json as Record<string, unknown>
    : {};
  const type = record.type === "daily" || record.type === "document" ? record.type : "weekly";
  const weeklyPlan =
    type === "weekly" && isWeeklyPlan(record.content_json)
      ? record.content_json
      : isWeeklyPlan(content.weekly_plan)
        ? content.weekly_plan
        : undefined;
  const day = typeof content.day === "string" ? content.day : undefined;
  const filename = typeof content.filename === "string" ? content.filename : undefined;

  return {
    id: record.record_id,
    type,
    title: record.title || record.theme || "纸笺生成记录",
    classLevel: record.class_level || "中班",
    createdAt: record.created_at_utc || new Date().toISOString(),
    theme: record.theme || record.title || "",
    phil: record.phil || weeklyPlan?.philosophy || "游戏化学习",
    day,
    weeklyPlan,
    filename,
  };
}

function mergeHistory(primary: RecentHistoryItem[], fallback: RecentHistoryItem[]): RecentHistoryItem[] {
  const seen = new Set<string>();
  return [...primary, ...fallback].filter((item) => {
    if (seen.has(item.id)) return false;
    seen.add(item.id);
    return true;
  });
}

export function RecentList() {
  const [items, setItems] = useState<RecentHistoryItem[]>([]);
  const [selected, setSelected] = useState<RecentHistoryItem | null>(null);
  const [notice, setNotice] = useState("");
  const [downloadingId, setDownloadingId] = useState("");

  useEffect(() => {
    let cancelled = false;
    const refresh = () => {
      const localItems = getRecentHistory();
      setItems(localItems);
      const userToken = getStoredUserToken();
      if (!userToken) return;
      getGenerationRecords(userToken, 20)
        .then((res) => {
          if (cancelled) return;
          const dbItems = (res.records || []).map(mapRecordToRecent);
          setItems(mergeHistory(dbItems, localItems));
        })
        .catch(() => {
          if (!cancelled) setItems(localItems);
        });
    };
    refresh();
    window.addEventListener(recentHistoryEventName, refresh);
    window.addEventListener("storage", refresh);
    return () => {
      cancelled = true;
      window.removeEventListener(recentHistoryEventName, refresh);
      window.removeEventListener("storage", refresh);
    };
  }, []);

  const visibleItems = useMemo(() => items.slice(0, 6), [items]);

  const handleCopy = async (item: RecentHistoryItem) => {
    await navigator.clipboard.writeText(recentItemToText(item));
    setNotice("已复制到剪贴板");
    window.setTimeout(() => setNotice(""), 1800);
  };

  const handleRegenerate = (item: RecentHistoryItem) => {
    window.dispatchEvent(new CustomEvent("weekly:regenerate", {
      detail: {
        theme: item.theme,
        phil: item.phil,
        classLevel: item.classLevel,
      },
    }));
  };

  const handleDownload = async (item: RecentHistoryItem) => {
    setDownloadingId(item.id);
    setNotice("");
    try {
      if (item.type === "daily" && item.weeklyPlan && item.day) {
        const userToken = getStoredUserToken();
        if (!userToken) {
          setNotice("请先登录后再下载日教案");
          return;
        }
        const blob = await generateDaily({
          weekly_plan: item.weeklyPlan,
          day: item.day,
          phil: item.phil,
          user_token: userToken,
        });
        await downloadBlob(blob, item.filename || safeFilename(item.title, ".docx"));
        return;
      }

      await downloadBlob(
        new Blob([recentItemToText(item)], { type: "text/plain;charset=utf-8" }),
        safeFilename(item.title, ".txt"),
      );
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "下载失败，请重试");
    } finally {
      setDownloadingId("");
    }
  };

  return (
    <section id="recent-section" className="pb-9 scroll-mt-8">
      <div className="flex items-end justify-between mb-4">
        <div className="flex items-center gap-3">
          <h3 className="text-h3 font-semibold text-ink">最近</h3>
          {notice && <span className="text-meta text-ink-3">{notice}</span>}
        </div>
      </div>

      <div className="rounded-md border border-rule bg-paper-hi overflow-hidden">
        {visibleItems.length === 0 ? (
          <div className="px-5 py-6 text-body-sm text-ink-3">
            暂无生成记录。生成周计划或日教案后会自动出现在这里。
          </div>
        ) : (
          visibleItems.map((item, i) => (
            <div
              key={item.id}
              className={[
                "flex items-center gap-4 px-5 min-h-[60px] hover:bg-paper-sunk transition-colors",
                i ? "border-t border-rule-soft" : "",
              ].join(" ")}
            >
              <Tag tone={toneMap[item.type]} variant="outline">{labelMap[item.type]}</Tag>
              <button
                type="button"
                onClick={() => setSelected(item)}
                className="flex-1 min-w-0 truncate text-left text-body-sm text-ink hover:text-brand"
              >
                {item.title}
              </button>
              <div className="hidden sm:block text-meta text-ink-3">{item.classLevel}</div>
              <div className="text-meta text-ink-3 whitespace-nowrap">{formatRelativeTime(item.createdAt)}</div>
              <div className="flex items-center gap-2 shrink-0">
                <button
                  type="button"
                  className="text-meta text-brand hover:text-brand-hover"
                  onClick={() => handleCopy(item)}
                >
                  复制
                </button>
                <button
                  type="button"
                  className="text-meta text-brand hover:text-brand-hover"
                  onClick={() => handleRegenerate(item)}
                >
                  重新生成
                </button>
                <button
                  type="button"
                  className="text-meta text-brand hover:text-brand-hover disabled:opacity-40"
                  disabled={downloadingId === item.id}
                  onClick={() => handleDownload(item)}
                >
                  {downloadingId === item.id ? "下载中" : "下载"}
                </button>
              </div>
            </div>
          ))
        )}
      </div>

      {selected && (
        <div
          className="fixed inset-0 z-50 flex items-end sm:items-center justify-center"
          style={{ background: "rgba(0,0,0,0.4)" }}
          onClick={(e) => { if (e.target === e.currentTarget) setSelected(null); }}
        >
          <div className="w-full max-w-2xl bg-white rounded-t-2xl sm:rounded-2xl shadow-2xl max-h-[86vh] overflow-hidden">
            <div className="flex items-center justify-between px-6 py-4 border-b border-rule-soft">
              <div>
                <h3 className="text-h3 font-semibold text-ink">{selected.title}</h3>
                <p className="text-meta text-ink-3 mt-0.5">
                  {selected.classLevel} · {selected.phil} · {formatRelativeTime(selected.createdAt)}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setSelected(null)}
                className="w-8 h-8 rounded-full text-ink-3 hover:bg-paper-sunk"
                aria-label="关闭"
              >
                x
              </button>
            </div>
            <pre className="px-6 py-5 max-h-[62vh] overflow-auto whitespace-pre-wrap text-body-sm text-ink bg-paper">
              {recentItemToText(selected)}
            </pre>
            <div className="flex justify-end gap-3 px-6 py-4 border-t border-rule-soft">
              <Button variant="ghost" type="button" onClick={() => handleCopy(selected)}>
                复制
              </Button>
              <Button variant="secondary" type="button" onClick={() => handleDownload(selected)}>
                下载
              </Button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
