import type { WeeklyPlan } from "@/lib/api";

const STORAGE_KEY = "zhijian_workbench_recent_v1";
const MAX_ITEMS = 20;

export type RecentHistoryType = "weekly" | "daily" | "document";

export type RecentHistoryItem = {
  id: string;
  type: RecentHistoryType;
  title: string;
  classLevel: string;
  createdAt: string;
  theme: string;
  phil: string;
  day?: string;
  weeklyPlan?: WeeklyPlan;
  filename?: string;
};

export type RecentHistoryInput = Omit<RecentHistoryItem, "id" | "createdAt"> & {
  id?: string;
  createdAt?: string;
};

export const recentHistoryEventName = "recent-history:changed";

function canUseStorage(): boolean {
  return typeof window !== "undefined" && Boolean(window.localStorage);
}

function parseItems(raw: string | null): RecentHistoryItem[] {
  if (!raw) return [];
  try {
    const value = JSON.parse(raw);
    return Array.isArray(value) ? value.filter(Boolean) : [];
  } catch {
    return [];
  }
}

function saveItems(items: RecentHistoryItem[]): void {
  if (!canUseStorage()) return;
  localStorage.setItem(STORAGE_KEY, JSON.stringify(items.slice(0, MAX_ITEMS)));
  window.dispatchEvent(new CustomEvent(recentHistoryEventName));
}

export function getRecentHistory(): RecentHistoryItem[] {
  if (!canUseStorage()) return [];
  return parseItems(localStorage.getItem(STORAGE_KEY));
}

export function addRecentHistory(input: RecentHistoryInput): RecentHistoryItem {
  const item: RecentHistoryItem = {
    ...input,
    id: input.id ?? `${input.type}_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
    createdAt: input.createdAt ?? new Date().toISOString(),
  };
  const existing = getRecentHistory().filter((entry) => entry.id !== item.id);
  saveItems([item, ...existing]);
  return item;
}

export function clearRecentHistory(): void {
  saveItems([]);
}

export function formatRelativeTime(iso: string): string {
  const then = new Date(iso).getTime();
  if (!Number.isFinite(then)) return "";
  const diffMs = Date.now() - then;
  const minutes = Math.max(0, Math.floor(diffMs / 60_000));
  if (minutes < 1) return "刚刚";
  if (minutes < 60) return `${minutes} 分钟前`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} 小时前`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days} 天前`;
  return new Intl.DateTimeFormat("zh-CN", { month: "numeric", day: "numeric" }).format(new Date(iso));
}

export function recentItemToText(item: RecentHistoryItem): string {
  const lines = [
    item.title,
    `班级：${item.classLevel}`,
    `理念：${item.phil}`,
    `主题：${item.theme}`,
  ];

  if (item.day) lines.push(`日期：${item.day}`);
  if (item.weeklyPlan?.days?.length) {
    lines.push("", "周计划：");
    item.weeklyPlan.days.forEach((day) => {
      const title = day.task || day.activity_name || day.domain || day.day;
      const focus = day.focus || day.domain;
      const hint = day.hint || day.teacher_hint || day.process;
      lines.push(`${day.day}：${title}`);
      if (focus) lines.push(`  聚焦：${focus}`);
      if (hint) lines.push(`  提示：${hint}`);
    });
  }

  return lines.join("\n");
}
