"use client";

import { useEffect, useState } from "react";
import { healthCheck, ApiError, API_BASE } from "@/lib/api";

type State = "checking" | "ok" | "down";

/**
 * 右下角一个迷你 API 状态徽章。
 * 目的只有一个：让开发/部署时一眼看到前端到 FastAPI 的链路是否通。
 * Phase 2e 做生产构建时会把它隐掉或改成环境变量 gating。
 */
export function HealthBadge() {
  const [state, setState] = useState<State>("checking");
  const [detail, setDetail] = useState<string>("");

  useEffect(() => {
    let cancelled = false;

    healthCheck()
      .then((r) => {
        if (cancelled) return;
        setState("ok");
        const short = typeof r === "object" && r !== null ? JSON.stringify(r) : String(r);
        setDetail(short.slice(0, 80));
      })
      .catch((e) => {
        if (cancelled) return;
        setState("down");
        const msg =
          e instanceof ApiError
            ? `${e.status} ${e.message}`
            : e instanceof Error
            ? e.message
            : String(e);
        setDetail(msg.slice(0, 80));
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const color =
    state === "ok" ? "#2f855a" : state === "down" ? "#b1301f" : "#8a8178";
  const label =
    state === "ok" ? "API ✓" : state === "down" ? "API ✗" : "API …";
  const base = API_BASE || "(same-origin)";

  return (
    <div
      title={`${label}  |  base: ${base}  |  ${detail}`}
      style={{
        position: "fixed",
        bottom: 12,
        right: 12,
        zIndex: 9999,
        padding: "6px 12px",
        borderRadius: 999,
        fontSize: 12,
        fontWeight: 600,
        letterSpacing: "0.02em",
        color,
        background: "rgba(255, 255, 255, 0.92)",
        border: "1px solid rgba(0, 0, 0, 0.08)",
        boxShadow: "0 4px 14px rgba(0, 0, 0, 0.08)",
        backdropFilter: "saturate(1.1) blur(6px)",
        fontFamily: "Inter, system-ui, -apple-system, sans-serif",
        pointerEvents: "none",
        userSelect: "none",
      }}
    >
      {label}
    </div>
  );
}
