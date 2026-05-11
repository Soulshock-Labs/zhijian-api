"use client";

/**
 * useAuth — 轻量登录态管理（localStorage + 内存 state）
 *
 * 存储结构（localStorage）：
 *   zj_user_token   string   登录 token
 *   zj_account_id   string   账号主键（uid_xxx）
 *   zj_member_no    string   会员号（如 10000）
 *   zj_user_role    string   角色：teacher / org_admin / platform_admin
 *   zj_org_id       string   所属园所 ID（暂时为 ""）
 *
 * 对外暴露：
 *   user        { token, account_id, member_no, user_id, role, org_id } | null
 *   login()     写入并广播
 *   logout()    清除并广播
 *   isLoggedIn  boolean
 */

import { useEffect, useState, useCallback } from "react";

const KEYS = {
  token:      "zj_user_token",
  account_id: "zj_account_id",
  member_no:  "zj_member_no",
  role:       "zj_user_role",
  org_id:     "zj_org_id",
} as const;

export type AuthUser = {
  token:      string;
  account_id: string;
  member_no:  string;
  user_id:    string;
  role:       string;
  org_id:     string;
};

function readFromStorage(): AuthUser | null {
  if (typeof window === "undefined") return null;
  try {
    const token = localStorage.getItem(KEYS.token) || "";
    const account_id =
      localStorage.getItem(KEYS.account_id) ||
      localStorage.getItem("zj_user_id") ||
      localStorage.getItem("user_id") ||
      "";
    if (!token || !account_id) return null;
    return {
      token,
      account_id,
      member_no: localStorage.getItem(KEYS.member_no) || "",
      user_id: account_id,
      role: localStorage.getItem(KEYS.role) || "teacher",
      org_id: localStorage.getItem(KEYS.org_id) || "",
    };
  } catch {
    return null;
  }
}

function writeToStorage(user: AuthUser) {
  try {
    localStorage.setItem(KEYS.token, user.token);
    localStorage.setItem(KEYS.account_id, user.account_id);
    localStorage.setItem(KEYS.member_no, user.member_no);
    localStorage.setItem(KEYS.role, user.role);
    localStorage.setItem(KEYS.org_id, user.org_id);
    // 兼容旧逻辑：旧 user_id 继续写 account_id，避免文档空间等接口串不起来
    localStorage.setItem("zj_user_id", user.account_id);
    localStorage.setItem("user_id", user.account_id);
    localStorage.setItem("STA_REDEEM_USER_ID", user.account_id);
  } catch {
    // ignore
  }
}

function clearStorage() {
  try {
    Object.values(KEYS).forEach((k) => localStorage.removeItem(k));
    localStorage.removeItem("zj_user_id");
    localStorage.removeItem("user_id");
    localStorage.removeItem("STA_REDEEM_USER_ID");
  } catch {
    // ignore
  }
}

// ── 简单的跨组件广播（同 tab 内用自定义事件） ──
const AUTH_EVENT = "zj_auth_change";

export function useAuth() {
  const [user, setUser] = useState<AuthUser | null>(null);

  // 首次挂载时从 storage 读取
  useEffect(() => {
    setUser(readFromStorage());

    function onAuthChange() {
      setUser(readFromStorage());
    }

    window.addEventListener(AUTH_EVENT, onAuthChange);
    return () => window.removeEventListener(AUTH_EVENT, onAuthChange);
  }, []);

  const login = useCallback((userData: AuthUser) => {
    writeToStorage(userData);
    setUser(userData);
    window.dispatchEvent(new Event(AUTH_EVENT));
  }, []);

  const logout = useCallback(() => {
    clearStorage();
    setUser(null);
    window.dispatchEvent(new Event(AUTH_EVENT));
  }, []);

  return {
    user,
    isLoggedIn: Boolean(user),
    login,
    logout,
  };
}
