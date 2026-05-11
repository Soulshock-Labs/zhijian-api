"use client";

import { Button } from "./ui/Button";

type Props = {
  open: boolean;
  onClose: () => void;
};

const tables = [
  {
    name: "accounts",
    note: "用户主档，替代 user_accounts.json",
    fields: [
      "account_id PK",
      "member_no UNIQUE",
      "phone UNIQUE",
      "openid UNIQUE",
      "password_hash",
      "role",
      "org_id",
      "agent_profile JSONB",
    ],
  },
  {
    name: "account_tokens",
    note: "多端登录 token，替代 active_tokens 数组和 token 索引",
    fields: [
      "token PK",
      "account_id FK",
      "created_at_utc",
      "last_used_at_utc",
      "revoked_at_utc",
    ],
  },
  {
    name: "documents",
    note: "文档空间索引，原文件和 Markdown 仍放对象存储",
    fields: [
      "doc_id PK",
      "account_id FK",
      "filename",
      "file_type",
      "size_bytes",
      "md_chars",
      "original_path",
      "md_path",
      "created_at",
    ],
  },
  {
    name: "generation_records",
    note: "最近生成、复制、重新生成、下载的后端历史",
    fields: [
      "record_id PK",
      "account_id FK",
      "type",
      "title",
      "theme",
      "phil",
      "day",
      "input_payload JSONB",
      "result_payload JSONB",
      "file_path",
    ],
  },
  {
    name: "member_no_counter",
    note: "会员号递增高水位，初始值取现有最大 member_no",
    fields: ["key PK", "value", "updated_at_utc"],
  },
];

export function DatabaseSchemaPanel({ open, onClose }: Props) {
  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end"
      style={{ background: "rgba(0,0,0,0.28)" }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <aside className="h-full w-full max-w-[520px] bg-paper-hi border-l border-rule shadow-2xl overflow-y-auto">
        <div className="sticky top-0 bg-paper-hi z-10 px-6 py-4 border-b border-rule-soft flex items-start justify-between gap-4">
          <div>
            <p className="eyebrow mb-2">DATABASE</p>
            <h2 className="text-h3 font-semibold text-ink">数据库设计</h2>
            <p className="text-body-sm text-ink-3 mt-1">
              第一阶段先保账号、文档空间和生成历史。
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="w-8 h-8 rounded-full text-ink-3 hover:bg-paper-sunk"
            aria-label="关闭"
          >
            x
          </button>
        </div>

        <div className="px-6 py-5 space-y-5">
          <div className="rounded-md border border-rule-soft bg-paper px-4 py-3">
            <p className="text-body-sm font-medium text-ink">关系</p>
            <div className="mt-3 grid gap-2 text-body-sm text-ink-2">
              <span>accounts 1:n account_tokens</span>
              <span>accounts 1:n documents</span>
              <span>accounts 1:n generation_records</span>
              <span>documents 1:n generation_records</span>
            </div>
          </div>

          {tables.map((table) => (
            <section key={table.name} className="rounded-md border border-rule bg-white px-4 py-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h3 className="text-body font-semibold text-ink">{table.name}</h3>
                  <p className="text-meta text-ink-3 mt-1">{table.note}</p>
                </div>
                <span className="font-mono text-[10px] text-ink-4 bg-paper-sunk rounded-pill px-2 py-1">
                  table
                </span>
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                {table.fields.map((field) => (
                  <span
                    key={field}
                    className="text-meta text-ink-2 bg-paper-hi border border-rule-soft rounded-pill px-3 py-1"
                  >
                    {field}
                  </span>
                ))}
              </div>
            </section>
          ))}

          <div className="rounded-md border border-rule-soft bg-paper px-4 py-3 text-body-sm text-ink-2">
            迁移顺序：先双写账号和 token，再迁文档索引，最后把前端最近生成接到 generation_records。
          </div>
        </div>

        <div className="sticky bottom-0 bg-paper-hi px-6 py-4 border-t border-rule-soft flex justify-end">
          <Button variant="secondary" type="button" onClick={onClose}>
            关闭
          </Button>
        </div>
      </aside>
    </div>
  );
}
