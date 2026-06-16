# PartyMate 仓库梳理与 v2 开发文档

## 1. 文档定位

本文档分两部分：

1. `当前仓库信息整理`：说明这个仓库现在已经实现了什么，真实技术栈是什么，哪些地方和 README 已经不完全一致。
2. `v2 开发文档`：结合项目定位，给出后续可继续实现的本地党务智能 Agent 工作台方案。

这份文档面向两个目标：

- 作为后续开发的基线说明
- 作为简历项目包装时的架构与功能说明底稿

---

## 2. 项目定位

PartyMate 当前定位更适合表述为：

> `单党支部、单党务负责人、本地优先` 的党务智能 Agent 工作台雏形。

它不是多用户企业平台，也不是 Spring Boot 平台化项目。  
当前仓库本质上是一个 `Python 本地单体应用`，通过 Web UI 和 CLI 提供党务场景工具能力，并可接入本地 Ollama 大模型完成简单的 Agent tool-calling。

---

## 3. 当前仓库真实技术栈

## 3.1 后端

| 层级 | 当前技术 | 说明 |
|------|----------|------|
| 运行语言 | Python 3.11 | `pyproject.toml` 要求 `>=3.11` |
| Web 框架 | Starlette + Uvicorn | 当前实际不是 FastAPI |
| Agent 调用 | `httpx` + 手写 OpenAI-compatible tool calling | 主要在 `partymate/agent.py` |
| 数据存储 | SQLite | `partymate/db/repository.py` |
| 文档解析 | PyMuPDF / python-docx | PDF、Word 解析 |
| OCR | easyocr | 图片文字识别 |
| 导出 | python-pptx / python-docx | 导出 PPT 与会议纪要 Word |

## 3.2 前端

| 层级 | 当前技术 | 说明 |
|------|----------|------|
| 前端形式 | 原生 HTML/CSS/JS | 不是 Vue |
| 交互方式 | 单页应用 SPA | 静态资源位于 `partymate/web/static/` |
| 状态存储 | 浏览器本地存储 + 后端接口 | 前端有最近文件、统计信息等本地状态 |

## 3.3 模型与知识库

| 模块 | 当前实现 | 说明 |
|------|----------|------|
| 本地模型 | Ollama | 默认走 `http://127.0.0.1:11434/v1` |
| API 兼容层 | OpenAI-compatible | 支持替换外部兼容接口 |
| RAG | 规则文本分块 + 关键词匹配 | 当前不是向量库方案 |
| 知识库来源 | `partymate/knowledge/party_rules.md` | 单文件规则库 |

## 3.4 需要特别说明

- `pyproject.toml` 中有 `pydantic-ai` 依赖，但当前核心 Agent 并没有真正建立在 LangChain / LangGraph / pydantic-ai runtime 上。
- 当前项目不是前后端完全分离部署架构，而是 `Python 服务 + 静态前端资源` 的本地单体模式。
- 这和你后面确定的方向是一致的：`本地优先、单用户、单支部使用`。

---

## 4. 当前仓库结构梳理

下面是当前仓库中最重要的模块分布。

```text
partymate/
├── __main__.py                  # python -m partymate 入口
├── cli.py                       # 统一命令入口
├── main.py                      # CLI 子命令实现
├── agent.py                     # 手写 Agent runtime
├── exporters.py                 # PPT / Word / 报告导出
├── db/
│   ├── models.py                # 阶段、材料、枚举定义
│   └── repository.py            # SQLite 仓储层
├── knowledge/
│   └── party_rules.md           # 规则知识库
├── scripts/
│   └── import_members.py        # 成员 CSV 导入
├── tools/
│   ├── content_gen.py           # 三会一课内容生成
│   ├── doc_check.py             # 材料合规检查
│   ├── file_parser.py           # PDF/Word/图片解析
│   ├── meeting_summary.py       # 会议记录整理
│   └── rag.py                   # 规则检索
└── web/
    ├── server.py                # Web API 与静态资源挂载
    └── static/
        ├── index.html
        ├── app.js
        └── style.css
```

仓库根目录还包含：

- `README.md`：项目说明，但内容相对早于当前实现
- `REPORT.md`：党务场景调研材料
- `DEVLOG.md`：开发记录
- `output/`：导出结果目录
- `data/`：SQLite 数据目录

---

## 5. 当前已实现能力

## 5.1 材料合规检查

代码入口：

- `partymate/tools/doc_check.py`
- `POST /api/check-doc`
- `partymate check-doc`

当前能力：

- 自动识别材料类型
  - 入党申请书
  - 思想汇报
  - 转正申请
  - 入党志愿书
  - 考察意见
- 日期格式检查
- 称呼、结尾等基本格式检查
- 字数估算
- 是否包含时政热点、自我批评内容的启发式检查
- 可通过 Web 或 CLI 调用

当前限制：

- 仍然是单文档检查为主
- 还没有形成“整套材料包一致性核查”
- 规则判断主要是字符串规则和启发式判断，尚不够严格

## 5.2 文件上传与 OCR

代码入口：

- `partymate/tools/file_parser.py`
- `POST /api/upload`

当前能力：

- 支持上传并解析：
  - `.pdf`
  - `.docx/.doc`
  - `.png/.jpg/.jpeg/.bmp/.tiff`
- PDF 文本提取
- Word 文本提取
- 图片 OCR 提取
- 返回全文、页数、预览片段

当前限制：

- OCR 只做一次提取，没有“低置信度标记 + 人工复核”闭环
- 还不支持 zip 材料包导入
- 还没有专门的手写件识别增强策略

## 5.3 会议记录整理

代码入口：

- `partymate/tools/meeting_summary.py`
- `POST /api/meeting`
- `partymate meeting`

当前能力：

- 从原始会议记录中提取：
  - 日期
  - 主持人
  - 记录人
  - 会议类型
  - 议题
  - 待办事项
  - 决议摘要占位
- 可导出会议纪要 Word 文档

当前限制：

- 议题和待办抽取以规则匹配为主
- 决议内容还不够强，很多情况仍需要人工补充
- 还没有“会前方案 -> 会中记录 -> 会后待办”的完整闭环

## 5.4 三会一课内容生成

代码入口：

- `partymate/tools/content_gen.py`
- `POST /api/content`
- `partymate content`

当前能力：

- 根据主题推荐会议类型
- 生成学习材料建议
- 生成 PPT 大纲
- 生成讨论题
- 支持导出 PPT

当前限制：

- 当前更偏模板化生成
- 没有结合具体支部、具体会议上下文
- 没有和提醒、台账、纪要联动

## 5.5 RAG 规则检索

代码入口：

- `partymate/tools/rag.py`
- `partymate/knowledge/party_rules.md`

当前能力：

- 将知识库按 Markdown 标题分块
- 基于关键词检索相关党务规则片段
- 在材料检查和内容生成结果中附带依据引用

当前限制：

- 当前是 `关键词 + 子串兜底`，不是向量检索
- 只有单一知识库文件
- 没有文档导入、重建索引、知识库管理界面

## 5.6 AI 对话与工具调用

代码入口：

- `partymate/agent.py`
- `POST /api/chat`
- `partymate interactive`

当前能力：

- 接受自然语言问题
- 模型可调用 3 个工具：
  - `check_doc`
  - `meeting_summary`
  - `content_gen`
- 通过 OpenAI-compatible `chat/completions` 协议与 Ollama 交互
- 支持本地 Ollama，也支持外部兼容 API

当前限制：

- 仍是轻量级 tool calling
- 没有显式工作流状态机
- 没有成员级上下文装载
- 没有长期记忆
- 没有结构化 Agent run trace

## 5.7 发展看板 / 台账 / 提醒

这部分是当前 README 没有完整体现、但代码中已经存在的能力。

代码入口：

- `partymate/db/repository.py`
- `partymate/db/models.py`
- `partymate/web/server.py`
- `partymate/web/static/app.js`

当前能力：

- 成员信息管理
- 发展阶段推进
- 阶段事件时间线
- 材料清单自动生成
- 提醒列表
- Dashboard 汇总
- CSV 导入成员
- 前端发展看板页面

当前数据库实体：

- `members`
- `timeline_events`
- `materials`
- `reminders`

当前限制：

- 这部分已经进入 v2 雏形，但还没有和 Agent 深度打通
- 还没有成员记忆
- 还没有会议待办自动写入提醒
- 还没有材料核查结果自动回写成员事实表

---

## 6. 当前仓库状态判断

从工程角度看，当前仓库不是“只有三个脚本”的最初原型了，而是已经开始向一个 `本地党务工作台` 演进。

可以把当前状态概括为：

| 模块 | 状态 |
|------|------|
| 文本材料检查 | 已实现 |
| 会议整理 | 已实现 |
| 内容生成 | 已实现 |
| Web UI | 已实现 |
| 文件上传 / OCR | 已实现 |
| RAG 引用 | 已实现基础版 |
| SQLite 成员看板 | 已实现基础版 |
| 成员记忆 | 未实现 |
| 材料包 zip 导入 | 未实现 |
| 材料整套一致性核查 | 未实现 |
| OCR 人工复核闭环 | 未实现 |
| 会议闭环工作流 | 未实现 |
| Agent 审计 / 任务追踪 | 未实现 |

## 6.1 README 与代码的差异

当前 README 更偏早期版本，主要强调“三个工具 + Web UI”。  
但从代码看，仓库已经额外包含：

- 文件上传与 OCR
- RAG 检索
- SQLite 仓储层
- 发展看板
- 提醒系统
- 成员导入

因此后续如果继续做简历项目，README 也应同步升级。

---

## 7. 当前仓库的主要不足

如果目标是把项目包装成一个更有竞争力的 `Agent 开发工程实习` 项目，当前最大问题不是“有没有聊天框”，而是下面几项还不够完整：

1. `缺少成员级上下文与记忆`
   - 现在 Agent 无法围绕“某个发展党员对象”持续工作

2. `缺少完整任务闭环`
   - 现在工具输出结果主要还是文本
   - 还没有稳定回写到台账、提醒、报告

3. `缺少复杂材料处理能力`
   - 没有 zip 材料包导入
   - 没有整套材料一致性核查

4. `OCR 流程不完整`
   - 没有低置信度标记与人工修订

5. `Agent 还偏“函数调用演示”，不是“有状态工作流执行器”`
   - 没有任务状态
   - 没有审计记录
   - 没有多步流程节点

---

## 8. v2 目标定位

## 8.1 产品目标

PartyMate v2 建议定位为：

> `本地党务智能 Agent 工作台`

服务对象：

- 单个党支部
- 单个党务负责人
- 本地电脑部署
- 本地 Ollama 驱动

核心价值不是“陪聊”，而是 `有状态的党务任务执行`。

## 8.2 设计原则

- `本地优先`：核心能力在本机运行
- `单用户`：不做复杂权限体系
- `事实与记忆分离`：结构化事实进数据库，Agent 记忆单独存
- `工具白名单`：模型不能直接拿到任意 shell
- `人机协同`：OCR 和复杂核查支持人工复核
- `任务闭环`：结果要落到台账、提醒和导出成果物

---

## 9. v2 推荐架构

## 9.1 推荐实现路线

结合当前仓库和你的目标，推荐路线不是推倒重来，而是：

1. `保留 Python 本地单体架构`
2. `保留手写 Agent runtime`
3. `后续只在复杂流程接入 LangGraph`
4. `不把 LangChain 作为基础依赖`
5. `不引入 Spring Boot`

## 9.2 Web 技术路线建议

这里分两种路线：

### 路线 A：最小延续方案

- 后端继续使用 `Starlette`
- 前端继续使用原生 `HTML/CSS/JS`

适合：

- 你想快速把 Agent 能力做完整
- 优先完成可展示的产品闭环

### 路线 B：简历强化方案

- 后端整理为 `FastAPI`
- 前端逐步升级为 `Vue 3 + TypeScript`

适合：

- 你想在简历里明确写出更主流的工程技术栈
- 你愿意接受一部分工程重构成本

### 当前建议

如果近期目标是做出能写进简历的 Agent 项目，建议：

- `先完成功能闭环`
- `再做前端与 API 层升级`

原因很直接：  
没有完整任务流的 Vue/FastAPI 壳子，含金量不如一个真正能处理材料包、OCR、会议闭环、成员记忆的本地 Agent 工作台。

---

## 10. v2 核心功能设计

## 10.1 发展党员材料工作台

### 要实现的功能

- 上传单文件
- 上传 zip 材料包
- 自动解压并建立文件索引
- 自动识别材料类型
- 文本提取与 OCR
- 单文档规范检查
- 整套材料一致性核查
- 输出整改清单和核查报告

### 使用说明

1. 选择成员或新建成员
2. 上传单份材料或 zip 包
3. 系统完成解析、分类、核查
4. 对低质量 OCR 项进入人工校对
5. 确认后生成正式报告

### 实现效果

- 清楚知道缺哪些材料
- 哪些材料格式不规范
- 哪些日期冲突
- 哪些字段需人工确认

## 10.2 材料包一致性核查

### 要实现的功能

- 姓名、年级、专业、学号一致性检查
- 阶段顺序合理性检查
- 思想汇报数量检查
- 半年考察记录缺失检查
- 关键日期冲突检查
- 必备材料缺失检查
- 重复归档或误归档检查

### 使用说明

1. 上传某成员完整材料包
2. 点击“整套核查”
3. 查看严重错误、一般警告、待确认项
4. 导出整改清单

### 实现效果

将“单文档检查”升级为“成员维度全套核查”，这是简历里的核心亮点之一。

## 10.3 会议工作台

### 要实现的功能

- 根据主题生成会议方案
- 推荐会议类型
- 生成议程、主持词、学习材料、讨论题
- 上传会议记录或图片
- 解析纪要、决议、待办
- 待办写入提醒系统
- 导出纪要 / PPT

### 使用说明

1. 输入主题，生成会前方案
2. 会议结束后上传记录
3. 系统整理纪要并抽取待办
4. 用户确认后写入提醒
5. 导出纪要与课件

### 实现效果

形成“会前准备 -> 会中记录 -> 会后待办”的闭环。

## 10.4 制度知识与问答工作台

### 要实现的功能

- 导入本地党务规章和学校模板
- 分块索引
- 关键词 + 向量召回预留
- 带引用的问答
- 支持成员上下文问答

### 使用说明

1. 导入知识库文档
2. 直接提问，或在成员页面发起上下文提问
3. 查看回答与引用依据
4. 一键插入方案或整改建议

### 实现效果

让输出不只是生成文本，而是带依据、可追溯。

## 10.5 台账与提醒工作台

### 要实现的功能

- 成员总览
- 阶段时间线
- 材料清单
- 缺件提醒
- 会议待办提醒
- 周视图 / 月视图
- 成员阶段报告导出

### 使用说明

1. 在总览页查看高风险成员和待办
2. 进入成员详情查看时间线和材料状态
3. 手动推进阶段或补录事件
4. 导出阶段进展报告

### 实现效果

把零散党务工作收束成一个个人工作控制台。

## 10.6 成员级独立记忆

### 要实现的功能

- 每个成员独立记忆命名空间
- 只保存高价值长期信息
- 支持摘要、风险、修订结论、用户偏好
- 支持人工删除、合并、固定

### 使用说明

1. 在某成员页面发起任务
2. 系统只加载该成员的事实与记忆
3. 任务结束后筛选有价值信息写入记忆
4. 用户在记忆页管理历史记忆

### 实现效果

避免不同成员之间上下文串线，这是你这个 Agent 项目的一个明显差异点。

---

## 11. Agent 设计规范

## 11.1 当前建议

- 继续保留手写 runtime
- 先不要引入 LangChain
- 多步工作流再考虑 LangGraph

## 11.2 工具调用原则

- 模型不能直接执行任意 shell
- 所有能力都暴露为白名单工具
- 工具输入必须是结构化参数
- 文件访问必须限制在受控目录
- 导出和写操作要有审计记录

## 11.3 建议工具清单

- `extract_archive(member_id, archive_path)`
- `list_member_files(member_id)`
- `parse_uploaded_document(file_path)`
- `run_material_package_check(member_id)`
- `export_member_report(member_id, format)`
- `create_meeting_summary(meeting_id)`
- `write_member_memory(member_id, memory_payload)`
- `load_member_context(member_id)`

---

## 12. OCR 与文件处理规范

## 12.1 支持输入

- `.docx`
- `.pdf`
- `.png/.jpg/.jpeg/.bmp/.tiff`
- `.zip`

## 12.2 建议处理流程

1. 判断文件类型
2. 文本型文档直接解析
3. 图片 / 扫描件进入 OCR
4. 标记低置信度片段
5. 人工确认正式文本
6. 正式文本进入后续核查

## 12.3 为什么必须有人审

因为党务材料里有大量：

- 手写内容
- 盖章扫描件
- 表格
- 模糊图片

这类材料很难一次自动识别准确。  
真正可落地的方案不是“宣称全自动”，而是做出 `OCR 初稿 + 重点字段标红 + 人工确认 + 正式入库` 的闭环。

---

## 13. 数据模型建议

## 13.1 当前已有

- `members`
- `timeline_events`
- `materials`
- `reminders`

## 13.2 v2 建议新增

- `member_memories`
- `ocr_tasks`
- `meetings`
- `meeting_actions`
- `knowledge_chunks`
- `agent_runs`
- `member_material_checks`

## 13.3 数据设计原则

- 结构化事实进数据库
- 记忆单独存储
- OCR 原始结果与确认结果分开存
- Agent 执行记录单独留痕

---

## 14. API 演进建议

## 14.1 当前已有核心接口

- `POST /api/check-doc`
- `POST /api/upload`
- `POST /api/meeting`
- `POST /api/content`
- `POST /api/chat`
- `GET /api/status`
- `GET /api/download`
- `GET/POST/PATCH/DELETE /api/members...`
- `GET /api/dashboard`
- `GET /api/reminders`

## 14.2 v2 建议新增接口

### 材料与 OCR

- `POST /api/materials/archive/import`
- `POST /api/members/{id}/materials/check`
- `POST /api/ocr/preview`
- `POST /api/ocr/confirm`
- `GET /api/ocr/tasks/{task_id}`

### 记忆与 Agent

- `GET /api/members/{id}/memories`
- `POST /api/members/{id}/memories`
- `DELETE /api/members/{id}/memories/{memory_id}`
- `POST /api/agent/tasks`
- `GET /api/agent/tasks/{task_id}`
- `GET /api/agent/runs/{run_id}`

### 会议闭环

- `POST /api/meetings/plan`
- `POST /api/meetings/parse`
- `POST /api/meetings/{id}/confirm-actions`
- `GET /api/meetings/{id}/export`

---

## 15. 开发优先级建议

建议按下面顺序做，而不是同时大改所有层：

### 第一阶段：把现有基础能力做完整

- 完善材料检查规则
- 完善上传解析
- 完善前端工作台结构
- 梳理 README 和文档

### 第二阶段：做出真正的 Agent 亮点

- zip 材料包导入
- 材料整套一致性核查
- OCR 人工复核闭环
- 成员级独立记忆

### 第三阶段：补齐工作流闭环

- 会议待办写入提醒
- 材料核查结果回写台账
- Agent run trace
- 成果物导出历史

### 第四阶段：简历强化工程升级

- 前端升级 Vue 3 + TypeScript
- 后端整理为 FastAPI
- 为 LangGraph 预留工作流节点

---

## 16. 用于简历时的项目表述建议

如果后续把 v2 做到位，这个项目可以这样概括：

> 设计并开发本地党务智能 Agent 工作台，围绕发展党员材料核查、会议闭环整理、制度知识检索、成员级长期记忆等场景，构建基于 Python、SQLite、Ollama 的本地多工具 Agent 系统；实现文件解析、OCR、人机复核、规则检索、台账回写与成果导出等完整工作流。

这类表述比“做了一个聊天机器人”更能体现：

- Agent tool calling
- 本地模型接入
- RAG
- OCR
- 工作流编排
- 结构化数据与长期记忆设计

---

## 17. 结论

当前 PartyMate 已经不是一个纯演示性质的小脚本，而是：

- 有 Web UI
- 有 CLI
- 有本地模型接入
- 有文件解析与 OCR
- 有规则检索
- 有成员看板与 SQLite

但它还没有完全成长为一个真正有竞争力的 `党务智能 Agent 工作台`。

后续最值得投入的方向不是 Spring Boot 平台化，而是把下面四件事做扎实：

1. `成员级独立记忆`
2. `材料包整套一致性核查`
3. `OCR 人工复核闭环`
4. `会议与台账的任务闭环`

如果这四部分完成，再决定是否升级为 Vue 3 + FastAPI，会比先做技术壳子更有价值。
