"use client";

/**
 * AuthModal — 注册 / 登录弹窗
 *
 * 注册：只填密码 → 系统自动分配会员号（如 94610）
 * 登录：会员号 + 密码
 *
 * 手机号只在小程序绑定时使用，Web 完全不涉及。
 */

import { useEffect, useId, useRef, useState } from "react";
import { useAuth, type AuthUser } from "@/lib/useAuth";
import {
  ApiError,
  type AuthResponse,
  type RedeemResponse,
  registerUser,
  loginUser,
  queryRedeemCode,
  redeemCode,
} from "@/lib/api";

type Tab = "register" | "login";
type RegisterRole = "teacher" | "org_admin" | "guest";
type RedeemAuthMode = "existing" | "new";

const REGISTER_ROLE_OPTIONS: Array<{
  value: RegisterRole;
  label: string;
  hint: string;
}> = [
  { value: "teacher", label: "幼师", hint: "适合日常生成周计划、观察记录" },
  { value: "org_admin", label: "园长", hint: "适合园所统筹与教研管理" },
  { value: "guest", label: "游客", hint: "先体验界面与基础流程" },
];

interface AuthModalProps {
  open: boolean;
  onClose: () => void;
  onSuccess: (data: AuthResponse) => void;
  defaultTab?: Tab;
  spotlightSection?: "redeem" | null;
  isLoggedIn?: boolean;
  authUser?: AuthUser | null;
}

const INPUT_CLS =
  "h-10 w-full px-3 rounded-sm border border-rule bg-white text-body-sm text-ink placeholder:text-ink-4 focus:outline-none focus:border-brand focus:shadow-focus transition-colors";

const LABEL_CLS = "block text-meta text-ink-3 mb-1.5 font-medium";

function getRoleOption(role: RegisterRole) {
  return REGISTER_ROLE_OPTIONS.find((option) => option.value === role) ?? REGISTER_ROLE_OPTIONS[0];
}

function RoleSelect({
  value,
  onChange,
  disabled = false,
}: {
  value: RegisterRole;
  onChange: (value: RegisterRole) => void;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  const listboxId = useId();
  const selected = getRoleOption(value);

  useEffect(() => {
    if (!open) return;
    function handlePointerDown(event: MouseEvent) {
      if (!wrapRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    function handleEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("keydown", handleEscape);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleEscape);
    };
  }, [open]);

  return (
    <div ref={wrapRef} className="relative">
      <button
        type="button"
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listboxId}
        onClick={() => !disabled && setOpen((current) => !current)}
        className={[
          "flex h-10 w-full items-center justify-between rounded-sm border border-rule bg-white px-3 text-left text-body-sm text-ink transition-colors",
          "focus:outline-none focus:border-brand focus:shadow-focus",
          disabled ? "opacity-50" : "hover:border-[color-mix(in_oklch,var(--color-brand),transparent_55%)]",
          open ? "border-brand shadow-focus" : "",
        ].join(" ")}
      >
        <span>{selected.label} · {selected.hint}</span>
        <span className={["text-ink-3 transition-transform", open ? "rotate-180" : ""].join(" ")}>▾</span>
      </button>

      {open ? (
        <div
          id={listboxId}
          role="listbox"
          className="absolute left-0 right-0 top-[calc(100%+6px)] z-10 overflow-hidden rounded-md border border-rule bg-white shadow-[0_18px_34px_rgba(47,38,28,0.16)]"
        >
          {REGISTER_ROLE_OPTIONS.map((option) => {
            const active = option.value === value;
            return (
              <button
                key={option.value}
                type="button"
                role="option"
                aria-selected={active}
                onClick={() => {
                  onChange(option.value);
                  setOpen(false);
                }}
                className={[
                  "flex w-full items-center px-4 py-3 text-left text-body-sm transition-colors",
                  active
                    ? "bg-[#213754] text-white"
                    : "text-ink hover:bg-[color-mix(in_oklch,#213754,white_90%)]",
                ].join(" ")}
              >
                <span>{option.label} · {option.hint}</span>
              </button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}

export function AuthModal({
  open,
  onClose,
  onSuccess,
  defaultTab = "login",
  spotlightSection = null,
  isLoggedIn = false,
  authUser = null,
}: AuthModalProps) {
  const { logout } = useAuth();
  const [tab, setTab]           = useState<Tab>(defaultTab);
  const [memberNo, setMemberNo] = useState("");   // 登录用
  const [password, setPassword] = useState("");
  const [confirm, setConfirm]   = useState("");
  const [registerRole, setRegisterRole] = useState<RegisterRole>("teacher");
  const [busy, setBusy]         = useState(false);
  const [error, setError]       = useState("");
  const [newMemberNo, setNewMemberNo] = useState(""); // 注册成功后显示
  const [registerData, setRegisterData] = useState<AuthResponse | null>(null); // 注册成功数据
  const [redeemCodeValue, setRedeemCodeValue] = useState("");
  const [redeemBusy, setRedeemBusy] = useState<"" | "query" | "redeem">("");
  const [redeemNote, setRedeemNote] = useState("输入卡号后可先查询状态，再完成兑换");
  const [redeemAuthMode, setRedeemAuthMode] = useState<RedeemAuthMode>("existing");
  const overlayRef = useRef<HTMLDivElement>(null);
  const redeemCardRef = useRef<HTMLDivElement>(null);

  function switchTab(t: Tab) {
    setTab(t);
    setError("");
    setPassword("");
    setConfirm("");
    setMemberNo("");
    setNewMemberNo("");
    setRegisterData(null);
    setRegisterRole("teacher");
  }

  function handleClose() {
    setBusy(false);
    setError("");
    setNewMemberNo("");
    setRegisterData(null);
    onClose();
  }

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") handleClose();
    }
    if (open) document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  useEffect(() => {
    if (open) document.body.style.overflow = "hidden";
    else document.body.style.overflow = "";
    return () => { document.body.style.overflow = ""; };
  }, [open]);

  useEffect(() => {
    if (!open || spotlightSection !== "redeem") return;
    const timer = window.setTimeout(() => {
      redeemCardRef.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }, 120);
    return () => window.clearTimeout(timer);
  }, [open, spotlightSection, tab]);


  useEffect(() => {
    if (!open) return;
    setTab(defaultTab);
    setRedeemAuthMode("existing");
  }, [open, defaultTab]);

  if (!open) return null;

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
      return [
        message || "可用",
        service,
        response.expires_at ? `截止 ${String(response.expires_at).split("T")[0]}` : "",
      ].filter(Boolean).join(" · ");
    }
    return [message || status || "未完成", service].filter(Boolean).join(" · ");
  }

  function validate(): string {
    const pw = password.trim();
    if (tab === "login" && !memberNo.trim()) return "请填写会员号";
    if (pw.length < 6) return "密码至少 6 位";
    if (tab === "register" && pw !== confirm.trim()) return "两次密码不一致";
    return "";
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const validationError = validate();
    if (validationError) { setError(validationError); return; }

    setBusy(true);
    setError("");
    try {
      if (tab === "register") {
        const data = await registerUser({
          password: password.trim(),
          role: registerRole,
        });
        setNewMemberNo(data.member_no || "");
        setRegisterData(data);
      } else {
        const data = await loginUser({
          member_no: memberNo.trim(),
          password:  password.trim(),
        });
        onSuccess(data);
        setMemberNo("");
        setPassword("");
      }
    } catch (err: unknown) {
      let msg = "操作失败，请重试";
      if (err instanceof ApiError) {
        const body = err.body as { detail?: string } | undefined;
        msg = body?.detail || "服务器返回错误，请重试";
      } else if (err instanceof Error) {
        if (err.message === "Failed to fetch" || err.message.includes("fetch")) {
          msg = "网络连接失败，请检查网络后重试";
        } else if (err.message.includes("timeout") || err.message.includes("Timeout")) {
          msg = "请求超时，请稍后再试";
        } else {
          msg = "操作失败，请重试";
        }
      }
      setError(msg);
    } finally {
      setBusy(false);
    }
  }

  async function handleRedeemQuery() {
    const code = redeemCodeValue.trim().toUpperCase();
    if (!code) {
      setRedeemNote("请先输入卡号");
      return;
    }
    setRedeemBusy("query");
    try {
      const res = await queryRedeemCode(code);
      setRedeemNote(resultText(res) || "已查询");
    } catch (err: unknown) {
      setRedeemNote(err instanceof Error ? err.message : "查询失败");
    } finally {
      setRedeemBusy("");
    }
  }

  async function handleRedeemSubmit() {
    const code = redeemCodeValue.trim().toUpperCase();
    if (!code) {
      setRedeemNote("请先输入卡号");
      return;
    }
    if (!isLoggedIn || !authUser) {
      setRedeemNote("请先注册或登录，再完成兑换");
      switchTab("register");
      return;
    }
    setRedeemBusy("redeem");
    try {
      const res = await redeemCode({
        user_id: authUser.user_id,
        user_token: authUser.token,
        code,
        source: "web_workbench_beta_entry",
      });
      setRedeemNote(resultText(res) || (res.ok ? "兑换成功" : "兑换失败"));
      if (res.ok) {
        setRedeemCodeValue("");
      }
    } catch (err: unknown) {
      setRedeemNote(err instanceof Error ? err.message : "兑换失败");
    } finally {
      setRedeemBusy("");
    }
  }

  const redeemOnlyMode = spotlightSection === "redeem";

  async function doRedeem(userId: string, token: string) {
    const code = redeemCodeValue.trim().toUpperCase();
    if (!code) return;
    setRedeemBusy("redeem");
    try {
      const res = await redeemCode({
        user_id: userId,
        user_token: token,
        code,
        source: "web_workbench_beta_entry",
      });
      setRedeemNote(resultText(res) || (res.ok ? "兑换成功" : "兑换失败"));
      if (res.ok) setRedeemCodeValue("");
    } catch (err: unknown) {
      setRedeemNote(err instanceof Error ? err.message : "兑换失败");
    } finally {
      setRedeemBusy("");
    }
  }

  async function handleRedeemAuthSubmit() {
    const code = redeemCodeValue.trim().toUpperCase();
    if (!code) { setRedeemNote("请先输入卡号"); return; }

    if (redeemAuthMode === "existing") {
      if (!memberNo.trim()) { setError("请填写已有会员号"); return; }
      if (password.trim().length < 6) { setError("请输入正确密码"); return; }
      setBusy(true);
      setError("");
      try {
        const data = await loginUser({ member_no: memberNo.trim(), password: password.trim() });
        onSuccess(data);
        setMemberNo("");
        setPassword("");
        await doRedeem(data.user_id, data.user_token);
      } catch (err: unknown) {
        let msg = "登录失败，请重试";
        if (err instanceof ApiError) {
          const body = err.body as { detail?: string } | undefined;
          msg = body?.detail || "服务器返回错误，请重试";
        } else if (err instanceof Error) {
          if (err.message === "Failed to fetch" || err.message.includes("fetch")) {
            msg = "网络连接失败，请检查网络后重试";
          } else {
            msg = "登录失败，请重试";
          }
        }
        setError(msg);
      } finally {
        setBusy(false);
      }
      return;
    }

    // 新号码：注册 + 立即兑换
    if (password.trim().length < 6) { setError("密码至少 6 位"); return; }
    if (password.trim() !== confirm.trim()) { setError("两次密码不一致"); return; }
    setBusy(true);
    setError("");
    try {
      const data = await registerUser({ password: password.trim(), role: registerRole });
      setNewMemberNo(data.member_no || "");
      onSuccess(data);
      setPassword("");
      setConfirm("");
      await doRedeem(data.user_id, data.user_token);
    } catch (err: unknown) {
      let msg = "创建账号失败，请重试";
      if (err instanceof ApiError) {
        const body = err.body as { detail?: string } | undefined;
        msg = body?.detail || "服务器返回错误，请重试";
      } else if (err instanceof Error) {
        if (err.message === "Failed to fetch" || err.message.includes("fetch")) {
          msg = "网络连接失败，请检查网络后重试";
        } else {
          msg = "创建账号失败，请重试";
        }
      }
      setError(msg);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 z-[500] flex items-center justify-center p-4"
      style={{ background: "rgba(30,28,26,0.55)", backdropFilter: "blur(3px)" }}
      onClick={(e) => { if (e.target === overlayRef.current) handleClose(); }}
    >
      <div className="relative w-full max-w-[520px] rounded-xl bg-paper shadow-2xl border border-rule overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 pt-5 pb-0">
          <div className="flex items-center gap-2">
            <img src="/chick-happy.svg" alt="小纸笺" className="h-6 w-6 rounded-xs shadow-xs" />
            <span className="font-wenkai text-body tracking-wider text-ink">小纸笺</span>
          </div>
          <button
            onClick={handleClose}
            className="w-7 h-7 rounded-full text-ink-3 hover:bg-paper-sunk hover:text-ink grid place-items-center text-[18px] leading-none"
            aria-label="关闭"
          >
            ×
          </button>
        </div>

        {/* Tab switcher — 兑换模式下隐藏 */}
        <div className={["flex gap-0 mx-6 mt-5 bg-paper-sunk rounded-lg p-1", redeemOnlyMode ? "hidden" : ""].join(" ")}>
          {(["login", "register"] as Tab[]).map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => switchTab(t)}
              className={[
                "flex-1 h-8 rounded-md text-body-sm font-medium transition-all",
                tab === t ? "bg-white text-ink shadow-xs" : "text-ink-3 hover:text-ink",
              ].join(" ")}
            >
              {t === "login" ? "登录" : "注册"}
            </button>
          ))}
        </div>

        {/* 注册成功：显示会员号 + 确认按钮 */}
        {newMemberNo && !redeemOnlyMode ? (
          <div className="px-6 py-8 text-center">
            <p className="text-meta text-ink-3 mb-2">注册成功！你的会员号是</p>
            <p className="font-num text-[2.5rem] font-bold text-brand tracking-widest">{newMemberNo}</p>
            <p className="text-meta text-ink-4 mt-3">请牢记此号码，登录时使用</p>
            <button
              className="mt-6 h-10 rounded-pill bg-brand px-8 text-sm font-medium text-white hover:opacity-90 active:opacity-80 transition-opacity"
              onClick={() => {
                if (!registerData) return;
                const data = registerData;
                setPassword("");
                setConfirm("");
                setNewMemberNo("");
                setRegisterData(null);
                onSuccess(data);
              }}
            >
              进入工作台
            </button>
          </div>
        ) : (
          /* Form — 兑换模式下禁用表单默认提交，避免回车误触 handleSubmit */
          <form onSubmit={redeemOnlyMode ? (e) => e.preventDefault() : handleSubmit} className="px-6 pt-5 pb-6 flex flex-col gap-4">
            {spotlightSection === "redeem" && (
              <div
                ref={redeemCardRef}
                className="rounded-xl border border-brand bg-[linear-gradient(180deg,rgba(255,255,255,0.86),rgba(247,245,242,0.98))] px-4 py-4 shadow-[0_0_0_3px_rgba(210,106,61,0.10),0_16px_30px_rgba(76,60,40,0.10)]"
              >
                <div className="flex items-center justify-between gap-3">
                  <span className="inline-flex h-6 items-center gap-1 rounded-pill bg-brand-tint px-2.5 text-micro font-medium leading-none text-brand">
                    <span className="h-1.5 w-1.5 rounded-full bg-current opacity-80" />
                    权益
                  </span>
                  <span className="text-[11px] tracking-[0.18em] text-ink-4">MEMBERSHIP</span>
                </div>
                <div className="mt-3 flex items-start justify-between gap-3">
                  <div>
                    <h3 className="font-wenkai text-[1.55rem] leading-none text-brand">兑换中心</h3>
                    <p className="mt-2 text-meta leading-6 text-ink-2">
                      当前入口对应 30 天月度会员卡。输入卡号后可先查状态，登录后立即兑换并写入你的账号权益。
                    </p>
                  </div>
                  {isLoggedIn && authUser ? (
                    <button
                      type="button"
                      onClick={logout}
                      className="shrink-0 h-8 px-3 rounded-pill border border-rule bg-paper-hi text-meta text-ink-2 hover:bg-paper-sunk"
                    >
                      切换账号
                    </button>
                  ) : null}
                </div>

                <div className="mt-4 grid gap-3 sm:grid-cols-[1.2fr_0.8fr]">
                  <div>
                    <label className={LABEL_CLS}>卡号</label>
                    <input
                      type="text"
                      value={redeemCodeValue}
                      onChange={(e) => setRedeemCodeValue(e.target.value.toUpperCase())}
                      placeholder="请输入兑换卡号"
                      className={INPUT_CLS}
                      disabled={Boolean(redeemBusy)}
                    />
                  </div>
                  <div>
                    <label className={LABEL_CLS}>当前账号</label>
                    <div className="h-10 px-3 rounded-sm border border-rule bg-paper-sunk flex items-center text-body-sm text-ink-2">
                      {isLoggedIn && authUser ? `会员号 ${authUser.member_no || authUser.user_id}` : "未登录"}
                    </div>
                  </div>
                </div>

                <div className="mt-3 flex flex-col gap-3 sm:flex-row sm:items-center">
                  <button
                    type="button"
                    onClick={handleRedeemQuery}
                    disabled={!redeemCodeValue.trim() || Boolean(redeemBusy)}
                    className="h-8 px-5 rounded-pill bg-paper-hi text-ink text-body-sm font-semibold border border-rule hover:bg-paper-sunk disabled:opacity-45 disabled:pointer-events-none"
                  >
                    {redeemBusy === "query" ? "查询中…" : "查询状态"}
                  </button>
                  <button
                    type="button"
                    onClick={isLoggedIn && authUser ? handleRedeemSubmit : () => void handleRedeemAuthSubmit()}
                    disabled={!redeemCodeValue.trim() || Boolean(redeemBusy) || busy}
                    className="h-8 px-5 rounded-pill bg-brand text-white text-body-sm font-semibold border border-brand shadow-sm hover:brightness-105 active:brightness-95 disabled:opacity-45 disabled:pointer-events-none"
                  >
                    {redeemBusy === "redeem" || busy
                      ? "兑换中…"
                      : isLoggedIn && authUser
                        ? "立即兑换"
                        : redeemAuthMode === "existing" ? "登录并兑换" : "注册并兑换"}
                  </button>
                  <p className="text-meta text-ink-3 sm:ml-auto">
                    {isLoggedIn && authUser ? "兑换成功后会直接抵扣本地卡密库存" : "未登录也可先查询卡密状态"}
                  </p>
                </div>

                <div className="mt-3 rounded-lg bg-paper-sunk px-3 py-2 text-meta text-ink-2">
                  {redeemNote}
                </div>

                {!isLoggedIn && (
                  <div className="mt-4 rounded-xl border border-rule bg-white px-4 py-4">
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => {
                          setRedeemAuthMode("existing");
                          setError("");
                        }}
                        className={[
                          "h-8 rounded-pill px-4 text-body-sm font-medium transition-colors",
                          redeemAuthMode === "existing"
                            ? "bg-paper-hi text-ink shadow-xs"
                            : "text-ink-3 hover:text-ink",
                        ].join(" ")}
                      >
                        绑定已有号码
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setRedeemAuthMode("new");
                          setError("");
                        }}
                        className={[
                          "h-8 rounded-pill px-4 text-body-sm font-medium transition-colors",
                          redeemAuthMode === "new"
                            ? "bg-paper-hi text-ink shadow-xs"
                            : "text-ink-3 hover:text-ink",
                        ].join(" ")}
                      >
                        分配新号码
                      </button>
                    </div>

                    <div className="mt-4 flex flex-col gap-3">
                      {redeemAuthMode === "existing" ? (
                        <>
                          <div className="grid gap-3 sm:grid-cols-2">
                            <div>
                              <label className={LABEL_CLS}>已有会员号</label>
                              <input
                                type="text"
                                value={memberNo}
                                onChange={(e) => setMemberNo(e.target.value)}
                                placeholder="请输入已有会员号"
                                className={INPUT_CLS}
                                disabled={busy}
                              />
                            </div>
                            <div>
                              <label className={LABEL_CLS}>密码</label>
                              <input
                                type="password"
                                autoComplete="current-password"
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                                placeholder="请输入密码"
                                className={INPUT_CLS}
                                disabled={busy}
                              />
                            </div>
                          </div>
                          <button
                            type="button"
                            onClick={() => void handleRedeemAuthSubmit()}
                            disabled={busy}
                            className="h-10 rounded-pill bg-brand text-white text-body-sm font-semibold border border-brand shadow-sm hover:brightness-105 active:brightness-95 disabled:opacity-45"
                          >
                            {busy ? "绑定中…" : "绑定并继续兑换"}
                          </button>
                        </>
                      ) : (
                        <>
                          <p className="rounded-lg bg-paper-sunk px-3 py-2 text-meta text-ink-2">
                            没有会员号也没关系，这里会像注册一样直接分配一个新号码给你。
                          </p>
                          <div>
                            <label className={LABEL_CLS}>身份</label>
                            <RoleSelect value={registerRole} onChange={setRegisterRole} disabled={busy} />
                          </div>
                          <div className="grid gap-3 sm:grid-cols-2">
                            <div>
                              <label className={LABEL_CLS}>密码</label>
                              <input
                                type="password"
                                autoComplete="new-password"
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                                placeholder="设置密码（至少 6 位）"
                                className={INPUT_CLS}
                                disabled={busy}
                              />
                            </div>
                            <div>
                              <label className={LABEL_CLS}>确认密码</label>
                              <input
                                type="password"
                                autoComplete="new-password"
                                value={confirm}
                                onChange={(e) => setConfirm(e.target.value)}
                                placeholder="再次输入密码"
                                className={INPUT_CLS}
                                disabled={busy}
                              />
                            </div>
                          </div>
                          <button
                            type="button"
                            onClick={() => void handleRedeemAuthSubmit()}
                            disabled={busy}
                            className="h-10 rounded-pill bg-brand text-white text-body-sm font-semibold border border-brand shadow-sm hover:brightness-105 active:brightness-95 disabled:opacity-45"
                          >
                            {busy ? "分配中…" : "分配新号码并继续兑换"}
                          </button>
                          {newMemberNo ? (
                            <p className="rounded-lg bg-brand-tint px-3 py-2 text-body-sm text-brand">
                              已分配会员号 {newMemberNo}，当前已绑定到账户，可直接兑换。
                            </p>
                          ) : null}
                        </>
                      )}
                    </div>
                  </div>
                )}
              </div>
            )}

            {redeemOnlyMode ? (
              <>
                {error && (
                  <p className="rounded-md bg-[color-mix(in_oklch,var(--color-danger),transparent_90%)] px-3 py-2 text-meta text-danger-ink">
                    {error}
                  </p>
                )}
              </>
            ) : (
              <>

                {/* 登录：会员号输入框 */}
                {tab === "login" && (
                  <div>
                    <label className={LABEL_CLS}>会员号</label>
                    <input
                      type="text"
                      inputMode="numeric"
                      autoComplete="username"
                      value={memberNo}
                      onChange={(e) => setMemberNo(e.target.value)}
                      placeholder="请输入会员号（如 94610）"
                      className={INPUT_CLS}
                      disabled={busy}
                    />
                  </div>
                )}

                {/* 注册：说明文字 */}
                {tab === "register" && (
                  <div className="bg-paper-sunk rounded-lg px-4 py-3">
                    <p className="text-meta text-ink-2">
                      注册后系统自动分配你的会员号，请妥善保存，登录时使用。
                    </p>
                  </div>
                )}

                {tab === "register" && (
                  <div>
                    <label className={LABEL_CLS}>身份</label>
                    <RoleSelect value={registerRole} onChange={setRegisterRole} disabled={busy} />
                  </div>
                )}

                <div>
                  <label className={LABEL_CLS}>密码</label>
                  <input
                    type="password"
                    autoComplete={tab === "register" ? "new-password" : "current-password"}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder={tab === "register" ? "设置密码（至少 6 位）" : "请输入密码"}
                    className={INPUT_CLS}
                    disabled={busy}
                  />
                </div>

                {tab === "register" && (
                  <div>
                    <label className={LABEL_CLS}>确认密码</label>
                    <input
                      type="password"
                      autoComplete="new-password"
                      value={confirm}
                      onChange={(e) => setConfirm(e.target.value)}
                      placeholder="再次输入密码"
                      className={INPUT_CLS}
                      disabled={busy}
                    />
                  </div>
                )}

                {error && (
                  <p className="rounded-md bg-[color-mix(in_oklch,var(--color-danger),transparent_90%)] px-3 py-2 text-meta text-danger-ink">
                    {error}
                  </p>
                )}

                <button
                  type="submit"
                  disabled={busy}
                  className="mt-1 h-10 w-full rounded-pill bg-brand text-white text-body-sm font-semibold border border-brand shadow-sm hover:brightness-105 active:brightness-95 disabled:opacity-45 disabled:pointer-events-none transition-all"
                >
                  {busy
                    ? (tab === "register" ? "注册中…" : "登录中…")
                    : (tab === "register" ? "创建账号" : "登录")}
                </button>

                <p className="text-center text-meta text-ink-3">
                  {tab === "login" ? "还没有账号？" : "已有账号？"}
                  <button
                    type="button"
                    onClick={() => switchTab(tab === "login" ? "register" : "login")}
                    className="ml-1 text-brand hover:underline font-medium"
                  >
                    {tab === "login" ? "立即注册" : "去登录"}
                  </button>
                </p>

              </>
            )}
          </form>
        )}
      </div>
    </div>
  );
}
