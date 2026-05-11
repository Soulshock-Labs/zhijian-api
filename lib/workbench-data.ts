export type Tone = "brand" | "info" | "neutral" | "success" | "warn" | "danger";

export const workbenchData = {
  greeting: { weekday: "星期三", time: "上午 9:04", weekNo: "第 16 周" },
  hero: {
    title: "今天，从一份更轻松的周计划开始",
    body: "先把本周五天安排定下来，再逐日延展成可导出的日教案。",
    ctaPrimary: "开始本周周计划",
    ctaSecondary: "查看最近生成",
  },
  tasks: [
    { id: "weekly", tag: "主任务", tone: "brand" as Tone,
      title: "本周周计划", body: "春天来了 · 中班", meta: "周三已补完" },
    { id: "daily", tag: "推荐", tone: "info" as Tone,
      title: "我的日教案", body: "从周计划延续生成", meta: "约 2 分钟" },
    { id: "observation", tag: "空", tone: "neutral" as Tone,
      title: "今日观察", body: "拍一张或说一句都行", meta: "随手记录" },
  ],
  quick: [
    { id: "recent", label: "查看最近生成" },
    { id: "knowledge", label: "上传园所资料" },
    { id: "theme", label: "整理本周主题" },
  ],
  recent: [
    { type: "lesson", typeLabel: "日教案", title: "周二·户外游戏活动",  cls: "中班", at: "2 天前" },
    { type: "weekly", typeLabel: "周计划", title: "第 15 周 · 植物朋友", cls: "中班", at: "5 天前" },
    { type: "obs",    typeLabel: "观察",   title: "小远搭积木的专注时刻", cls: "中班", at: "6 天前" },
  ],
  status: {
    kb:     "已同步 · 114 份文件",
    member: "剩余 128 次 · 5月23日到期",
    streak: "已连续使用 7 天",
  },
};

export type WorkbenchData = typeof workbenchData;
