# ★ PartyMate — 本地党务智能 Agent 工作台

> 面向高校党支部党务负责人的 **本地优先、单用户、多工具智能 Agent 工作台**。
>
> 覆盖 **发展党员材料管理 → AI 核查 → 会议闭环 → 成员台账 → Agent 可追溯执行** 全流程。

---

## 为什么做这个项目？

> 笔者本人担任过研究生党支部党务负责人，亲身经历过：

- **发展党员材料**（入党申请书、思想汇报、转正申请等）格式要求严格，全靠人工逐份检查，多个成员材料混在一起时极易遗漏
- **会议记录**（支委会、党员大会、党小组会、党课）需要整理为规范格式，待办事项常常被遗忘
- **成员进度跟踪**：谁到了哪个阶段、缺哪些材料，全靠纸质台账和记忆，没有统一视图
- **党务规范复杂**：阶段顺序、材料清单、时间线要求繁琐，新负责人上手成本高

市面上没有专门针对高校基层党务场景的 AI Agent 产品，因此做了这个项目。它不是简单的「聊天机器人」，而是一个**有状态的、可追溯的、人机协同的 Agent 工作台**。

---

## 项目亮点

| 特性 | 说明 | 面试价值 |
|------|------|----------|
| 🧠 **Agent 执行追踪（Trace）** | 每次 AI 对话自动记录：用户输入、模型选择、工具调用链、耗时、结果摘要 | **Agent 可观测性设计** |
| 🔄 **会议闭环工作流** | 从「整理纪要到自动提取待办事项并写入提醒系统」，形成任务闭环 | **工作流编排能力** |
| 📦 **ZIP 材料包导入 + 一致性核查** | 上传成员材料包，自动解压、识别材料类型、整套一致性检查（缺件/重复/阶段冲突/身份冲突） | **多步骤 Agent 任务编排** |
| 🧠 **成员级独立记忆** | 每个成员独立的记忆命名空间，Agent 只加载当前成员的事实与历史结论 | **Agent 长期记忆设计** |
| 🔍 **OCR 人工复核闭环** | 低置信度 OCR 片段标记 → 人工修正 → 确认入库，形成人机协同流程 | **人机协同设计模式** |
| 🎯 **痛点导向** | 基于真实党务工作体验，非「造轮子」项目 | **产品设计思维** |
| 🧩 **双模式（独立 + AI）** | 不依赖 LLM 也能完成基础检查，Ollama 可选 | **容错设计** |
| 🌐 **Web 界面 + CLI** | 红金党务主题 SPA 看板，同时支持命令行调用 | **全栈交付能力** |
| 🗃️ **SQLite 结构化存储** | 成员、材料、事件、提醒、记忆、OCR 任务均持久化 | **数据建模能力** |

---

## 快速开始

### 环境要求

- Python ≥ 3.11
- [uv](https://docs.astral.sh/uv/)（推荐包管理器）
- [Ollama](https://ollama.ai/)（可选，用于 AI 对话模式）

### 安装与启动

```bash
cd E:\Hermes\PartyMate
uv sync
uv run python -m partymate
```

浏览器访问 **http://localhost:8567**

### 命令一览

```bash
# 🚀 启动 Web 界面
partymate

# 💬 AI 对话（交互式）
partymate interact

# 📋 材料合规检查
partymate check-doc --raw "思想汇报正文..."

# 📝 会议记录整理
partymate meeting --raw "会议原始记录..."

# 📚 三会一课内容生成
partymate content "党纪学习教育"
```

---

## 核心功能架构

### 1. 📋 发展党员材料合规检查

自动识别材料类型（入党申请书/思想汇报/转正申请/入党志愿书/考察意见），检查：

| 检查项 | 说明 |
|--------|------|
| ✅ 日期格式 | 规范日期写法 |
| ✅ 必备要素 | 称呼、结尾、落款 |
| ✅ 内容质量 | 字数、时政结合、自我批评 |
| ✅ 格式规范 | 标题、段落 |
| ✅ 规程引用 | RAG 检索相关知识库片段 |

### 2. 📦 材料包导入与整套一致性核查

**核心亮点：** 将「单文档检查」升级为「成员维度全套核查」，体现 Agent 多步骤任务编排能力。

- 上传 ZIP 材料包 → 自动解压 → 文件类型识别 → 文本/OCR 提取
- 整套一致性核查：
  - ❌ **缺件**：当前阶段及之前所有阶段的必备材料
  - ❌ **重复**：同名材料被多次归档
  - ⚠️ **阶段冲突**：出现超出当前阶段的材料
  - ⚠️ **身份冲突**：材料中姓名/专业与成员档案不一致
  - 🔍 **待复核**：OCR 低置信度、未知类型文件

### 3. 🔄 会议闭环工作流

**核心亮点：** 形成「会前准备 → 会中记录 → 会后待办」的任务闭环，体现工作流编排能力。

```
原始记录 → 结构化纪要（议题/决议/待办）
                              ↓
                    解析待办事项 → 自动写入提醒系统
                              ↓
                    待办跟踪：待确认 → 进行中 → 已完成
```

### 4. 🧠 成员级独立记忆

**核心亮点：** 每个成员独立的记忆命名空间，Agent 只加载当前成员的事实与历史结论，避免跨成员上下文串扰。

- 支持类型：结论摘要 / 风险提醒 / 工作指令 / 修订结论 / 一般记录
- 支持置顶、合并、删除
- Agent 对话时可绑定某成员，自动注入记忆作为上下文

### 5. 🔍 OCR 人工复核闭环

**核心亮点：** 人机协同设计，体现「机器初稿 + 人工确认 + 正式入库」的工程思维。

```
扫描件/图片 → OCR 提取
               ↓
        低置信度片段标记
               ↓
        人工修正确认 → 正式文本入库
```

### 6. 🗺️ 发展看板与提醒

- 按发展阶段的成员分组（申请人/积极分子/发展对象/预备党员/正式党员）
- 材料进度条、时间线、待提交/已提交标记
- 待办提醒：材料缺件、阶段超期

### 7. 🔄 Agent 执行记录（Trace）Tab

**核心亮点：** 每次 AI 对话自动记录可追溯的执行轨迹，体现 Agent 可观测性设计。

- 用户输入原文
- 模型选择与版本
- 工具调用链（工具名 → 参数 → 结果摘要 → 耗时）
- 总执行耗时
- 执行状态（成功/错误）

---

## 技术栈

| 层级 | 技术 | 用途 |
|------|------|------|
| **语言** | Python 3.11 | — |
| **包管理** | uv | 依赖与虚拟环境 |
| **Agent 框架** | 手写 runtime（httpx + function calling） | AI 工具调用与执行追踪 |
| **LLM** | Ollama（本地）/ 任意 OpenAI-compatible API | AI 增强模式 |
| **数据库** | SQLite（5 个主表 + 3 个扩展表） | 结构化持久化 |
| **文件解析** | PyMuPDF / python-docx / easyocr | PDF/Word/图片解析 |
| **导出** | python-pptx / python-docx | PPT / Word 导出 |
| **Web 服务** | Starlette + Uvicorn | REST API |
| **前端** | 原生 HTML/CSS/JS（红金党务主题 SPA） | 工作台 UI |

### Agent 核心设计

```python
# 每个 Agent run 自动记录
AgentRun {
    run_id: str,           # 唯一标识
    user_input: str,       # 用户原问
    model_used: str,       # 使用的模型
    tool_calls: [          # 工具调用链
        {tool_name, arguments, result_summary, duration_ms, call_order}
    ],
    duration_ms: int,      # 总耗时
    status: str,           # completed / error
    result_summary: str    # 输出摘要
}
```

---

## Web 界面

![](_) <!-- 建议后续补一张截图 -->

| 功能模块 | 说明 |
|----------|------|
| 🏠 **首页仪表盘** | 统计卡片 + 快速入口 + 最近文件 |
| 📋 **材料检查** | 双栏布局：原文预览 ↔ 检查结果，支持文件拖拽/RAG 引用 |
| 📝 **会议整理** | 上传/粘贴 → 结构化纪要 → Word 导出 → **解析待办并写入提醒** |
| 📚 **内容生成** | 主题 → 学习材料/PPT 大纲/讨论题 → PPT 导出 + 规程引用 |
| 💬 **AI 对话** | 支持成员上下文绑定 + 文件上传分析 + 自动执行追踪 |
| 📊 **发展看板** | 看板三栏：成员列表 ↔ 详情（材料/时间线/OCR/记忆） ↔ 提醒 |
| 🔄 **执行记录** | Agent 调用历史 + 工具调用链详情 |

---

## 项目结构

```
E:\Hermes\PartyMate\
├── pyproject.toml              # 项目配置
├── README.md                   # 本文件
├── DEVPLAN.md                  # 开发计划与架构说明（简历参考）
├── DEVLOG.md                   # 详细开发日志
│
├── partymate/                  # 主包
│   ├── __main__.py             # 启动入口
│   ├── agent.py                # Agent runtime（支持执行追踪）
│   ├── cli.py / main.py        # CLI 入口
│   ├── exporters.py            # PPT/Word 导出
│   ├── file_manager.py         # 文件管理
│   ├── timeline_engine.py      # 阶段时间线
│   ├── reminder_engine.py      # 提醒引擎
│   │
│   ├── db/                     # 数据层
│   │   ├── models.py           # 枚举与阶段材料定义
│   │   └── repository.py       # SQLite 仓储层（~1000 行）
│   │
│   ├── services/               # 业务服务层
│   │   ├── agent_trace_service.py      # Agent 执行追踪
│   │   ├── material_check_service.py   # 材料整套一致性核查
│   │   ├── material_import_service.py  # ZIP 材料包导入
│   │   ├── meeting_workflow_service.py # 会议闭环工作流
│   │   ├── member_memory_service.py    # 成员级独立记忆
│   │   ├── member_view_service.py      # 看板视图组装
│   │   └── ocr_review_service.py       # OCR 人工复核闭环
│   │
│   ├── tools/                  # 核心工具层
│   │   ├── doc_check.py        # 材料合规检查
│   │   ├── meeting_summary.py  # 会议记录整理
│   │   ├── content_gen.py      # 三会一课内容生成
│   │   ├── file_parser.py      # 文件解析（PDF/Word/OCR）
│   │   └── rag.py              # 规则知识库检索
│   │
│   ├── knowledge/
│   │   └── party_rules.md      # 党务规则知识库
│   │
│   ├── scripts/                # 运维脚本
│   │   ├── import_members.py   # CSV 批量导入成员
│   │   └── daily_brief.py      # 每日简报脚本
│   │
│   └── web/                    # Web 服务层
│       ├── server.py           # Starlette API（~600 行）
│       └── static/
│           ├── index.html      # SPA 页面
│           ├── style.css       # 红金党务主题
│           └── app.js          # 客户端逻辑
│
├── tests/                      # 单元测试（31 个测试用例）
├── data/                       # SQLite 数据库
└── output/                     # 导出成果物
```

---

## API 文档

| 端点 | 说明 |
|------|------|
| `POST /api/check-doc` | 材料合规检查 |
| `POST /api/meeting` | 会议纪要整理 |
| `POST /api/meeting/parse-actions` | 会议待办解析并写入提醒 ⭐ |
| `GET /api/meeting/actions` | 待办列表 |
| `POST /api/meeting/actions/{id}/confirm` | 确认待办 |
| `POST /api/meeting/actions/{id}/complete` | 完成待办 |
| `POST /api/chat` | AI 对话（支持成员上下文） |
| `POST /api/materials/archive/import` | ZIP 材料包导入 ⭐ |
| `POST /api/members/{id}/materials/check` | 整套一致性核查 ⭐ |
| `GET /api/ocr/tasks/{id}` | OCR 复核任务详情 |
| `POST /api/ocr/confirm` | 确认 OCR 文本 |
| `GET /api/agent/runs` | Agent 执行记录列表 ⭐ |
| `GET /api/agent/runs/{id}` | 执行详情（含工具调用链） ⭐ |
| `GET/POST/PATCH/DELETE /api/members/*` | 成员 CRUD |
| `GET/POST/DELETE /api/members/{id}/memories/*` | 成员记忆管理 ⭐ |

---

## 设计原则

1. **本地优先**：核心能力在本机运行，不依赖外部服务
2. **单用户、单支部**：不做复杂权限系统，聚焦业务价值
3. **事实与记忆分离**：结构化事实进 SQLite，Agent 上下文临时组装
4. **白名单工具**：模型只能调用预定义工具，不能执行任意 shell
5. **人机协同**：OCR 低置信度片段、复杂核查结果支持人工确认
6. **任务闭环**：工具输出不能只停留在文本，要回写到台账、提醒和成果物
7. **Agent 可追溯**：每次执行自动记录，支持审计回顾

---

## 关于作者

研二计算机硕士，3DGS 三维重建方向（小论文已投稿）。

担任过研究生党支部党务负责人，有第一手党务工作经验。正在学习 Agent 开发技术，目标进入 AI Agent 赛道实习。

**适合的实习方向**：AI Agent 开发 / LLM 工程 / 智能应用开发

---

> **声明**：本项目的党务规范知识库基于公开资料整理，实际工作中请以学校党委下发的最新文件为准。作者不对因使用本项目产生的任何法律后果负责。
