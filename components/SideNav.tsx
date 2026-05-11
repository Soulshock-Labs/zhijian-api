"use client";

import { useAuth } from "@/lib/useAuth";

export type SideNavPanel = "workbench" | "weekly" | "daily" | "knowledge" | "database" | null;

function emit(panel: SideNavPanel) {
  window.dispatchEvent(new CustomEvent("sidenav:open", { detail: panel }));
}

interface Item {
  label: string;
  badge?: string;
  pill?: string;
  active?: boolean;
  disabled?: boolean;
  panel?: SideNavPanel;
  href?: string;
}

export function SideNav() {
  const { user } = useAuth();
  const isPlatformAdmin = user?.role === "platform_admin";
  const knowledgeLabel =
    user?.role === "platform_admin" ? "纸笺知识库"
    : user?.role === "org_admin" ? "园本知识库"
    : "我的知识库";

  const groups: { title: string; items: Item[] }[] = [
    {
      title: "今天",
      items: [
        { label: "工作台", badge: "3", active: true, panel: "workbench" },
        { label: "日教案", panel: "daily" },
        { label: "观察记录", pill: "即将上线", disabled: true },
      ],
    },
    {
      title: "本周",
      items: [
        { label: "周计划", panel: "weekly" },
      ],
    },
    {
      title: "资源",
      items: [
        { label: knowledgeLabel, panel: "knowledge" },
        { label: "模板中心", pill: "即将上线", disabled: true },
      ],
    },
    {
      title: "纸笺集",
      items: [
        { label: "小纸笺", pill: "即将上线", disabled: true },
        { label: "数据库设计", panel: "database" },
        { label: "会员权益", pill: "即将上线", disabled: true },
        ...(isPlatformAdmin ? [{ label: "管理后台", href: "#admin-console" } satisfies Item] : []),
      ],
    },
  ];

  return (
    <aside
      className="flex flex-col px-2.5 py-4"
      style={{
        width: "220px",
        flexShrink: 0,
        height: "100%",
        overflowY: "auto",
        background: "var(--color-paper-hi)",
        borderRight: "1px solid var(--color-rule-soft)",
      }}
    >
      <div className="flex flex-col gap-0.5 flex-1">
      {groups.map((g) => (
        <div key={g.title}>
          {/* Section label */}
          <div
            className="px-3 pt-3 pb-1.5"
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "9px",
              letterSpacing: "1.5px",
              textTransform: "uppercase",
              color: "var(--color-ink-4)",
            }}
          >
            {g.title}
          </div>

          {g.items.map((it) => (
            <button
              key={it.label}
              disabled={it.disabled}
              onClick={() => {
                if (it.disabled) return;
                if (it.href) { window.location.hash = it.href.replace(/^#/, ""); return; }
                if (it.panel) emit(it.panel);
              }}
              className="w-full flex items-center gap-2.5 h-9 px-3 rounded-sm text-body-sm transition-all text-left border"
              style={
                it.active
                  ? { background: "oklch(0.94 0.05 55 / 0.8)", color: "var(--color-brand)", fontWeight: 500, borderColor: "oklch(0.62 0.14 40 / 0.15)" }
                  : { color: "var(--color-ink-3)", background: "transparent", borderColor: "transparent" }
              }
              onMouseEnter={e => { if (!it.active && !it.disabled) { (e.currentTarget as HTMLButtonElement).style.background = "var(--color-paper-sunk)"; (e.currentTarget as HTMLButtonElement).style.color = "var(--color-ink-2)"; } }}
              onMouseLeave={e => { if (!it.active && !it.disabled) { (e.currentTarget as HTMLButtonElement).style.background = "transparent"; (e.currentTarget as HTMLButtonElement).style.color = "var(--color-ink-3)"; } }}
            >
              {/* dot */}
              <span
                className="flex-shrink-0 rounded-full opacity-50"
                style={{ width: "6px", height: "6px", background: "currentColor" }}
              />
              <span>{it.label}</span>
              {it.pill && (
                <span
                  className="ml-auto text-micro"
                  style={{
                    height: "18px",
                    padding: "0 6px",
                    borderRadius: "999px",
                    display: "inline-flex",
                    alignItems: "center",
                    background: "var(--color-paper-sunk)",
                    color: "var(--color-ink-4)",
                  }}
                >
                  {it.pill}
                </span>
              )}
              {it.badge && (
                <span className="ml-auto font-num text-meta" style={{ color: "var(--color-ink-4)" }}>
                  {it.badge}
                </span>
              )}
            </button>
          ))}
        </div>
      ))}
      </div>

      {/* 小黄鸭 mascot — 左下角 */}
      <div className="mt-auto pt-4 flex justify-center select-none pointer-events-none">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src="/chick-default.svg"
          alt="小黄鸭"
          width={88}
          height={104}
          style={{ opacity: 0.88, filter: "drop-shadow(0 2px 6px rgba(240,184,48,.25))" }}
        />
      </div>
    </aside>
  );
}
