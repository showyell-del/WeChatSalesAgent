# 微信客户成交 Agent — 产品需求

## 产品定义

一款运行在 macOS Apple Silicon 上的专业桌面 Agent。它从本机微信读取近一段时间的真人私聊，识别值得跟进的客户，生成可审计的客户激活表，并在人工确认后向目标客户发送个性化文本及附件。

产品不复制 Chatlog 的通用后台。每个可见功能必须直接服务于发现线索、判断意向、组织跟进或完成触达。

## 首版平台边界

- 仅支持 macOS Apple Silicon。
- 仅支持经过精确验证的微信 `4.1.11.55` build `269111`；完整 `wechat.dylib` SHA-256 必须为 `c2a4794b343625a8013752095e76bc688acd42d48f30001a255620db2fc542a9`，arm64 slice SHA-256 必须为 `da53625065d283d748f959627f5e4d724eb786f2911f49c91a72cc12f17d30f7`。
- 不匹配的微信版本必须停止取钥或发信，并明确显示原因。
- 桌面程序面板，不提供 Web 控制台。
- 微信原始聊天默认只在本机处理；只向用户配置的 DeepSeek API 发送经过筛选的必要片段。

## 核心用户流程

1. 用户连接并选择微信业务账号，Agent 完成取钥、解密和增量同步。
2. 用户选择分析时间范围并启动客户筛选。
3. Agent 排除群聊、公众号、系统会话和无有效互动的联系人。
4. 本地规则提取需求、问价、课表、地址、体验、付款、联系方式、时间限制及负面信号。
5. DeepSeek 根据必要证据生成结构化意向判断、阻碍、建议动作和个性化激活文本。
6. 用户在仪表盘和客户表中检查评分、证据及预计 Token 成本。
7. 用户选择客户，输入公共要求或拖入附件，预览每位客户的最终消息。
8. 用户确认后，Agent 串行发送并记录每位客户的成功、失败、Ack 和清理状态。

## 功能需求

### 数据连接

- **REQ-DATA-001** 自动发现本机微信账号与数据目录。
- **REQ-DATA-002** 提取并逐库验证数据库密钥，维护明确的账号状态。
- **REQ-DATA-003** 完成首次解密和后续增量更新，不要求用户进入通用数据库页面。
- **REQ-DATA-004** 支持切换已验证的历史账号，但同一分析任务只能绑定一个明确账号。
- **REQ-DATA-005** 所有读取失败必须显示具体失败数据库或步骤，不使用旧快照冒充最新结果。

### 线索分析

- **REQ-LEAD-001** 按时间范围批量读取真人一对一私聊。
- **REQ-LEAD-002** 排除群聊、公众号、服务通知、机器人和无有效内容会话。
- **REQ-LEAD-003** 确定性提取手机、座机、微信号、年龄、年级、区域、可用时间、预算和明确需求。
- **REQ-LEAD-004** 输出 0–100 的成交意向分和高意向、待激活、长期培育、排除四档结果。
- **REQ-LEAD-005** 评分必须附带真实聊天证据、最近联系时间、阻碍因素和建议动作。
- **REQ-LEAD-006** 未经真实成交标签校准前，界面称其为“成交意向分”，不得称为统计成交概率。
- **REQ-LEAD-007** 支持店铺经营信息、产品、价格、优惠、地址、营业时间和禁用承诺等业务配置。
- **REQ-LEAD-008** DeepSeek 返回严格结构化 JSON；空结果、缺字段或证据不匹配必须判定分析失败。

### 仪表盘与客户表

- **REQ-UI-001** 仪表盘只展示客户总量、高意向人数、待激活人数、近期新增线索、意向分布和本次预计价值相关指标。
- **REQ-UI-002** 客户表支持按意向等级、最近联系、需求、阻碍、联系方式和发送状态筛选排序。
- **REQ-UI-003** 客户详情展示必要证据、关键信息、建议动作和待发送文案，不展示裸数据库结构。
- **REQ-UI-004** 导出一份格式清晰、可筛选的 Excel 客户激活表。
- **REQ-UI-005** 每次分析显示真实输入/输出 Token、预计费用和累计费用。

### DeepSeek

- **REQ-AI-001** 提供 DeepSeek API Key、Base URL 和模型配置接口，默认面向 `deepseek-v4-flash` 的非思考结构化任务。
- **REQ-AI-002** 本地先筛选和压缩证据，禁止默认上传半年完整聊天。
- **REQ-AI-003** 只为最终候选客户生成个性化激活文案。
- **REQ-AI-004** 文案不得虚构价格、优惠、库存、承诺或客户未表达的需求。
- **REQ-AI-005** 公共系统提示使用稳定前缀，以利用服务端上下文缓存并降低成本。

### 批量触达

- **REQ-SEND-001** 文本输入框支持公共要求，并为每位客户生成可编辑的个性化文本。
- **REQ-SEND-002** 支持将图片、视频和任意文件拖入附件区，发送前显示类型、大小和目标人数。
- **REQ-SEND-003** 文本、图片、视频和文件必须分别拥有经过验证的原生发送适配器；未完成验证的类型不得出现在可发送列表。
- **REQ-SEND-004** 所有发送命令由一个会话所有者串行执行，禁止并发操作共享 native 状态。
- **REQ-SEND-005** 一键发送前必须提供完整预览、目标人数、预计 Token、附件和最终确认。
- **REQ-SEND-006** 支持取消单个客户，默认保留用户筛选后的全部线索客户。
- **REQ-SEND-007** 每条消息记录 queued、running、succeeded、failed、Ack 和 cleanup 状态。
- **REQ-SEND-008** 发送失败不得切换到系统自动化、剪贴板、键鼠模拟或其他替代路径。
- **REQ-SEND-009** 任务结束或取消后必须完成脚本卸载、会话断开、Frida 关闭和微信健康检查。

## 明确不做

- 群聊数据大盘、群成员排行和群聊对比。
- 朋友圈、收藏、裸数据库、SQL 和通用全局搜索页面。
- 时间知识图谱、通用 RAG、wx-cli 兼容页面和发信调试页面。
- 自动生成后不经预览直接群发。
- Windows、Intel Mac 或未验证微信版本的兼容分支。

## 首版完成标准

- 使用一个真实业务账号完成取钥、解密、近半年私聊筛选、DeepSeek 分析、客户表导出和个性化触达闭环。
- 每个线索分数能追溯到真实证据，联系方式抽取经过人工抽样核对。
- 文本、图片、视频和文件分别通过真实私聊发送、Ack、取消和清理测试。
- 完成至少 100 个目标的连续串行发送测试，无错发、无残留 Frida helper、无微信持续高 CPU 或失去登录状态。
- 桌面界面不暴露无商业价值的 Chatlog 通用功能。

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| REQ-DATA-001 | Phase 1 | Complete |
| REQ-DATA-002 | Phase 1 | Complete |
| REQ-DATA-003 | Phase 1 | Complete |
| REQ-DATA-004 | Phase 1 | Complete |
| REQ-DATA-005 | Phase 1 | Complete |
| REQ-LEAD-001 | Phase 2 | Pending |
| REQ-LEAD-002 | Phase 2 | Pending |
| REQ-LEAD-003 | Phase 2 | Pending |
| REQ-LEAD-004 | Phase 3 | Pending |
| REQ-LEAD-005 | Phase 3 | Pending |
| REQ-LEAD-006 | Phase 3 | Pending |
| REQ-LEAD-007 | Phase 3 | Pending |
| REQ-LEAD-008 | Phase 3 | Pending |
| REQ-UI-001 | Phase 4 | Pending |
| REQ-UI-002 | Phase 4 | Pending |
| REQ-UI-003 | Phase 4 | Pending |
| REQ-UI-004 | Phase 4 | Pending |
| REQ-UI-005 | Phase 4 | Pending |
| REQ-AI-001 | Phase 3 | Pending |
| REQ-AI-002 | Phase 3 | Pending |
| REQ-AI-003 | Phase 3 | Pending |
| REQ-AI-004 | Phase 3 | Pending |
| REQ-AI-005 | Phase 3 | Pending |
| REQ-SEND-001 | Phase 6 | Pending |
| REQ-SEND-002 | Phase 6 | Pending |
| REQ-SEND-003 | Phase 5 | Pending |
| REQ-SEND-004 | Phase 6 | Pending |
| REQ-SEND-005 | Phase 6 | Pending |
| REQ-SEND-006 | Phase 6 | Pending |
| REQ-SEND-007 | Phase 6 | Pending |
| REQ-SEND-008 | Phase 6 | Pending |
| REQ-SEND-009 | Phase 6 | Pending |
