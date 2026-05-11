"use client";

import { useCallback, useEffect, useState } from "react";
import { Card, CardTitle, CardBody, CardFooter } from "./ui/Card";
import { Tag } from "./ui/Tag";
import { workbenchData } from "@/lib/workbench-data";
import { WeeklyPlanPanel } from "./WeeklyPlanPanel";

export function TaskCards() {
  const [weeklyMounted, setWeeklyMounted] = useState(false);
  const [weeklyMinimized, setWeeklyMinimized] = useState(false);
  const [weeklyProgress, setWeeklyProgress] = useState({
    active: false,
    progress: 0,
    seconds: 0,
    label: "",
  });
  const [dailyProgress, setDailyProgress] = useState({
    active: false,
    progress: 0,
    seconds: 0,
    label: "",
  });
  const [panelSource, setPanelSource] = useState<"weekly" | "daily">("weekly");
  const [dailyDrafts, setDailyDrafts] = useState<Record<string, "queued" | "preparing" | "ready" | "error">>({});

  const handleDailyDraftsChange = useCallback((drafts: Record<string, "queued" | "preparing" | "ready" | "error">) => {
    setDailyDrafts(drafts);
  }, []);

  const handleCardClick = (id: string) => {
    if (id === "weekly") {
      setPanelSource("weekly");
      setWeeklyMounted(true);
      setWeeklyMinimized(false);
    }
    if (id === "daily" && weeklyMounted) {
      setPanelSource("daily");
      setWeeklyMinimized(false);
    }
  };

  useEffect(() => {
    function handleSideNav(e: Event) {
      const panel = (e as CustomEvent<string>).detail;
      if (panel !== "daily") return;
      const card = document.querySelector("[data-daily-lesson-card]");
      card?.scrollIntoView({ behavior: "smooth", block: "center" });
      if (weeklyMounted) {
        setPanelSource("daily");
        setWeeklyMinimized(false);
      }
    }

    window.addEventListener("sidenav:open", handleSideNav);
    return () => window.removeEventListener("sidenav:open", handleSideNav);
  }, [weeklyMounted]);

  const handleWeeklyProgress = useCallback((state: {
    active: boolean;
    progress: number;
    seconds: number;
    label: string;
  }) => {
    setWeeklyProgress(state);
  }, []);

  const handleDailyProgress = useCallback((state: {
    active: boolean;
    progress: number;
    seconds: number;
    label: string;
  }) => {
    setDailyProgress(state);
  }, []);

  return (
    <>
      <section className="pb-9">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {workbenchData.tasks.map((t) => (
            <Card
              key={t.id}
              hover
              onClick={() => handleCardClick(t.id)}
              data-weekly-plan-card={t.id === "weekly" ? "true" : undefined}
              data-daily-lesson-card={t.id === "daily" ? "true" : undefined}
            >
              <Tag tone={t.tone} dot>{t.tag}</Tag>
              <div className="mt-3">
                <CardTitle>{t.title}</CardTitle>
                {t.id === "daily" && (
                  <div className="mt-3 flex items-start gap-2 pl-4">
                    <span className="text-[12px] text-ink-3 leading-none mt-[18px]">周</span>
                    {(["周一", "周二", "周三", "周四", "周五"] as const).map((day, i) => {
                      const status = dailyDrafts[day];
                      const label = ["一", "二", "三", "四", "五"][i];
                      return (
                        <div key={day} className="flex flex-col items-center gap-1">
                          <span className="text-[12px] text-ink-3 leading-none">{label}</span>
                          <div className={[
                            "w-9 h-7 rounded-[5px] border flex items-center justify-center text-[13px] font-semibold transition-colors",
                            status === "ready" ? "border-brand bg-brand text-white" :
                            status === "preparing" || status === "queued" ? "border-ink-3 bg-paper-sunk text-ink-3" :
                            status === "error" ? "border-red-400 bg-red-50 text-red-400" :
                            "border-rule-soft bg-paper-sunk",
                          ].join(" ")}>
                            {status === "ready" ? "✓" :
                             status === "preparing" || status === "queued" ? "…" :
                             status === "error" ? "✕" : ""}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
                {t.id === "daily"
                  ? <p className="text-body-sm text-ink-2 mt-2 pl-4">{t.body}</p>
                  : <CardBody>{t.body}</CardBody>
                }
              </div>
              <CardFooter>
                <span>{t.meta}</span>
                <span className="text-brand font-medium">→</span>
              </CardFooter>
              {t.id === "weekly" && weeklyMinimized && weeklyProgress.active && (
                <div className="mt-3">
                  <div className="flex items-center justify-between text-meta text-ink-3">
                    <span className="wait-shimmer-text">{weeklyProgress.label}</span>
                    <span className="wait-shimmer-text font-mono tabular-nums">{weeklyProgress.seconds}s · {weeklyProgress.progress}%</span>
                  </div>
                  <div className="mt-1.5 h-1.5 overflow-hidden rounded-pill bg-paper-sunk">
                    <div
                      className="wait-shimmer-bar h-full rounded-pill bg-brand transition-[width] duration-700"
                      style={{ width: `${Math.max(8, Math.min(100, weeklyProgress.progress))}%` }}
                    />
                  </div>
                </div>
              )}
              {t.id === "daily" && weeklyMinimized && dailyProgress.active && (
                <div className="mt-3">
                  <div className="flex items-center justify-between text-meta text-ink-3">
                    <span className="wait-shimmer-text">{dailyProgress.label}</span>
                    <span className="wait-shimmer-text font-mono tabular-nums">{dailyProgress.seconds}s · {dailyProgress.progress}%</span>
                  </div>
                  <div className="mt-1.5 h-1.5 overflow-hidden rounded-pill bg-paper-sunk">
                    <div
                      className="wait-shimmer-bar h-full rounded-pill bg-brand transition-[width] duration-700"
                      style={{ width: `${Math.max(8, Math.min(100, dailyProgress.progress))}%` }}
                    />
                  </div>
                </div>
              )}
            </Card>
          ))}
        </div>
      </section>

      {weeklyMounted && (
        <WeeklyPlanPanel
          open={!weeklyMinimized}
          animateFrom={panelSource}
          onClose={() => {
            setWeeklyMounted(false);
            setWeeklyMinimized(false);
          }}
          onMinimize={() => {
            setPanelSource(weeklyProgress.active ? "weekly" : "daily");
            setWeeklyMinimized(true);
          }}
          onProgressChange={handleWeeklyProgress}
          onDailyProgressChange={handleDailyProgress}
          onDailyDraftsChange={handleDailyDraftsChange}
        />
      )}
    </>
  );
}
