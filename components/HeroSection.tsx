"use client";

import { useEffect, useState } from "react";
import { Button } from "./ui/Button";
import { workbenchData } from "@/lib/workbench-data";

type State = "default" | "empty" | "quota";

function useWeekProgress() {
  const calc = () => {
    const now = new Date();
    const day = now.getDay(); // 0=Sun,1=Mon...5=Fri,6=Sat
    const weekDay = day === 0 ? 7 : day; // 把周日挪到末尾，周一=1
    const secondsIntoDay =
      now.getHours() * 3600 + now.getMinutes() * 60 + now.getSeconds();
    const totalWeekSeconds = 5 * 24 * 3600; // 周一到周五
    const elapsed = Math.min((weekDay - 1) * 24 * 3600 + secondsIntoDay, totalWeekSeconds);
    return Math.min(elapsed / totalWeekSeconds, 1);
  };
  const [pct, setPct] = useState(calc);
  useEffect(() => {
    const id = setInterval(() => setPct(calc()), 1000);
    return () => clearInterval(id);
  }, []);
  return pct;
}

export function HeroSection({ state = "default" }: { state?: State }) {
  const { greeting, hero } = workbenchData;
  const weekPct = useWeekProgress();

  const title =
    state === "empty" ? "第一次来，从一个周计划开始吧" : hero.title;
  const body =
    state === "empty" ? "不需要复杂设置，选一个主题 2 分钟就能完成" : hero.body;
  const primary =
    state === "empty" ? "创建第一份周计划"
    : state === "quota" ? "本月额度已用完"
    : hero.ctaPrimary;
  const openWeekly = () => {
    window.dispatchEvent(new CustomEvent("sidenav:open", { detail: "weekly" }));
  };
  const openRecent = () => {
    document.getElementById("recent-section")?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <section className="pb-8 w-full">
      <div className="eyebrow">
        {greeting.weekday} · {greeting.time} · {greeting.weekNo}
      </div>
      <h1 className="font-wenkai font-normal text-h1 md:text-[34px] text-ink tracking-tight leading-tight mt-2 max-w-[620px]">
        {title}
      </h1>
      <p className="text-body text-ink-2 mt-3 max-w-[560px]">{body}</p>

      <div className="flex flex-col sm:flex-row sm:items-center gap-10 mt-5 w-full">
        {/* 本周进度条 — 左侧长条，按钮固定在右侧 */}
        <div className="relative hidden sm:block flex-1 min-w-[420px] overflow-hidden rounded-pill border border-rule-soft bg-paper-sunk" style={{ height: "36px" }}>
          <div
            className="absolute inset-y-0 left-0 transition-none"
            style={{ width: `${(weekPct * 100).toFixed(4)}%`, background: "linear-gradient(90deg, var(--color-brand), oklch(0.70 0.13 50))" }}
          />
          <div className="relative z-10 flex items-center justify-between h-full px-3.5">
            <span className="text-meta font-semibold" style={{ mixBlendMode: "difference", color: "white" }}>本周进度</span>
            <span className="text-meta font-num" style={{ mixBlendMode: "difference", color: "oklch(0.55 0 0)" }}>
              {(weekPct * 100).toFixed(2)}%
            </span>
          </div>
        </div>

        <div className="hidden sm:flex items-center gap-2 shrink-0">
          <Button variant="primary" size="md" disabled={state === "quota"} onClick={openWeekly}>
            {primary}
          </Button>
          {state !== "empty" && (
            <Button variant="ghost" size="md" onClick={openRecent}>
              {hero.ctaSecondary}
            </Button>
          )}
        </div>
      </div>
    </section>
  );
}
