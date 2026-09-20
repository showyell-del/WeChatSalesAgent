---
name: wechat-analysis
display_name: 微信客户分析
display_name_en: WeChat Customer Analysis
description: 检索本机微信会话和消息、查看仪表盘，或发起基于原始证据的客户与群聊分析。
description_zh: 检索本机微信会话和消息、查看仪表盘，或发起基于原始证据的客户与群聊分析。
description_en: Search local WeChat conversations and messages, inspect dashboard metrics, or run evidence-based customer and group analysis.
allowed-tools: search_wechat_messages, list_conversations, get_dashboard, analyze_conversation, get_analysis_result
version: 1.0.2
author: WeChat Customer Analysis Agent
---

# 微信客户分析

当用户要查找微信联系人、检索聊天原文、了解微信业务概况，或分析客户和群聊时使用本连接器。所有数据都来自用户当前在本机应用中连接的微信账号。

## 工具选择

- `list_conversations`：列出当前账号的会话。可传 `limit` 和 `cursor`；当返回 `pagination.has_next=true` 时，用 `pagination.next_cursor` 继续读取。
- `search_wechat_messages`：检索一个明确会话的消息。`chat` 必填；可传 Unix 秒时间范围 `since`、`until`，以及 `keyword`、`msg_type`、`sub_type`、`direction`、`limit`、`cursor`。需要完整覆盖时持续翻页，直到 `has_next=false`。
- `get_dashboard`：读取当前业务仪表盘。可用 `time_range`（`today`、`last-1d`、`last-30d`、`all`）、`private_chat` 和 `group_chat` 控制范围。
- `analyze_conversation`：发起较耗时的语义分析。`question` 必填；可传 `session_id` 延续同一分析会话、`task_type` 指定分析模式、`timeout` 设置 10～600 秒执行上限。返回操作对象后不要重复提交。
- `get_analysis_result`：用 `operation_id` 查询分析状态。状态为 `queued` 或 `running` 时稍后继续查询；`succeeded` 时读取 `result`；`failed` 时向用户说明 `error`。

## 执行规则

1. 分析指定私聊或群聊前，先调用一次 `list_conversations` 验证当前账号、连接器和目标会话均可用；如果首页未找到精确名称，按 `next_cursor` 继续翻页，不得在未确认目标时发起分析。
2. 精确查原文、日期、发送人或上下文时使用 `search_wechat_messages`；不要用模型记忆猜测聊天内容。
3. 统计概况使用 `get_dashboard`。只有用户要求归纳、比较、画像、机会、风险、时间线或群聊主题时，才调用 `analyze_conversation`。
4. 分析请求只提交一次，然后使用返回的操作 ID 调用 `get_analysis_result`。立即查询一次状态；若仍为 `queued` 或 `running`，每 10 秒查询一次。不要以重复提交代替轮询，也不要使用 30 秒以上的固定等待。
5. 回答中区分聊天原始事实、分析结论和证据不足之处。引用工具返回的证据，不编造联系人、消息或结论。
6. 不向回复、日志或其他工具暴露本机密钥、Bearer token、数据库路径或未被用户要求的私人聊天内容。
7. `question` 必须原样保留用户的完整 Unicode 文本，包括中文、完整群名和 emoji；不得缩写、翻译或只传关键词。
8. 最终答复只呈现用户要求的数据基础、结论、证据和必要局限。除非用户明确追问，不展示工具名、operation ID、轮询过程、失败重试、调试经验或本机文件路径。
9. 不得自动创建 Skill、记忆或规则文件；只有用户明确要求时才可写入。用户未要求报告文件时，直接在对话中给出结果。

## 错误处理

- `ACCOUNT_MISMATCH`：停止读取或分析，提示用户回到微信客户分析应用，重新连接并同步需要使用的微信账号；不能改读另一个账号。
- `UNAUTHORIZED` 或连接器启动失败：提示用户确认本机应用和连接器已经安装并启动，不要索要或回显 token。
- 游标无效：从第一页重新调用对应的列表工具；不要自行构造游标。
- 分析失败：展示工具返回的可读错误，不用无证据的答案替代失败结果。
