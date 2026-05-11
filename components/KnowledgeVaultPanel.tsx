"use client";

import { useEffect, useMemo, useState } from "react";
import { useAuth } from "@/lib/useAuth";
import {
  ApiError,
  deleteDocFromSpace,
  getDocSpaceMarkdown,
  listDocSpace,
  type DocSpaceItem,
  uploadDocToSpace,
} from "@/lib/api";

function roleTitle(role: string) {
  if (role === "org_admin") return "园本知识库";
  if (role === "platform_admin") return "纸笺知识库";
  return "我的知识库";
}

function roleHint(role: string) {
  if (role === "org_admin") return "上传园本课程、制度通知和教研资料，后续生成时会优先参考这些内容。";
  if (role === "platform_admin") return "上传平台标准模板、示范案例与品牌资料，逐步沉淀纸笺知识库。";
  return "上传你自己的教案、观察记录和备课素材，后续生成时会吸收这些资料。";
}

function fmtDate(value?: string) {
  if (!value) return "";
  return value.replace("T", " ").slice(0, 16);
}

function fmtSize(size?: number) {
  if (!size) return "0 KB";
  if (size >= 1024 * 1024) return `${(size / (1024 * 1024)).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(size / 1024))} KB`;
}

export function KnowledgeVaultPanel() {
  const { user, isLoggedIn } = useAuth();
  const [docs, setDocs] = useState<DocSpaceItem[]>([]);
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [previewId, setPreviewId] = useState("");
  const [previewText, setPreviewText] = useState("");
  const [loadingPreview, setLoadingPreview] = useState(false);

  const title = useMemo(() => roleTitle(user?.role || "teacher"), [user?.role]);
  const hint = useMemo(() => roleHint(user?.role || "teacher"), [user?.role]);

  async function refreshDocs() {
    if (!user?.token) return;
    setBusy(true);
    setError("");
    try {
      const data = await listDocSpace(user.token);
      setDocs(data.docs || []);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "读取资料失败");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    if (isLoggedIn && user?.token) {
      void refreshDocs();
    } else {
      setDocs([]);
      setPreviewId("");
      setPreviewText("");
    }
  }, [isLoggedIn, user?.token]);

  async function handleUpload(file: File) {
    if (!user?.token) {
      setError("请先登录后再上传资料");
      return;
    }
    setUploading(true);
    setError("");
    setNotice("");
    try {
      const res = await uploadDocToSpace(file, user.token);
      setNotice(res.message || `${res.filename} 上传成功`);
      await refreshDocs();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        const detail = (err.body as { detail?: string } | undefined)?.detail;
        setError(detail || err.message);
      } else {
        setError(err instanceof Error ? err.message : "上传失败");
      }
    } finally {
      setUploading(false);
    }
  }

  async function handlePreview(doc: DocSpaceItem) {
    if (!user?.token) return;
    if (previewId === doc.doc_id) {
      setPreviewId("");
      setPreviewText("");
      return;
    }
    setLoadingPreview(true);
    setError("");
    try {
      const res = await getDocSpaceMarkdown(doc.doc_id, user.token);
      setPreviewId(doc.doc_id);
      setPreviewText(res.md || "");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "读取内容失败");
    } finally {
      setLoadingPreview(false);
    }
  }

  async function handleDelete(doc: DocSpaceItem) {
    if (!user?.token) return;
    setError("");
    setNotice("");
    try {
      await deleteDocFromSpace(doc.doc_id, user.token);
      if (previewId === doc.doc_id) {
        setPreviewId("");
        setPreviewText("");
      }
      setNotice(`${doc.filename} 已删除`);
      await refreshDocs();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "删除失败");
    }
  }

  return (
    <section id="knowledge-vault" className="pb-9">
      <div className="rounded-[26px] border border-rule bg-white/90 p-6 shadow-[0_18px_60px_rgba(120,94,56,0.10)]">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="eyebrow">Knowledge</div>
            <h2 className="mt-2 font-wenkai text-[32px] leading-tight text-ink">{title}</h2>
            <p className="mt-2 max-w-[720px] text-body-sm text-ink-2">{hint}</p>
          </div>
          <label className="inline-flex h-10 cursor-pointer items-center justify-center rounded-pill bg-brand px-5 text-body-sm font-semibold text-white shadow-sm hover:brightness-105">
            {uploading ? "上传中…" : "上传资料"}
            <input
              type="file"
              accept=".docx,.pdf,.jpg,.jpeg,.png,.webp"
              className="hidden"
              disabled={!isLoggedIn || uploading}
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) void handleUpload(file);
                e.currentTarget.value = "";
              }}
            />
          </label>
        </div>

        <div className="mt-4 rounded-2xl bg-paper-sunk px-4 py-3 text-body-sm text-ink-2">
          支持上传 `.docx / .pdf / .jpg / .png / .webp`。系统会提取正文并存入你的资料空间，后续生成时逐步吸收这些内容。
        </div>

        {!isLoggedIn ? (
          <div className="mt-5 rounded-2xl border border-rule bg-paper-hi px-5 py-5 text-body-sm text-ink-2">
            登录后即可上传资料并查看你的文档空间。
          </div>
        ) : null}

        {error ? (
          <div className="mt-5 rounded-xl bg-[color-mix(in_oklch,var(--color-danger),transparent_90%)] px-4 py-3 text-body-sm text-danger-ink">
            {error}
          </div>
        ) : null}

        {notice ? (
          <div className="mt-5 rounded-xl bg-brand-tint px-4 py-3 text-body-sm text-brand">
            {notice}
          </div>
        ) : null}

        <div className="mt-6 flex items-center justify-between">
          <h3 className="text-h4 font-semibold text-ink">已上传资料</h3>
          <button
            type="button"
            onClick={() => void refreshDocs()}
            disabled={!isLoggedIn || busy}
            className="h-8 rounded-pill border border-rule bg-paper-hi px-4 text-meta text-ink hover:bg-paper-sunk disabled:opacity-50"
          >
            {busy ? "刷新中…" : "刷新列表"}
          </button>
        </div>

        <div className="mt-4 space-y-3">
          {docs.length === 0 ? (
            <div className="rounded-2xl border border-rule bg-paper-hi px-5 py-5 text-body-sm text-ink-3">
              还没有上传资料。先上传一份教案、PDF 或图片试试。
            </div>
          ) : (
            docs.map((doc) => (
              <div key={doc.doc_id} className="rounded-2xl border border-rule bg-paper-hi px-5 py-4">
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0">
                    <div className="truncate text-body font-medium text-ink">{doc.filename}</div>
                    <div className="mt-1 text-meta text-ink-3">
                      {doc.file_type || doc.ext || "资料"} · {fmtSize(doc.size_bytes)} · {doc.md_chars || 0} 字 · {fmtDate(doc.created_at)}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => void handlePreview(doc)}
                      className="h-8 rounded-pill border border-rule bg-white px-4 text-meta text-ink hover:bg-paper-sunk"
                    >
                      {previewId === doc.doc_id ? "收起内容" : loadingPreview ? "读取中…" : "查看内容"}
                    </button>
                    <button
                      type="button"
                      onClick={() => void handleDelete(doc)}
                      className="h-8 rounded-pill border border-[color-mix(in_oklch,var(--color-danger),transparent_72%)] bg-[color-mix(in_oklch,var(--color-danger),white_92%)] px-4 text-meta text-danger-ink"
                    >
                      删除
                    </button>
                  </div>
                </div>
                {previewId === doc.doc_id ? (
                  <pre className="mt-4 max-h-[320px] overflow-auto rounded-xl bg-white px-4 py-4 whitespace-pre-wrap text-body-sm leading-7 text-ink-2">
                    {previewText || "没有可预览内容"}
                  </pre>
                ) : null}
              </div>
            ))
          )}
        </div>
      </div>
    </section>
  );
}
