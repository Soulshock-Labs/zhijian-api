"use client";

import { useEffect, useRef, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { HeroSection } from "@/components/HeroSection";
import { TaskCards } from "@/components/TaskCards";
import { QuickActions } from "@/components/QuickActions";
import { RecentList } from "@/components/RecentList";
import { StatusStrip } from "@/components/StatusStrip";
import { HealthBadge } from "@/components/HealthBadge";
import { AdminConsolePanel } from "@/components/AdminConsolePanel";
import { KnowledgeVaultPanel } from "@/components/KnowledgeVaultPanel";
import { DatabaseSchemaPanel } from "@/components/DatabaseSchemaPanel";
import { WeeklyPlanPanel, type WeeklyPlanSeed } from "@/components/WeeklyPlanPanel";
import type { SideNavPanel } from "@/components/SideNav";

const state: "default" | "empty" | "quota" = "default";

export default function Page() {
  const [weeklyOpen, setWeeklyOpen] = useState(false);
  const [databaseOpen, setDatabaseOpen] = useState(false);
  const [weeklySeed, setWeeklySeed] = useState<WeeklyPlanSeed | null>(null);
  const knowledgeRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onSideNav(e: Event) {
      const panel = (e as CustomEvent<SideNavPanel>).detail;
      if (panel === "weekly") {
        setWeeklySeed(null);
        setWeeklyOpen(true);
      } else if (panel === "knowledge") {
        knowledgeRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      } else if (panel === "database") {
        setDatabaseOpen(true);
      }
    }
    function onWeeklyRegenerate(e: Event) {
      setWeeklySeed((e as CustomEvent<WeeklyPlanSeed>).detail);
      setWeeklyOpen(true);
    }
    window.addEventListener("sidenav:open", onSideNav);
    window.addEventListener("weekly:regenerate", onWeeklyRegenerate);
    return () => {
      window.removeEventListener("sidenav:open", onSideNav);
      window.removeEventListener("weekly:regenerate", onWeeklyRegenerate);
    };
  }, []);

  return (
    <AppShell>
      <HeroSection state={state} />
      <TaskCards />
      <QuickActions />
      <div ref={knowledgeRef}>
        <KnowledgeVaultPanel />
      </div>
      <AdminConsolePanel />
      <RecentList />
      <StatusStrip />
      <HealthBadge />
      <WeeklyPlanPanel open={weeklyOpen} seed={weeklySeed} onClose={() => setWeeklyOpen(false)} />
      <DatabaseSchemaPanel open={databaseOpen} onClose={() => setDatabaseOpen(false)} />
    </AppShell>
  );
}
