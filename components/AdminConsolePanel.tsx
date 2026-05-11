"use client";

import { useEffect, useMemo, useState } from "react";
import {
  ApiError,
  authorizeUser,
  getAdminGenerationLogs,
  getAdminUsers,
  getInternalBetaAccounts,
  getInternalBetaRedeemCodes,
  type AdminGenerationLog,
  type AdminUserRow,
  type InternalBetaAccount,
  type InternalRedeemCode,
} from "@/lib/api";
import { useAuth } from "@/lib/useAuth";

const roleLabel: Record<string, string> = {
  teacher: "幼师",
  org_admin: "园长",
  guest: "游客",
  platform_admin: "管理员",
};

function formatDate(value?: string | null): string {
  if (!value) return "未设置";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", { hour12: false });
}

function compactError(error: unknown): string {
  if (error instanceof ApiError) {
    const detail = (error.body as { detail?: string } | undefined)?.detail;
    return detail || error.message;
  }
  if (error instanceof Error) return error.message;
  return "请求失败，请稍后再试";
}

function membershipUntilAfterDays(days: number): string {
  const date = new Date();
  date.setUTCDate(date.getUTCDate() + days);
  date.setUTCHours(23, 59, 59, 0);
  return date.toISOString();
}

function exportUsersCsv(rows: AdminUserRow[]) {
  const header = ["member_no", "role", "permissions", "org_id", "phone_or_openid", "membership_until", "note"];
  const lines = rows.map((row) => [
    row.member_no || "",
    row.role || "",
    (row.permissions || []).join("|"),
    row.org_id || "",
    row.phone || row.openid || row.account_id || "",
    row.service?.membership_until || "",
    row.note || "",
  ]);
  const csv = [header, ...lines]
    .map((cols) => cols.map((value) => `"${String(value).replaceAll('"', '""')}"`).join(","))
    .join("\n");

  const blob = new Blob([`\ufeff${csv}`], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `小纸笺_用户权限表_${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

export function AdminConsolePanel() {
  const { user, isLoggedIn } = useAuth();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [betaAccounts, setBetaAccounts] = useState<InternalBetaAccount[]>([]);
  const [redeemCodes, setRedeemCodes] = useState<InternalRedeemCode[]>([]);
  const [redeemSummary, setRedeemSummary] = useState({ unused: 0, used: 0, expired: 0 });
  const [allUsers, setAllUsers] = useState<AdminUserRow[]>([]);
  const [generationLogs, setGenerationLogs] = useState<AdminGenerationLog[]>([]);
  const [query, setQuery] = useState("");
  const [roleFilter, setRoleFilter] = useState("all");
  const [grantStatus, setGrantStatus] = useState("");
  const [grantLoading, setGrantLoading] = useState(false);
  const [form, setForm] = useState({
    member_no: "",
    role: "",
    org_id: "",
    note: "",
    membership_until: "",
  });

  const memberNo = user?.member_no ?? "";
  const isPlatformAdmin = isLoggedIn && user?.role === "platform_admin";
  const canViewBeta = isPlatformAdmin && (memberNo === "1001" || memberNo === "10001");
  const canManageUsers = isPlatformAdmin && memberNo === "10001";

  useEffect(() => {
    if (!isPlatformAdmin || !user?.token) return;

    let cancelled = false;

    async function load() {
      setLoading(true);
      setError("");
      try {
        const betaPromise = canViewBeta ? getInternalBetaAccounts(user.token) : Promise.resolve(null);
        const redeemPromise = canViewBeta ? getInternalBetaRedeemCodes(user.token) : Promise.resolve(null);
        const adminPromise = canManageUsers ? getAdminUsers(user.token) : Promise.resolve(null);
        const logsPromise = canManageUsers ? getAdminGenerationLogs(user.token) : Promise.resolve(null);

        const [betaRes, redeemRes, adminRes, logsRes] = await Promise.all([betaPromise, redeemPromise, adminPromise, logsPromise]);
        if (cancelled) return;

        setBetaAccounts(betaRes?.accounts ?? []);
        setRedeemCodes(redeemRes?.codes ?? []);
        setRedeemSummary(redeemRes?.summary ?? { unused: 0, used: 0, expired: 0 });
        setAllUsers(adminRes?.users ?? []);
        setGenerationLogs(logsRes?.logs ?? []);
      } catch (err) {
        if (!cancelled) setError(compactError(err));
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [canManageUsers, canViewBeta, isPlatformAdmin, user?.token]);

  const filteredUsers = useMemo(() => {
    const keyword = query.trim().toLowerCase();
    let rows = allUsers.filter((row) => row.account_id || row.member_no || row.phone || row.openid);
    if (roleFilter !== "all") {
      rows = rows.filter((row) => row.role === roleFilter);
    }
    if (!keyword) return rows;
    return rows.filter((row) =>
      [
        row.member_no,
        row.account_id,
        row.role,
        row.org_id,
        row.note,
        row.phone,
        row.openid,
      ]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(keyword)),
    );
  }, [allUsers, query, roleFilter]);

  async function refreshUsers() {
    if (!user?.token || !canManageUsers) return;
    const [latest, logs] = await Promise.all([
      getAdminUsers(user.token),
      getAdminGenerationLogs(user.token),
    ]);
    setAllUsers(latest.users ?? []);
    setGenerationLogs(logs.logs ?? []);
  }

  async function submitAuthorize() {
    if (!user?.token || !form.member_no.trim()) {
      setGrantStatus("请先填写目标会员号");
      return;
    }

    setGrantLoading(true);
    setGrantStatus("");
    try {
      const result = await authorizeUser({
        user_token: user.token,
        member_no: form.member_no.trim(),
        role: form.role || undefined,
        org_id: form.org_id.trim(),
        note: form.note.trim(),
        membership_until: form.membership_until.trim(),
      });
      setGrantStatus(`已更新 ${result.member_no}，角色为 ${result.role}`);
      await refreshUsers();
    } catch (err) {
      setGrantStatus(compactError(err));
    } finally {
      setGrantLoading(false);
    }
  }

  async function quickGrantMembership(memberNoValue: string, days: number) {
    if (!user?.token) return;
    setGrantLoading(true);
    setGrantStatus("");
    try {
      await authorizeUser({
        user_token: user.token,
        member_no: memberNoValue,
        membership_until: membershipUntilAfterDays(days),
        note: `${days}天会员已由 10001 后台开通`,
      });
      setGrantStatus(`已为 ${memberNoValue} 开通 ${days} 天会员`);
      await refreshUsers();
    } catch (err) {
      setGrantStatus(compactError(err));
    } finally {
      setGrantLoading(false);
    }
  }

  function fillFormFromRow(row: AdminUserRow) {
    setForm({
      member_no: row.member_no || "",
      role: row.role || "",
      org_id: row.org_id || "",
      note: row.note || "",
      membership_until: row.service?.membership_until || "",
    });
  }

  if (!isPlatformAdmin) return null;

  return (
    <section id="admin-console" className="mt-10 space-y-6">
      <div className="rounded-[28px] border border-rule bg-white/90 p-6 shadow-[0_22px_70px_rgba(150,120,72,0.12)]">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full bg-success-tint px-3 py-1 text-meta font-semibold text-success-ink">
              <span className="h-2 w-2 rounded-full bg-success" />
              管理后台
            </div>
            <h2 className="mt-4 text-h1 leading-tight text-ink">账号权限与内测控制台</h2>
            <p className="mt-2 max-w-3xl text-body-sm text-ink-2">
              当前登录账号为 {memberNo}。1001 可查看另外 99 个内测号与 103 个兑换码使用情况；10001 额外可查看全量用户并执行授权。
            </p>
          </div>
          <div className="rounded-[24px] border border-rule bg-paper px-5 py-4 text-right">
            <p className="text-meta text-ink-3">当前角色</p>
            <p className="mt-1 text-h3 leading-tight text-ink">{roleLabel[user?.role ?? ""] ?? user?.role}</p>
            <p className="text-meta text-ink-3">会员号 {memberNo}</p>
          </div>
        </div>

        {error ? (
          <div className="mt-5 rounded-2xl border border-[color-mix(in_oklch,var(--color-brand),transparent_70%)] bg-[color-mix(in_oklch,var(--color-brand),white_92%)] px-4 py-3 text-body-sm text-brand">
            {error}
          </div>
        ) : null}

          <div className="mt-6 grid gap-4 lg:grid-cols-4">
            <div className="rounded-[24px] border border-rule bg-paper px-5 py-4">
              <p className="text-meta text-ink-3">内测账号</p>
              <p className="mt-2 font-num text-[2rem] leading-none text-ink">{betaAccounts.length}</p>
              <p className="text-meta text-ink-3">{memberNo === "1001" ? "你可查看另外 99 个" : "当前整组内测账号"}</p>
            </div>
            <div className="rounded-[24px] border border-rule bg-paper px-5 py-4">
              <p className="text-meta text-ink-3">兑换码库存</p>
              <p className="mt-2 font-num text-[2rem] leading-none text-ink">{redeemCodes.length}</p>
              <p className="text-meta text-ink-3">30 天月卡为主</p>
            </div>
            <div className="rounded-[24px] border border-rule bg-paper px-5 py-4">
              <p className="text-meta text-ink-3">未使用</p>
              <p className="mt-2 font-num text-[2rem] leading-none text-success-ink">{redeemSummary.unused}</p>
              <p className="text-meta text-ink-3">可直接兑换</p>
            </div>
            <div className="rounded-[24px] border border-rule bg-paper px-5 py-4">
              <p className="text-meta text-ink-3">主账号可见用户</p>
              <p className="mt-2 font-num text-[2rem] leading-none text-ink">{canManageUsers ? allUsers.length : "--"}</p>
              <p className="text-meta text-ink-3">{canManageUsers ? "含权限字段" : "仅 10001 可查看"}</p>
            </div>
          </div>

        <div className="mt-6 grid gap-6 xl:grid-cols-[1.05fr_1.15fr]">
          <div className="rounded-[26px] border border-rule bg-paper px-5 py-5">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-h4 text-ink">内测账号列表</p>
                <p className="text-meta text-ink-3">1001 可见 1002-1100；10001 可见整组</p>
              </div>
              <div className="rounded-full bg-white px-3 py-1 text-meta font-num text-ink-3">
                {loading ? "加载中" : `${betaAccounts.length} 个`}
              </div>
            </div>
            <div className="mt-4 max-h-[420px] overflow-auto rounded-[20px] border border-rule bg-white">
              <table className="min-w-full text-left text-body-sm">
                <thead className="sticky top-0 bg-paper">
                  <tr className="text-ink-3">
                    <th className="px-4 py-3 font-medium">会员号</th>
                    <th className="px-4 py-3 font-medium">角色</th>
                    <th className="px-4 py-3 font-medium">园所</th>
                    <th className="px-4 py-3 font-medium">更新时间</th>
                  </tr>
                </thead>
                <tbody>
                  {betaAccounts.map((row) => (
                    <tr key={row.account_id} className="border-t border-rule text-ink-2">
                      <td className="px-4 py-3 font-num text-ink">{row.member_no}</td>
                      <td className="px-4 py-3">{row.role}</td>
                      <td className="px-4 py-3">{row.org_id || "--"}</td>
                      <td className="px-4 py-3">{formatDate(row.updated_at_utc)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="rounded-[26px] border border-rule bg-paper px-5 py-5">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-h4 text-ink">兑换码使用情况</p>
                <p className="text-meta text-ink-3">当前 103 个码，其中大部分为 30 天月卡</p>
              </div>
              <div className="flex gap-2 text-meta">
                <span className="rounded-full bg-white px-3 py-1 text-success-ink">未用 {redeemSummary.unused}</span>
                <span className="rounded-full bg-white px-3 py-1 text-ink-3">已用 {redeemSummary.used}</span>
              </div>
            </div>
            <div className="mt-4 max-h-[420px] overflow-auto rounded-[20px] border border-rule bg-white">
              <table className="min-w-full text-left text-body-sm">
                <thead className="sticky top-0 bg-paper">
                  <tr className="text-ink-3">
                    <th className="px-4 py-3 font-medium">卡密</th>
                    <th className="px-4 py-3 font-medium">状态</th>
                    <th className="px-4 py-3 font-medium">权益</th>
                    <th className="px-4 py-3 font-medium">使用人</th>
                  </tr>
                </thead>
                <tbody>
                  {redeemCodes.map((row) => (
                    <tr key={row.code} className="border-t border-rule text-ink-2">
                      <td className="px-4 py-3 font-num text-ink">{row.code}</td>
                      <td className="px-4 py-3">{row.status}</td>
                      <td className="px-4 py-3">{row.service?.name || row.description || "--"}</td>
                      <td className="px-4 py-3">{row.used_by || "--"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        {canManageUsers ? (
          <>
          <div className="mt-6 rounded-[26px] border border-rule bg-paper px-5 py-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-h4 text-ink">生成日志</p>
                <p className="text-meta text-ink-3">最近 {generationLogs.length} 条，含周计划、日教案、模型与耗时</p>
              </div>
              <button
                type="button"
                onClick={() => void refreshUsers()}
                className="h-10 rounded-2xl border border-rule bg-white px-4 text-body-sm font-medium text-ink hover:bg-paper-hi"
              >
                刷新日志
              </button>
            </div>
            <div className="mt-4 max-h-[420px] overflow-auto rounded-[20px] border border-rule bg-white">
              <table className="min-w-full text-left text-body-sm">
                <thead className="sticky top-0 bg-paper">
                  <tr className="text-ink-3">
                    <th className="px-4 py-3 font-medium">时间</th>
                    <th className="px-4 py-3 font-medium">会员号</th>
                    <th className="px-4 py-3 font-medium">类型</th>
                    <th className="px-4 py-3 font-medium">主题</th>
                    <th className="px-4 py-3 font-medium">模型</th>
                    <th className="px-4 py-3 font-medium">耗时</th>
                    <th className="px-4 py-3 font-medium">状态</th>
                  </tr>
                </thead>
                <tbody>
                  {generationLogs.map((row) => (
                    <tr key={row.record_id} className="border-t border-rule text-ink-2">
                      <td className="px-4 py-3 whitespace-nowrap">{formatDate(row.created_at_utc)}</td>
                      <td className="px-4 py-3 font-num text-ink">{row.member_no || "--"}</td>
                      <td className="px-4 py-3">{row.type}</td>
                      <td className="px-4 py-3 min-w-[220px]">
                        <p className="text-ink">{row.title || row.theme || "--"}</p>
                        <p className="text-meta text-ink-3">{[row.class_level, row.phil].filter(Boolean).join(" · ")}</p>
                      </td>
                      <td className="px-4 py-3">{row.model_used || "--"}</td>
                      <td className="px-4 py-3 font-num">
                        {typeof row.duration_ms === "number" ? `${Math.round(row.duration_ms / 100) / 10}s` : "--"}
                      </td>
                      <td className="px-4 py-3">{row.status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="mt-6 grid gap-6 xl:grid-cols-[0.86fr_1.14fr]">
            <div className="rounded-[26px] border border-rule bg-paper px-5 py-5">
              <div>
                <p className="text-h4 text-ink">审核授权</p>
                <p className="text-meta text-ink-3">10001 可按会员号调整角色、园所和会员到期时间</p>
              </div>
              <div className="mt-4 space-y-3">
                <input
                  value={form.member_no}
                  onChange={(e) => setForm((prev) => ({ ...prev, member_no: e.target.value }))}
                  className="h-11 w-full rounded-2xl border border-rule bg-white px-4 text-body-sm text-ink outline-none focus:border-brand"
                  placeholder="目标会员号，例如 60232"
                />
                <select
                  value={form.role}
                  onChange={(e) => setForm((prev) => ({ ...prev, role: e.target.value }))}
                  className="h-11 w-full rounded-2xl border border-rule bg-white px-4 text-body-sm text-ink outline-none focus:border-brand"
                >
                  <option value="">角色不变</option>
                  <option value="teacher">幼师</option>
                  <option value="org_admin">园长</option>
                  <option value="guest">游客</option>
                  <option value="platform_admin">管理员</option>
                </select>
                <input
                  value={form.org_id}
                  onChange={(e) => setForm((prev) => ({ ...prev, org_id: e.target.value }))}
                  className="h-11 w-full rounded-2xl border border-rule bg-white px-4 text-body-sm text-ink outline-none focus:border-brand"
                  placeholder="org_id，可选"
                />
                <input
                  value={form.membership_until}
                  onChange={(e) => setForm((prev) => ({ ...prev, membership_until: e.target.value }))}
                  className="h-11 w-full rounded-2xl border border-rule bg-white px-4 text-body-sm text-ink outline-none focus:border-brand"
                  placeholder="会员到期，如 2027-12-31T23:59:59+00:00"
                />
                <textarea
                  value={form.note}
                  onChange={(e) => setForm((prev) => ({ ...prev, note: e.target.value }))}
                  className="min-h-[110px] w-full rounded-[22px] border border-rule bg-white px-4 py-3 text-body-sm text-ink outline-none focus:border-brand"
                  placeholder="备注，例如：评审体验账号 / 内部管理员"
                />
                <div className="grid grid-cols-3 gap-2">
                  <button
                    type="button"
                    onClick={() => setForm((prev) => ({ ...prev, membership_until: membershipUntilAfterDays(30) }))}
                    className="h-10 rounded-2xl border border-rule bg-white text-body-sm text-ink hover:bg-paper-hi"
                  >
                    30天会员
                  </button>
                  <button
                    type="button"
                    onClick={() => setForm((prev) => ({ ...prev, membership_until: membershipUntilAfterDays(90) }))}
                    className="h-10 rounded-2xl border border-rule bg-white text-body-sm text-ink hover:bg-paper-hi"
                  >
                    90天会员
                  </button>
                  <button
                    type="button"
                    onClick={() => setForm((prev) => ({ ...prev, membership_until: membershipUntilAfterDays(365) }))}
                    className="h-10 rounded-2xl border border-rule bg-white text-body-sm text-ink hover:bg-paper-hi"
                  >
                    365天会员
                  </button>
                </div>
                <button
                  type="button"
                  onClick={() => void submitAuthorize()}
                  disabled={grantLoading}
                  className="h-11 w-full rounded-2xl bg-brand text-body font-semibold text-white transition hover:brightness-105 disabled:cursor-not-allowed disabled:opacity-70"
                >
                  {grantLoading ? "提交中..." : "保存授权"}
                </button>
                {grantStatus ? <p className="text-body-sm text-ink-2">{grantStatus}</p> : null}
              </div>
            </div>

            <div className="rounded-[26px] border border-rule bg-paper px-5 py-5">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-h4 text-ink">全量用户与权限</p>
                  <p className="text-meta text-ink-3">可搜索会员号、手机号、openid、角色、备注</p>
                </div>
                <div className="flex w-full max-w-[620px] flex-wrap items-center gap-2">
                  <select
                    value={roleFilter}
                    onChange={(e) => setRoleFilter(e.target.value)}
                    className="h-10 rounded-2xl border border-rule bg-white px-4 text-body-sm text-ink outline-none focus:border-brand"
                  >
                    <option value="all">全部角色</option>
                    <option value="teacher">teacher</option>
                    <option value="org_admin">org_admin</option>
                    <option value="guest">guest</option>
                    <option value="platform_admin">platform_admin</option>
                  </select>
                  <input
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    className="h-10 min-w-[220px] flex-1 rounded-2xl border border-rule bg-white px-4 text-body text-ink outline-none focus:border-brand"
                    placeholder="搜索用户 / 权限"
                  />
                  <button
                    type="button"
                    onClick={() => exportUsersCsv(filteredUsers)}
                    className="h-10 rounded-2xl border border-rule bg-white px-4 text-body-sm font-medium text-ink hover:bg-paper-hi"
                  >
                    导出用户表
                  </button>
                </div>
              </div>
              <div className="mt-4 max-h-[560px] overflow-auto rounded-[20px] border border-rule bg-white">
                <table className="min-w-full text-left text-body-sm">
                  <thead className="sticky top-0 bg-paper">
                    <tr className="text-ink-3">
                      <th className="px-4 py-3 font-medium">会员号</th>
                      <th className="px-4 py-3 font-medium">角色</th>
                      <th className="px-4 py-3 font-medium">权限</th>
                      <th className="px-4 py-3 font-medium">账号标识</th>
                      <th className="px-4 py-3 font-medium">会员到期</th>
                      <th className="px-4 py-3 font-medium">操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredUsers.map((row, index) => (
                      <tr key={`${row.account_id || row.openid || "row"}-${index}`} className="border-t border-rule text-ink-2">
                        <td className="px-4 py-3 font-num text-ink">{row.member_no || "--"}</td>
                        <td className="px-4 py-3">{row.role}</td>
                        <td className="px-4 py-3">{row.permissions.join(", ") || "--"}</td>
                        <td className="px-4 py-3">{row.phone || row.openid || row.account_id || "--"}</td>
                        <td className="px-4 py-3">{formatDate(row.service?.membership_until)}</td>
                        <td className="px-4 py-3">
                          <div className="flex flex-wrap gap-2">
                            <button
                              type="button"
                              onClick={() => fillFormFromRow(row)}
                              className="h-8 rounded-full border border-rule bg-white px-3 text-meta text-ink hover:bg-paper-hi"
                            >
                              填入授权
                            </button>
                            {row.member_no ? (
                              <>
                                <button
                                  type="button"
                                  onClick={() => void quickGrantMembership(row.member_no, 30)}
                                  className="h-8 rounded-full bg-brand px-3 text-meta text-white hover:brightness-105"
                                >
                                  开30天
                                </button>
                                <button
                                  type="button"
                                  onClick={() => void quickGrantMembership(row.member_no, 365)}
                                  className="h-8 rounded-full bg-success px-3 text-meta text-white hover:brightness-105"
                                >
                                  开365天
                                </button>
                              </>
                            ) : null}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
          </>
        ) : null}
      </div>
    </section>
  );
}
