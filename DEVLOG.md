# PartyMate 党务工作智能助手 — 开发日志

> 项目开始时间：2026年6月

---

## 2026-06 项目启动

### 背景
基于调研发现：高校基层党务工作大量依赖人工，发展党员材料审核、三会一课内容准备、会议记录整理三个场景痛点突出，市场上没有专门的AI Agent解决方案。

### 技术选型
- **基础框架**: pydantic-ai v1.105.0（轻量级Agent框架，支持单Agent+Tool模式）
- **开发语言**: Python 3.11
- **包管理**: uv
- **LLM**: 通过 Hermes 配置的 API（支持 OpenAI/DeepSeek/Claude 等）

### Day 1 完成工作
- [x] 完成调研报告（REPORT.md）
- [x] 创建项目目录结构
- [x] 安装 pydantic-ai 和 python-docx 依赖
- [x] 配置 .env 模板
- [x] 编写党务规范知识库（party_rules.md）
- [x] 实现三个核心工具：
  - `check_doc.py` — 发展党员材料合规检查
  - `meeting_summary.py` — 会议记录整理
  - `content_gen.py` — 三会一课内容生成
- [x] 实现 Agent 核心逻辑（agent.py）— lazy init，避免无API key时崩溃
- [x] 实现 CLI 入口（main.py）— 支持独立模式和AI增强双模式
- [x] 编写示例材料（examples/）
- [x] 验证：所有工具独立运行通过（不依赖LLM）
- [x] 配置用户API环境变量

### 架构决策记录

**为什么选 pydantic-ai 而不是 CrewAI？**
- 当前是单Agent阶段，pydantic-ai更轻量
- 后续升级多Agent时可以无缝迁移到 CrewAI
- Pydantic的类型安全特性让工具定义更清晰

**为什么 Tool 函数签名都用 str → str？**
- 保持接口统一，方便后续扩展
- Agent 只需管理字符串输入输出
- 文件解析逻辑封装在 Tool 内部

---

|*开发日志将持续更新*

---

## 2026-06 优化迭代

### Day 2 完成工作

#### 问题修复
- **修复 `_detect_meeting_type` 优先级**：之前"学习"关键词先匹配"党小组会"，现在把"党课"类关键词优先级提到最高，确保"党纪学习教育"→"党课"、"学习两会精神"→"党小组会" 正确分配
- **修复 PPT 大纲占位符**：`{topic}` 原来在非 f-string 中没有被替换，导致输出文字为字面量 `{topic}`，修复后正确显示实际主题
- **修复中文引号在 Python f-string 中的语法错误**：`"X年X月X日"` 这样的中文引号与 Python 双引号字符串冲突，统一改用单引号包裹外层字符串

#### 架构升级
- **从 pydantic-ai 改为直接 HTTP 调用**：抛弃 pydantic-ai 的模型解析层，直接用 `httpx` 调用 OpenAI-compatible API。理由：
  - 兼容性更好（不再受 pydantic-ai 的模型注册和 API 格式限制）
  - 支持本地 Ollama（`qwen3.5:4b`），无需 API Key 即可使用
  - 错误处理可控（精确区分 401/404/超时等）
- **默认使用本地模型**：`qwen3.5:4b`（Ollama），零配置启动；外部 API 可通过环境变量切换

#### 工具强化
- **`check_doc.py` 重写**：从"输出检查标准清单"升级为"实际分析文本内容"，新增：
  - 日期格式自动识别和修正建议（`2024.6.15` → `2024年6月15日`）
  - 必备要素检查（称呼、落款格式、此致敬礼位置）
  - 内容质量分析（字数评估、时政热点、空洞套话检测、自我批评检查）
  - 输出摘要统计（❌错误数 / ⚠️警告数 / ✅通过数）
- **`content_gen.py` 优化**：修复 `{topic}` 占位符问题、提升关键词匹配逻辑

#### CLI 升级
- `main.py` 支持四种模式：`check-doc`、`meeting`、`content`、`interactive`（AI 对话）
- 所有模式均支持 `--ai` 参数在独立模式分析后追加 AI 增强

### 验证结果
- [x] `check-doc`: 正确识别思想汇报，发现 2 个错误 2 个警告 2 项通过
- [x] `meeting`: 结构化会议纪要，提取日期、主持人、议题
- [x] `content`: 正确判断"党纪学习教育"→"党课"，输出完整方案
- [x] AI agent 全链路：Ollama qwen3.5:4b 成功调用工具，返回自然语言分析

### 当前技术栈
- **框架**: 自定义 agent（httpx + function calling），无第三方 Agent 框架
- **本地 LLM**: Ollama qwen3.5:4b（默认）
- **备选 LLM**: 支持任意 OpenAI-compatible API（DeepSeek/Claude/GPT 等）
- **文件导出**: python-pptx 1.0.2 / python-docx 1.2.0
- **Web 服务**: Starlette + Uvicorn（端口 8567）

---

## 2026-06 新增 Web 界面

### Day 3 完成工作

#### Web 服务架构
- [x] 创建 `partymate/web/` 目录，分离前后端
- [x] 后端 `server.py` — Starlette 应用，4个 API 端点：
  - `POST /api/check-doc` — 材料合规检查
  - `POST /api/meeting` — 会议记录整理（支持导出 Word）
  - `POST /api/content` — 三会一课内容生成（支持导出 PPT）
  - `POST /api/chat` — AI 对话（需 Ollama）
  - `GET /api/status` — 服务器与 AI 状态
  - `GET /api/download` — 文件下载
- [x] 前端单页应用（纯 HTML/CSS/JS，无框架依赖）：

#### 前端设计
| 区域 | 内容 |
|------|------|
| **顶栏** | ★ PartyMate 品牌 + 运行状态指示 + 实时日期 |
| **左侧导航** | 4个工具按钮，红底高亮当前选中 |
| **材料检查** | 文本域 + 🔍 开始检查按钮 |
| **会议整理** | 文本域 + 📊 整理纪要 + 📝 导出 Word |
| **内容生成** | 输入框 + 📚 生成方案 + 📊 导出 PPT |
| **AI 对话** | 聊天界面（消息气泡 + 输入框 + 发送按钮） |

#### 视觉风格
- **配色**: 中国红(#C01B28) + 金色(#D4A02C) 党务主题
- **布局**: 左侧176px导航 + 右侧内容区，最大960px
- **响应式**: 手机端导航自动收缩为图标模式
- **信息密度**: 每个工具卡片紧凑，结果区域垂直滚动
- **无动画**: 仅 hover 过渡效果，无轮播/弹窗干扰

#### 启动方式
```bash
cd E:\Hermes\PartyMate

# 直接启动 Web UI（推荐）
uv run python -m partymate

# 或者用 bat 脚本（需要 partymate.bat 在 PATH 中）
partymate

# 传统启动方式
uv run python -m partymate.web.server
# 访问 http://localhost:8567
```

#### 命令一览
| 命令 | 作用 |
|------|------|
| `partymate` | 🚀 启动 Web 界面 (默认) |
| `partymate help` | ℹ️ 显示帮助 |
| `partymate check-doc --raw "..."` | 📋 材料检查 |
| `partymate meeting --raw "..."` | 📝 会议整理 |
| `partymate content "主题"` | 📚 内容生成 |
| `partymate interact` | 💬 AI 对话 |

### 项目结构
```
E:\Hermes\PartyMate\
├── partymate.bat          # ← 一键启动脚本
├── partymate/
│   ├── cli.py             # ← 统一 CLI 入口
│   ├── __main__.py        # ← python -m 入口
│   ├── main.py            # CLI 工具（原）
│   ├── agent.py           # AI Agent 核心
│   ├── exporters.py       # 文件导出引擎
│   ├── web/
│   │   ├── server.py      # Web 后端
│   │   └── static/        # 前端资源
│   ├── tools/             # 三个核心工具
│   └── knowledge/         # 党务规范知识库
├── output/                # 导出的 PPT/Word
├── pyproject.toml
└── DEVLOG.md
```

### 验证结果
- [x] HTML 首页正常加载，4 个 Tab 切换正常
- [x] 材料检查 API 正确返回检查清单
- [x] 会议整理 API 正确解析议题和待办事项
- [x] 内容生成 API 正确返回方案，PPT 导出成功
- [x] 服务器状态显示 AI 在线（Ollama 运行中）

---

## 2026-06-04 — v2.0 智能体升级

### 背景
用户要求 PartyMate 从一次性工具升级为具有**持久记忆、发展全流程追踪、自动材料归档、定时循环提醒**的智能体系统。参考了内部知识库中的《贵州师范大学组织发展工作专项培训工作手册》和《贵州省发展党员工作规程（试行）》两个核心规范文件。

### 新增模块

| 模块 | 文件 | 说明 |
|------|------|------|
| 数据库层 | `partymate/db/models.py` | Stage/EventStatus/MemberStatus 枚举 + 各阶段材料清单定义 |
| 数据库层 | `partymate/db/repository.py` | SQLite Repository：成员CRUD、阶段流转、事件/材料/提醒管理 |
| 数据库层 | `partymate/db/setup.py` | 初始化 + 3个示例成员样本数据 |
| 业务引擎 | `partymate/timeline_engine.py` | 自动时间线生成（按规范计算各阶段预期日期） |
| 业务引擎 | `partymate/reminder_engine.py` | 提醒规则引擎（扫描成员阶段生成 actionable 提醒） |
| 业务引擎 | `partymate/file_manager.py` | 文件归档管理器（按成员/阶段/自动创建目录结构） |
| 看板UI | `partymate/web/server.py` | 新增 10 个 Kanban API 端点 |
| 看板UI | `partymate/web/static/index.html` | 新增第5个 Tab「📊 发展看板」+ 三栏布局 |
| 看板UI | `partymate/web/static/app.js` | 看板全交互逻辑：成员列表→详情→材料→流转→提醒 |
| 看板UI | `partymate/web/static/style.css` | 看板样式：成员卡片/时间线/材料清单/倒计时 |
| 定时提醒 | `partymate/scripts/daily_brief.py` | 每日简报生成脚本 |
| 定时提醒 | Hermes Cron `partymate_daily_brief` | 每日08:00自动推送简报到微信 |

### 数据库 Schema（4张表）
- `members` — 成员信息 + 5阶段时间字段
- `timeline_events` — 29种事件类型 + 预期日期 + 状态
- `materials` — 各阶段所需材料清单 + 提交状态
- `reminders` — 待办提醒 + 到期日 + 推送状态

### 规范依据
严格遵循《贵州省发展党员工作规程（试行）》五阶段25步骤：
1. **申请入党** — 申请书→1个月内谈话→建立档案
2. **入党积极分子** — 至少3个月后推优→党委备案→1年以上培养考察→思想汇报每季度1篇→半年考察
3. **发展对象** — 积极分子满1年→听取意见→公示5工作日→政审→短期培训3天/24学时
4. **预备党员** — 预审→支部大会→党委审批3个月内→预备期1年→入党宣誓
5. **正式党员** — 预备期满前1周申请转正→支部大会→公示5工作日→党委审批3个月内→归档

### 关键时间节点（学校场景定制）
- 开学季（9月/3月）：提醒写申请书
- 申请书递交后25天：提醒安排谈话
- 满3个月：提醒推优确定积极分子
- 积极分子满11个月：提醒准备列为发展对象
- 每季度末：提醒收集思想汇报
- 每学期末（6月/12月）：半年考察提醒
- 预备期满前14天：提醒写转正申请
- 预审合格后20天：提醒召开支部大会

### 验证结果
- [x] 数据库初始化 + 3个示例成员（申请/积极分子/预备党员各一）
- [x] 阶段流转 API（applicant→activist 自动生成事件+材料）
- [x] 材料提交 API（标记已交 + 记录日期）
- [x] Dashboard 汇总 API（成员分布/逾期事件/待交材料）
- [x] 提醒引擎生成每日简报（中文输出, 待办+倒计时+学校节点）
- [x] Cron 定时任务已配置（每天08:00推送）
- [x] Web 服务器运行正常（localhost:8567）

### 启动方式
```bash
# 启动 Web UI（默认）
partymate
# 或
uv run python -m partymate

# 初始化/重设数据库
rm -f data/partymate.db && uv run python -m partymate.db.setup

# 手动生成每日简报
uv run python partymate/scripts/daily_brief.py