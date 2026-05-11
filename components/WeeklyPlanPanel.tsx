"use client";

import { useEffect, useRef, useState } from "react";
import {
  generateDaily,
  generateWeeklyDocumentWithTemplate,
  getWeeklyGenerationJob,
  downloadBlob,
  startWeeklyGenerationJob,
  type WeeklyDay,
  type WeeklyPlan,
} from "@/lib/api";
import { addRecentHistory } from "@/lib/recent-history";
import { Button } from "./ui/Button";

type Props = {
  open: boolean;
  onClose: () => void;
  onMinimize?: () => void;
  onProgressChange?: (state: { active: boolean; progress: number; seconds: number; label: string }) => void;
  onDailyProgressChange?: (state: { active: boolean; progress: number; seconds: number; label: string }) => void;
  onDailyDraftsChange?: (drafts: Record<string, "queued" | "preparing" | "ready" | "error">) => void;
  animateFrom?: "weekly" | "daily";
  seed?: WeeklyPlanSeed | null;
};

export type WeeklyPlanSeed = {
  theme?: string;
  phil?: string;
  classLevel?: string;
  model?: string;
};

type DailyDraft = {
  status: "queued" | "preparing" | "ready" | "error";
  seconds: number;
  elapsed?: number;
  blob?: Blob;
  filename?: string;
  error?: string;
};

function getStoredUserId(): string {
  if (typeof window === "undefined") return "";
  try {
    return localStorage.getItem("user_id") || localStorage.getItem("STA_REDEEM_USER_ID") || "";
  } catch {
    return "";
  }
}

function getStoredUserToken(): string {
  if (typeof window === "undefined") return "";
  try {
    return localStorage.getItem("zj_user_token") || "";
  } catch {
    return "";
  }
}

function ElapsedBadge({ seconds }: { seconds: number }) {
  return (
    <span className="font-mono text-ink-3 text-meta tabular-nums">
      {seconds}s
    </span>
  );
}

const WEEKDAY_ORDER: Record<string, number> = {
  "周一": 1,
  "星期一": 1,
  "周二": 2,
  "星期二": 2,
  "周三": 3,
  "星期三": 3,
  "周四": 4,
  "星期四": 4,
  "周五": 5,
  "星期五": 5,
};

function currentTeachingWeekday() {
  const day = new Date().getDay();
  if (day === 0) return 5;
  return Math.min(day, 5);
}

function shouldAutoPrepareDay(day: string) {
  const order = WEEKDAY_ORDER[day.trim()];
  if (!order) return false;
  return order >= currentTeachingWeekday();
}

export function WeeklyPlanPanel({
  open,
  onClose,
  onMinimize,
  onProgressChange,
  onDailyProgressChange,
  onDailyDraftsChange,
  animateFrom = "weekly",
  seed,
}: Props) {
  const [theme, setTheme] = useState("");
  const [phil, setPhil] = useState("游戏化学习");
  const [classLevel, setClassLevel] = useState("中班");
  const [loading, setLoading] = useState(false);
  const [loadingSeconds, setLoadingSeconds] = useState(0);
  const [weeklyProgress, setWeeklyProgress] = useState(0);
  const [weeklyElapsed, setWeeklyElapsed] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [plan, setPlan] = useState<WeeklyPlan | null>(null);
  const [dailyLoading, setDailyLoading] = useState<string | null>(null);
  const [dailyDrafts, setDailyDrafts] = useState<Record<string, DailyDraft>>({});
  const [dailyError, setDailyError] = useState<string | null>(null);
  const [documentFile, setDocumentFile] = useState<File | null>(null);
  const [documentName, setDocumentName] = useState("");
  const [documentBusy, setDocumentBusy] = useState<"" | "process">("");
  const [documentSeconds, setDocumentSeconds] = useState(0);
  const [documentElapsed, setDocumentElapsed] = useState<number | null>(null);
  const [documentNote, setDocumentNote] = useState("");
  const [model, setModel] = useState("deepseek-chat");
  const [isClosing, setIsClosing] = useState(false);
  const dailyRunRef = useRef(0);
  const weeklyRunRef = useRef(0);
  const closeTimerRef = useRef<number | null>(null);
  const dailyWorkActive = Object.values(dailyDrafts).some(
    (draft) => draft.status === "queued" || draft.status === "preparing",
  );
  const activeDailyDraft = dailyLoading ? dailyDrafts[dailyLoading] : null;
  const activeDailyProgress =
    activeDailyDraft?.status === "preparing"
      ? Math.min(95, Math.max(12, Math.round((activeDailyDraft.seconds / 75) * 100)))
      : dailyWorkActive
        ? 12
        : 0;

  useEffect(() => {
    if (open) setIsClosing(false);
  }, [open]);

  useEffect(() => {
    onProgressChange?.({
      active: loading,
      progress: Math.max(weeklyProgress, loading ? 8 : 0),
      seconds: loadingSeconds,
      label: loading ? "周计划生成冷却中" : "",
    });
  }, [
    loading,
    loadingSeconds,
    onProgressChange,
    weeklyProgress,
  ]);

  useEffect(() => {
    onDailyProgressChange?.({
      active: dailyWorkActive,
      progress: activeDailyProgress,
      seconds: activeDailyDraft?.seconds ?? 0,
      label: dailyLoading ? `${dailyLoading} 日教案准备中` : dailyWorkActive ? "日教案排队中" : "",
    });
  }, [
    activeDailyDraft?.seconds,
    activeDailyProgress,
    dailyLoading,
    dailyWorkActive,
    onDailyProgressChange,
  ]);

  useEffect(() => {
    const simplified: Record<string, "queued" | "preparing" | "ready" | "error"> = {};
    for (const [day, draft] of Object.entries(dailyDrafts)) {
      simplified[day] = draft.status;
    }
    onDailyDraftsChange?.(simplified);
  }, [dailyDrafts, onDailyDraftsChange]);

  useEffect(() => {
    if (!open || !seed) return;
    setTheme(seed.theme ?? "");
    setPhil(seed.phil ?? "游戏化学习");
    setClassLevel(seed.classLevel ?? "中班");
    setModel(seed.model ?? "deepseek-chat");
    setPlan(null);
    setError(null);
    setDailyError(null);
    setWeeklyElapsed(null);
    setWeeklyProgress(0);
    setDailyDrafts({});
    setDocumentElapsed(null);
  }, [open, seed]);

  useEffect(() => {
    return () => {
      dailyRunRef.current += 1;
      weeklyRunRef.current += 1;
      if (closeTimerRef.current !== null) {
        window.clearTimeout(closeTimerRef.current);
      }
    };
  }, []);

  if (!open) return null;

  const handleAnimatedClose = () => {
    if (isClosing) return;
    setIsClosing(true);
    const targetSelector = loading ? "[data-weekly-plan-card]" : "[data-daily-lesson-card]";
    const target = document.querySelector(targetSelector);
    target?.classList.add("weekly-card-receive");
    closeTimerRef.current = window.setTimeout(() => {
      closeTimerRef.current = null;
      if ((loading || dailyWorkActive || plan) && onMinimize) {
        onMinimize();
      } else {
        onClose();
      }
      window.setTimeout(() => {
        target?.scrollIntoView({
          behavior: "smooth",
          block: "center",
        });
      }, 40);
      window.setTimeout(() => {
        target?.classList.remove("weekly-card-receive");
      }, 900);
    }, 540);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!theme.trim()) return;
    const userToken = getStoredUserToken();
    if (!userToken) {
      setError("请先登录后再生成周计划");
      return;
    }
    setLoading(true);
    setError(null);
    setPlan(null);
    setWeeklyElapsed(null);
    setLoadingSeconds(0);
    setWeeklyProgress(0);
    const runId = weeklyRunRef.current + 1;
    weeklyRunRef.current = runId;
    const startTime = Date.now();
    const ticker = window.setInterval(() => {
      setLoadingSeconds(Math.floor((Date.now() - startTime) / 1000));
    }, 1000);
    try {
      const started = await startWeeklyGenerationJob({
        theme: theme.trim(),
        phil: phil.trim(),
        user_token: userToken,
        class_level: classLevel,
        model,
        ref_doc: documentFile ?? undefined,
      });
      let res = null;
      while (weeklyRunRef.current === runId) {
        await new Promise(resolve => window.setTimeout(resolve, 2000));
        const job = await getWeeklyGenerationJob(started.job_id, userToken);
        if (weeklyRunRef.current !== runId) return;
        setWeeklyProgress(Math.max(0, Math.min(100, Math.round(job.progress ?? 0))));
        if (typeof job.elapsed_seconds === "number") {
          setLoadingSeconds(job.elapsed_seconds);
        }
        if (job.status === "success" && job.result?.weekly_plan) {
          res = job.result;
          break;
        }
        if (job.status === "error") {
          throw new Error(job.error || "生成失败，请重试");
        }
      }
      if (!res) return;
      const elapsed = Math.round((Date.now() - startTime) / 100) / 10;
      setWeeklyElapsed(elapsed);
      setWeeklyProgress(100);
      setPlan(res.weekly_plan);
      void prepareDailyDrafts(res.weekly_plan);
      addRecentHistory({
        type: "weekly",
        title: `${res.weekly_plan.week_theme ?? theme.trim()} · 周计划`,
        classLevel,
        theme: theme.trim(),
        phil: res.weekly_plan.philosophy ?? phil.trim(),
        weeklyPlan: res.weekly_plan,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "生成失败，请重试");
    } finally {
      window.clearInterval(ticker);
      setLoading(false);
    }
  };

  const handleReset = () => {
    dailyRunRef.current += 1;
    weeklyRunRef.current += 1;
    setPlan(null);
    setError(null);
    setDailyError(null);
    setWeeklyElapsed(null);
    setWeeklyProgress(0);
    setDailyDrafts({});
    setDailyLoading(null);
  };

  const handleDocumentUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.currentTarget.files?.[0];
    if (!file) return;
    const name = file.name.toLowerCase();
    const allowed = [".docx", ".pdf", ".jpg", ".jpeg", ".png", ".webp", ".gif"];
    if (!allowed.some((ext) => name.endsWith(ext))) {
      setDocumentNote("支持 .docx、.pdf、.jpg、.png、.webp（拍照上传）");
      return;
    }
    setDocumentFile(file);
    setDocumentName(file.name);
    setDocumentNote("");
  };

  const handleGenerateFromDocument = async () => {
    if (!documentFile) {
      setDocumentNote("请先上传文档");
      return;
    }
    if (!theme.trim()) {
      setDocumentNote("请填写主题，或上传能识别标题的文档");
      return;
    }
    const userToken = getStoredUserToken();
    if (!userToken) {
      setDocumentNote("请先登录后再生成文档");
      return;
    }
    setDocumentBusy("process");
    setDocumentNote("");
    setDocumentElapsed(null);
    setDocumentSeconds(0);
    const startTime = Date.now();
    const ticker = window.setInterval(() => {
      setDocumentSeconds(Math.floor((Date.now() - startTime) / 1000));
    }, 1000);
    try {
      const blob = await generateWeeklyDocumentWithTemplate(documentFile, {
        theme: theme.trim(),
        phil: phil.trim(),
        class_level: classLevel,
        client: "web",
        user_id: getStoredUserId(),
        user_token: userToken,
      });
      const elapsed = Math.round((Date.now() - startTime) / 100) / 10;
      setDocumentElapsed(elapsed);
      const safeTheme = theme.trim().replace(/[^一-龥a-zA-Z0-9]/g, "_");
      const filename = `周计划_${safeTheme || "纸笺"}.docx`;
      await downloadBlob(blob, filename);
      addRecentHistory({
        type: "document",
        title: `${theme.trim()} · Word 周计划`,
        classLevel,
        theme: theme.trim(),
        phil,
        filename,
      });
      setDocumentNote(`已生成 Word · ${elapsed}s`);
    } catch (err) {
      setDocumentNote(err instanceof Error ? err.message : "文档生成失败");
    } finally {
      window.clearInterval(ticker);
      setDocumentBusy("");
    }
  };

  function buildDailyFilename(weeklyPlan: WeeklyPlan, day: string) {
    const safeName = (weeklyPlan.week_theme ?? theme).replace(/[^一-龥a-zA-Z0-9]/g, "_");
    return `日教案_${safeName}_${day}.docx`;
  }

  async function prepareOneDailyDraft(weeklyPlan: WeeklyPlan, day: string, runId: number) {
    const userToken = getStoredUserToken();
    if (!userToken) {
      setDailyError("请先登录后再生成日教案");
      return;
    }
    setDailyLoading(day);
    setDailyError(null);
    setDailyDrafts(prev => ({
      ...prev,
      [day]: { status: "preparing", seconds: 0 },
    }));
    const startTime = Date.now();
    const ticker = window.setInterval(() => {
      const seconds = Math.floor((Date.now() - startTime) / 1000);
      setDailyDrafts(prev => {
        const current = prev[day];
        if (!current || current.status !== "preparing") return prev;
        return { ...prev, [day]: { ...current, seconds } };
      });
    }, 1000);
    try {
      const blob = await generateDaily({ weekly_plan: weeklyPlan, day, phil, user_token: userToken });
      if (dailyRunRef.current !== runId) return;
      const elapsed = Math.round((Date.now() - startTime) / 100) / 10;
      const filename = buildDailyFilename(weeklyPlan, day);
      setDailyDrafts(prev => ({
        ...prev,
        [day]: { status: "ready", seconds: Math.floor(elapsed), elapsed, blob, filename },
      }));
    } catch (err) {
      if (dailyRunRef.current !== runId) return;
      if (err instanceof Error && (err.name === "AbortError" || err.message.includes("aborted"))) return;
      const message = err instanceof Error ? err.message : `${day} 日教案生成失败，请重试`;
      setDailyDrafts(prev => ({
        ...prev,
        [day]: {
          status: "error",
          seconds: Math.floor((Date.now() - startTime) / 1000),
          error: message,
        },
      }));
      setDailyError(message);
    } finally {
      window.clearInterval(ticker);
      if (dailyRunRef.current === runId) setDailyLoading(null);
    }
  }

  const prepareDailyDrafts = async (weeklyPlan: WeeklyPlan) => {
    const days = weeklyPlan.days ?? [];
    if (days.length === 0) return;
    const userToken = getStoredUserToken();
    if (!userToken) return;
    const runId = dailyRunRef.current + 1;
    dailyRunRef.current = runId;
    const initialDrafts: Record<string, DailyDraft> = {};
    days.forEach((d) => {
      if (d.day && shouldAutoPrepareDay(d.day)) {
        initialDrafts[d.day] = { status: "queued", seconds: 0 };
      }
    });
    setDailyDrafts(initialDrafts);
    for (const d of days) {
      if (dailyRunRef.current !== runId) return;
      if (!d.day) continue;
      if (!shouldAutoPrepareDay(d.day)) continue;
      await prepareOneDailyDraft(weeklyPlan, d.day, runId);
    }
  };

  const handlePrepareDaily = async (day: string) => {
    if (!plan || dailyLoading) return;
    const runId = dailyRunRef.current + 1;
    dailyRunRef.current = runId;
    await prepareOneDailyDraft(plan, day, runId);
  };

  const handleDownloadDaily = async (day: string) => {
    if (!plan) return;
    const draft = dailyDrafts[day];
    if (!draft?.blob || !draft.filename) return;
    await downloadBlob(draft.blob, draft.filename);
    addRecentHistory({
      type: "daily",
      title: `${day} · ${plan.week_theme ?? theme} · 日教案`,
      classLevel,
      theme: plan.week_theme ?? theme,
      phil: plan.philosophy ?? phil,
      day,
      weeklyPlan: plan,
      filename: draft.filename,
    });
  };

  function renderDailyAction(day: string) {
    const draft = dailyDrafts[day];
    if (draft?.status === "ready") {
      return (
        <button
          onClick={() => handleDownloadDaily(day)}
          className="text-meta text-brand hover:text-brand-hover font-medium whitespace-nowrap"
          title={`下载 ${day} 日教案`}
        >
          下载 Word
        </button>
      );
    }
    if (draft?.status === "preparing") {
      const progress = Math.min(95, Math.max(12, Math.round((draft.seconds / 75) * 100)));
      return (
        <div className="w-[128px]">
          <div className="flex items-center justify-between text-meta text-ink-3">
            <span className="wait-shimmer-text">准备中</span>
            <span className="wait-shimmer-text font-mono tabular-nums">{draft.seconds}s</span>
          </div>
          <div className="mt-1 h-1.5 overflow-hidden rounded-pill bg-paper-sunk">
            <div
              className="wait-shimmer-bar h-full rounded-pill transition-[width]"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
      );
    }
    if (draft?.status === "queued") {
      return <span className="text-meta text-ink-3 whitespace-nowrap">排队准备</span>;
    }
    if (draft?.status === "error") {
      return (
        <button
          onClick={() => void handlePrepareDaily(day)}
          disabled={!!dailyLoading}
          className="text-meta text-danger-ink hover:text-brand-hover font-medium disabled:opacity-30 whitespace-nowrap"
          title={draft.error || `重新准备 ${day} 日教案`}
        >
          重新准备
        </button>
      );
    }
    return (
      <button
        onClick={() => void handlePrepareDaily(day)}
        disabled={!!dailyLoading}
        className="opacity-0 group-hover:opacity-100 transition-opacity text-meta text-brand hover:text-brand-hover font-medium disabled:opacity-30 whitespace-nowrap"
        title={`准备 ${day} 日教案`}
      >
        准备日教案
      </button>
    );
  }

  return (
    <div
      className={[
        "fixed inset-0 z-50 flex items-end sm:items-center justify-center transition-opacity duration-300 ease-out",
        isClosing ? "opacity-0" : "opacity-100",
      ].join(" ")}
      style={{ background: "rgba(0,0,0,0.4)" }}
      onClick={(e) => { if (e.target === e.currentTarget) handleAnimatedClose(); }}
    >
      <div
        className={[
          "w-full max-w-2xl bg-white rounded-t-2xl sm:rounded-2xl shadow-2xl max-h-[90vh] overflow-y-auto",
          "origin-[22%_42%]",
          isClosing
            ? `${loading ? "weekly-panel-recede" : "daily-panel-recede"} opacity-0 blur-[1px]`
            : `${animateFrom === "daily" ? "daily-panel-enter" : "weekly-panel-enter"} opacity-100 translate-y-0 translate-x-0 scale-100 blur-0`,
        ].join(" ")}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-rule-soft sticky top-0 bg-white z-10">
          <h2 className="text-h3 font-semibold text-ink">生成本周周计划</h2>
          <button
            onClick={handleAnimatedClose}
            className="w-8 h-8 rounded-full text-ink-3 hover:bg-paper-sunk flex items-center justify-center text-lg"
            aria-label="关闭"
          >
            ✕
          </button>
        </div>

        <div className="px-6 py-5">
          {/* Form */}
          {!plan && (
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-body-sm font-medium text-ink mb-1.5">
                  周主题 <span className="text-danger">*</span>
                </label>
                <input
                  className="w-full px-3 py-2 rounded-md border border-rule bg-paper text-ink text-body-sm focus:outline-none focus:ring-2 focus:ring-brand/40 placeholder:text-ink-3"
                  placeholder="例：春天来了 / 我爱我家 / 小小科学家"
                  value={theme}
                  onChange={(e) => setTheme(e.target.value)}
                  required
                  autoFocus
                />
              </div>

              <div className="rounded-md border border-rule-soft bg-paper-hi px-3 py-3">
                <label className="block text-body-sm font-medium text-ink mb-1.5">
                  上传参考文档 <span className="text-ink-3 font-normal">（旧计划 / 模板 / 拍照）</span>
                </label>
                <input
                  type="file"
                  accept=".docx,.pdf,.jpg,.jpeg,.png,.webp,.gif,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/pdf,image/*"
                  onChange={handleDocumentUpload}
                  disabled={Boolean(documentBusy)}
                  className="block w-full text-body-sm text-ink file:mr-3 file:h-8 file:px-3 file:rounded-pill file:border file:border-rule file:bg-white file:text-body-sm file:text-ink hover:file:bg-paper-sunk"
                />
                {(documentName || documentNote) && (
                  <div className="mt-2 text-meta text-ink-3 flex items-center gap-2">
                    {documentName && <span className="text-ink-2">{documentName}</span>}
                    {documentNote && <span>{documentName ? " · " : ""}{documentNote}</span>}
                    {documentBusy === "process" && <ElapsedBadge seconds={documentSeconds} />}
                  </div>
                )}
              </div>

              <div className="grid grid-cols-3 gap-4">
                <div>
                  <label className="block text-body-sm font-medium text-ink mb-1.5">教育理念</label>
                  <select
                    className="w-full px-3 py-2 rounded-md border border-rule bg-paper text-ink text-body-sm focus:outline-none"
                    value={phil}
                    onChange={(e) => setPhil(e.target.value)}
                  >
                    <option>游戏化学习</option>
                    <option>探究式学习</option>
                    <option>蒙台梭利</option>
                    <option>瑞吉欧</option>
                    <option>生活化学习</option>
                  </select>
                </div>
                <div>
                  <label className="block text-body-sm font-medium text-ink mb-1.5">班级</label>
                  <select
                    className="w-full px-3 py-2 rounded-md border border-rule bg-paper text-ink text-body-sm focus:outline-none"
                    value={classLevel}
                    onChange={(e) => setClassLevel(e.target.value)}
                  >
                    <option value="小班">小班</option>
                    <option value="中班">中班</option>
                    <option value="大班">大班</option>
                  </select>
                </div>
                <div>
                  <label className="block text-body-sm font-medium text-ink mb-1.5">生成模型</label>
                  <select
                    className="w-full px-3 py-2 rounded-md border border-rule bg-paper text-ink text-body-sm focus:outline-none"
                    value={model}
                    onChange={(e) => setModel(e.target.value)}
                    title="快模型3-8秒"
                  >
                    <option value="deepseek-chat">🚀 DeepSeek（快）</option>
                    <option value="moonshot-v1-8k">⚡ Kimi 轻量版（快）</option>
                  </select>
                </div>
              </div>

              {error && (
                <p className="rounded-md border border-[color-mix(in_oklch,var(--color-danger),transparent_72%)] bg-[color-mix(in_oklch,var(--color-danger),white_92%)] px-3 py-2 text-body-sm text-danger-ink">
                  {error}
                </p>
              )}

              {loading && (
                <div className="rounded-md border border-rule-soft bg-paper-hi px-3 py-2">
                  <div className="flex items-center justify-between text-meta text-ink-3">
                    <span className="wait-shimmer-text">生成冷却中</span>
                    <span className="wait-shimmer-text font-mono tabular-nums">{Math.max(weeklyProgress, 8)}%</span>
                  </div>
                  <div className="mt-2 h-1.5 overflow-hidden rounded-pill bg-paper-sunk">
                    <div
                      className="wait-shimmer-bar h-full rounded-pill transition-[width]"
                      style={{ width: `${Math.max(weeklyProgress, 8)}%` }}
                    />
                  </div>
                </div>
              )}

              <div className="flex items-center justify-end gap-3 pt-2">
                {loading && <ElapsedBadge seconds={loadingSeconds} />}
                <Button variant="ghost" type="button" onClick={handleAnimatedClose}>
                  {loading ? "收起" : "取消"}
                </Button>
                {documentFile && (
                  <Button
                    variant="secondary"
                    type="button"
                    disabled={Boolean(documentBusy) || !theme.trim()}
                    onClick={handleGenerateFromDocument}
                  >
                    {documentBusy === "process" ? "生成中…" : "生成并下载 Word"}
                  </Button>
                )}
                <Button
                  variant="primary"
                  type="submit"
                  disabled={loading || !theme.trim()}
                >
                  {loading ? "AI 生成中…" : "生成周计划"}
                </Button>
              </div>
            </form>
          )}

          {/* Result */}
          {plan && (
            <div>
              <div className="mb-5 flex items-start justify-between gap-4">
                <div>
                  <p className="text-h3 font-semibold text-ink">{plan.week_theme ?? theme}</p>
                  <p className="text-meta text-ink-3 mt-0.5">
                    {classLevel} · {plan.philosophy ?? phil}
                    {weeklyElapsed !== null && (
                      <span className="ml-2 font-mono text-ink-4">· {weeklyElapsed}s</span>
                    )}
                  </p>
                </div>
                <Button variant="ghost" size="sm" type="button" onClick={handleReset}>
                  重新生成
                </Button>
              </div>

              <div className="space-y-2">
                {(plan.days ?? []).map((d: WeeklyDay) => (
                  <div
                    key={d.day}
                    className="flex gap-3 items-start rounded-md border border-rule-soft bg-paper-hi px-4 py-3 group"
                  >
                    <span className="font-mono text-brand font-semibold w-8 shrink-0 pt-0.5">
                      {d.day}
                    </span>
                    <div className="flex-1 min-w-0">
                      <p className="text-body-sm text-ink font-medium">
                        {d.task || d.activity_name || d.domain || d.day}
                      </p>
                      {(d.focus || d.domain) && (
                        <p className="text-meta text-ink-3 mt-0.5">
                          聚焦：{d.focus || d.domain}
                        </p>
                      )}
                      {(d.hint || d.teacher_hint || d.process) && (
                        <p className="text-meta text-ink-3">
                          {d.hint || d.teacher_hint || d.process}
                        </p>
                      )}
                    </div>
                    <div className="flex items-center gap-2 shrink-0 pt-0.5">
                      {d.activity_type && (
                        <span className="text-meta text-ink-3">{d.activity_type}</span>
                      )}
                      {dailyDrafts[d.day]?.elapsed !== undefined && (
                        <span className="font-mono text-meta text-ink-4">{dailyDrafts[d.day]?.elapsed}s</span>
                      )}
                      {renderDailyAction(d.day)}
                    </div>
                  </div>
                ))}
              </div>

              {dailyError && (
                <p className="mt-3 rounded-md border border-[color-mix(in_oklch,var(--color-danger),transparent_72%)] bg-[color-mix(in_oklch,var(--color-danger),white_92%)] px-3 py-2 text-body-sm text-danger-ink">
                  {dailyError}
                </p>
              )}

              <div className="flex justify-end gap-3 pt-5 border-t border-rule-soft mt-5">
                <Button variant="ghost" type="button" onClick={handleAnimatedClose}>
                  收起
                </Button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
