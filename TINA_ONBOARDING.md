# 知笺项目 — Tina 开发环境搭建

## 仓库结构（单仓库，前后端合并）

```
ZhiJian/
├── app/                  ← Next.js 前端页面
├── components/           ← React 组件
├── routers/              ← Python FastAPI 路由
├── services/             ← Python 业务逻辑
├── core/                 ← Python 核心（DB、认证）
├── repositories/         ← Python 数据层
├── templates/belesi/     ← 贝乐思 Word 模板（6个）
├── package.json          ← 前端依赖
└── requirements.txt      ← Python 依赖
```

---

## 第一步：安装依赖

```bash
# Python 后端
pip install -r requirements.txt

# 前端
npm install
```

---

## 第二步：环境变量

找 Ethan 要 `.env` 文件，参考 `.env.example`：

```bash
cp .env.example .env
# 填入 Ethan 给你的 key 值
```

---

## 第三步：本地启动

```bash
# 后端（新终端）
uvicorn main:app --host 0.0.0.0 --port 8080 --reload

# 前端（新终端）
npm run dev
```

访问 http://localhost:3000

---

## ⚠️ 最重要的事

**禁止重启或重新部署 Cloud Run！**
102 个真实付费用户数据在服务器上，重启即全部丢失。
任何部署操作前必须先联系 Ethan。

---

## Claude Code 设置（一次性）

创建 `~/.claude/CLAUDE.md`：

```markdown
# Tina 开发规范
角色：开发执行，架构决策必须先问 Ethan。

## 准则
1. 先想后写，不确定就问
2. 最少代码解决问题
3. 只改任务范围内的代码
4. 禁止擅改 UI 尺寸（看项目 CLAUDE.md）
```

项目根目录的 `CLAUDE.md` 有完整规范，Claude Code 启动时自动读取。

---

有问题找 Ethan。
