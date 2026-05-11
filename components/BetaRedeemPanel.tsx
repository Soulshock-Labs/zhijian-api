"use client";

import { useState } from "react";
import { Button } from "./ui/Button";
import { Card } from "./ui/Card";
import { AuthModal } from "./AuthModal";
import { useAuth } from "@/lib/useAuth";
import {
  type RedeemResponse,
  type AuthResponse,
  queryRedeemCode,
  redeemCode,
} from "@/lib/api";

function serviceLabel(response?: RedeemResponse): string {
  const service = response?.service ?? {};
  const name = service.name || service.type || response?.description || "";
  if (!name) return "";
  if (service.days) return `${name} · ${service.days} 天`;
  if (service.amount) return `${name} · ${service.amount}`;
  return String(name);
}

function resultText(response?: RedeemResponse): string {
  if (!response) return "";
  const status = response.status || "";
  const message = response.message || "";
  const service = serviceLabel(response);
  if (response.ok) {
    return [message || "可用", service, response.expires_at ? `截止 ${String(response.expires_at).split("T")[0]}` : ""]
      .filter(Boolean)
      .join(" · ");
  }
  return [message || status || "未完成", service].filter(Boolean).join(" · ");
}

export function BetaRedeemPanel() {
  const { user, isLoggedIn, login } = useAuth();
  const [authOpen, setAuthOpen] = useState(false);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState<"query" | "redeem" | "">("");
  const [redeemNote, setRedeemNote] = useState("等待卡密");

  function handleAuthSuccess(data: AuthResponse) {
    login({
      token: data.user_token,
      account_id: data.account_id,
      member_no: data.member_no,
      user_id: data.user_id,
      role: data.role || "teacher",
      org_id: data.org_id || "",
    });
    setAuthOpen(false);
  }

  const canUseCode = isLoggedIn && Boolean(code.trim());

  async function handleQuery() {
    const cardCode = code.trim().toUpperCase();
    if (!cardCode) { setRedeemNote("请填写卡密"); return; }
    setBusy("query");
    try {
      const res = await queryRedeemCode(cardCode);
      setRedeemNote(resultText(res) || "已查询");
    } catch (error) {
      setRedeemNote(error instanceof Error ? error.message : "查询失败");
    } finally {
      setBusy("");
    }
  }

  async function handleRedeem() {
    if (!user) return;
    const cardCode = code.trim().toUpperCase();
    if (!cardCode) { setRedeemNote("请填写卡密"); return; }
    setBusy("redeem");
    try {
      const res = await redeemCode({ user_id: user.user_id, user_token: user.token, code: cardCode });
      setRedeemNote(resultText(res) || (res.ok ? "兑换成功" : "兑换失败"));
      if (res.ok) setCode("");
    } catch (error) {
      setRedeemNote(error instanceof Error ? error.message : "兑换失败");
    } finally {
      setBusy("");
    }
  }

  return (
    <section id="beta-redeem" className="pb-9 grid gap-3 lg:grid-cols-[0.82fr_1fr] max-w-[980px]">
      {/* ── 左卡：账号状态 ── */}
      <Card variant="raised" size="sm" className="min-h-[218px] bg-[color-mix(in_oklch,var(--color-paper-hi),var(--color-white)_28%)]">
        <div className="flex h-[66px] items-start justify-between gap-3">
          <div>
            <span className="inline-flex h-5 items-center gap-1 rounded-pill bg-brand-tint px-2.5 text-micro font-medium leading-none text-brand">
              <span className="h-1.5 w-1.5 rounded-full bg-current opacity-80" />
              AI 就绪
            </span>
          <h2 className="mt-2 font-wenkai text-h3 font-normal text-brand">
              {isLoggedIn ? "账号中心" : "内测中心"}
            </h2>
            <p className="text-meta text-ink-2 mt-0.5">小纸笺 · 幼师工作台 · v1.2.1</p>
          </div>
          <span className="h-7 px-3 rounded-pill bg-success border border-success inline-flex items-center text-meta font-semibold leading-none text-white shadow-xs">
            内测版
          </span>
        </div>

        {isLoggedIn && user ? (
          /* 已登录 — 显示账号信息 */
          <div className="mt-5 space-y-2">
            <div className="flex items-center gap-2">
              <div className="w-9 h-9 rounded-full bg-brand text-white grid place-items-center text-body-sm font-semibold">
                {user.member_no.slice(-4) || user.account_id.replace(/\D/g, "").slice(-4) || user.account_id[0]?.toUpperCase()}
              </div>
              <div>
                <p className="text-body-sm font-medium text-ink">会员号 {user.member_no || "未分配"}</p>
                <p className="text-meta text-ink-3">
                  {{ teacher: "幼师", org_admin: "园长", guest: "游客", platform_admin: "管理员" }[user.role] ?? user.role}
                </p>
              </div>
            </div>
            <p className="text-meta text-ink-3 pt-1">已登录，可在右侧兑换卡密</p>
          </div>
        ) : (
          /* 未登录 — 引导注册 */
          <div className="mt-4 space-y-3">
            <p className="text-meta text-ink-2">注册后系统自动分配会员号，使用会员号和密码登录</p>
            <div className="flex gap-3">
              <button
                type="button"
                onClick={() => setAuthOpen(true)}
                className="h-8 px-5 rounded-pill bg-success text-white text-body-sm font-semibold border border-success shadow-sm hover:brightness-105 active:brightness-95 whitespace-nowrap"
              >
                注册 / 登录
              </button>
              <p className="text-meta text-ink-3 self-center">内测版 · 轻量高效</p>
            </div>
          </div>
        )}
      </Card>

      {/* ── 右卡：兑换中心 ── */}
      <Card variant="raised" size="sm" className="min-h-[218px] bg-[color-mix(in_oklch,var(--color-paper-hi),var(--color-white)_24%)]">
        <div className="flex h-[66px] items-start justify-between gap-3">
          <div>
            <span className="inline-flex h-5 items-center gap-1 rounded-pill bg-brand-tint px-2.5 text-micro font-medium leading-none text-brand">
              <span className="h-1.5 w-1.5 rounded-full bg-current opacity-80" />
              权益
            </span>
          <h2 className="mt-2 font-wenkai text-h3 font-normal text-brand">兑换中心</h2>
            <p className="text-meta text-ink-2 mt-0.5">卡密兑换 · 次数 · 会员 · 余额</p>
          </div>
          <a href="#top" className="h-7 px-3 rounded-pill bg-paper-hi border border-rule inline-flex items-center text-meta leading-none text-ink-2 hover:bg-paper-sunk">
            返回顶部
          </a>
        </div>

        {isLoggedIn ? (
          <>
            <div className="mt-4 flex items-center gap-3">
              <div className="flex-1">
                <p className="text-meta text-ink-3 mb-1.5">当前账号</p>
                <div className="h-8 px-3 rounded-sm border border-rule bg-paper-sunk flex items-center text-body-sm text-ink-2">
                  会员号 {user?.member_no || "未分配"}
                </div>
              </div>
              <div className="flex-1">
                <p className="text-meta text-ink-3 mb-1.5">卡密</p>
                <input
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  className="h-8 w-full px-3 rounded-sm border border-rule bg-white text-body-sm text-ink placeholder:text-ink-4 focus:border-brand focus:shadow-focus"
                  placeholder="请输入卡密"
                />
              </div>
            </div>

            <div className="mt-3 flex flex-col sm:flex-row gap-3 sm:items-center">
              <button
                type="button"
                disabled={!canUseCode || Boolean(busy)}
                onClick={handleRedeem}
                className="h-8 px-5 rounded-pill bg-success text-white text-body-sm font-semibold border border-success shadow-sm hover:brightness-105 active:brightness-95 disabled:opacity-45 disabled:pointer-events-none"
              >
                {busy === "redeem" ? "兑换中" : "立即兑换"}
              </button>
              <Button
                variant="secondary"
                size="sm"
                disabled={!code.trim() || Boolean(busy)}
                onClick={handleQuery}
              >
                {busy === "query" ? "查询中" : "查询状态"}
              </Button>
              <p className="text-meta text-ink-2 sm:ml-auto">{redeemNote}</p>
            </div>
          </>
        ) : (
          <div className="mt-5 flex flex-col items-start gap-3">
            <p className="text-meta text-ink-2">请先登录账号，再使用卡密兑换权益</p>
            <button
              type="button"
              onClick={() => setAuthOpen(true)}
              className="h-8 px-5 rounded-pill bg-brand text-white text-body-sm font-semibold border border-brand shadow-sm hover:brightness-105 active:brightness-95"
            >
              登录账号
            </button>
          </div>
        )}
      </Card>

      <AuthModal
        open={authOpen}
        defaultTab="login"
        onClose={() => setAuthOpen(false)}
        onSuccess={handleAuthSuccess}
      />
    </section>
  );
}
