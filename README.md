# 知笺幼师助手

幼儿园教案 AI 生成系统。帮助老师一键生成周计划和日教案，输出标准 Word 文档。

## 技术栈

| 层 | 技术 |
|----|------|
| 前端 | Next.js 14 + Tailwind CSS |
| 后端 | Python FastAPI |
| 部署 | Vercel（前端）+ Google Cloud Run（后端）|
| 数据库 | Supabase PostgreSQL |
| AI | Kimi / DeepSeek / Qwen |

## 快速开始

```bash
# 1. 克隆
git clone https://github.com/Ethan7586/ZhiJian.git
cd ZhiJian

# 2. 环境变量
cp .env.example .env   # 填入真实 key

# 3. 安装依赖
pip install -r requirements.txt
npm install

# 4. 启动
uvicorn main:app --port 8080 --reload   # 后端
npm run dev                              # 前端
```

## 开发文档

- `CLAUDE.md` — 项目规范（Claude Code 自动读取）
- `TINA_ONBOARDING.md` — 新成员环境搭建
- `.env.example` — 环境变量说明

## 联系

- Ethan（架构）：Ethan7586@gsyen.com
