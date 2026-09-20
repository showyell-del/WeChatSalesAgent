# 本机 MCP 与 WorkBuddy 连接器

微信客户分析 Agent 提供标准 MCP stdio Server，将已验证的本机 REST API 暴露为 Agent 可发现的结构化工具。MCP 层不读数据库、不复制分析逻辑，所有业务请求都经过 `http://127.0.0.1:8765/v1/` 和现有账号绑定校验。

## 使用前提

1. 将 App 安装在 `/Applications/WeChatSalesAgent.app`。
2. 打开 App，连接并同步需要读取的微信账号。
3. App 保持运行。Chatlog `127.0.0.1:5030` 和 REST API `127.0.0.1:8765` 随 App 启动和退出。

MCP Server 使用 App 内置 Python，通过 macOS Keychain 读取本机 API token，不在 WorkBuddy 连接器、命令行或配置文件中存储明文凭据。

## WorkBuddy

可交付连接器位于：

```text
integrations/workbuddy/
├── connector-meta.json
├── mcp.json
├── icon.svg
└── skills/wechat-analysis/SKILL.md
```

安装版 App 会将该目录复制到：

```text
/Applications/WeChatSalesAgent.app/Contents/Resources/Integrations/WorkBuddy
```

WorkBuddy 连接器使用单一 stdio Server：

```json
{
  "mcpServers": {
    "wechat-customer-analysis": {
      "type": "stdio",
      "command": "/Applications/WeChatSalesAgent.app/Contents/Resources/PythonRuntime/bin/python3",
      "args": ["-m", "agent_core.local_mcp"],
      "env": {
        "PYTHONHOME": "/Applications/WeChatSalesAgent.app/Contents/Resources/PythonRuntime",
        "PYTHONPATH": "/Applications/WeChatSalesAgent.app/Contents/Resources/Python"
      },
      "timeout": 30000
    }
  }
}
```

## MCP 工具

- `list_conversations`：分页列出当前账号会话。
- `search_wechat_messages`：在明确会话中检索原始消息。
- `get_dashboard`：读取仪表盘真实统计。
- `analyze_conversation`：异步发起智能分析，立即返回 operation id。
- `get_analysis_result`：轮询分析状态并取得结果。

`analyze_conversation` 不在 MCP 请求内等待 DeepSeek 长任务完成。MCP Server 为每次工具调用生成幂等键，REST API 返回的 operation id 是后续轮询的唯一标识。

## 手工协议验证

开发环境中先确保 App 的本机 API 已启动，再执行：

```bash
python3 -m agent_core.local_mcp
```

通过 stdin 逐行发送 JSON-RPC `initialize`、`notifications/initialized`、`tools/list` 和 `tools/call`；stdout 只输出换行分隔的 JSON-RPC 消息。

自动化验证：

```bash
python3 -m unittest Tests.test_local_mcp Tests.test_workbuddy_connector Tests.test_local_api
```

## 边界

- 当前 MCP 是本机 stdio 接入，不是公网 MCP 服务。
- 只能读取 App `active_account` 与 Chatlog 数据库路径严格一致的微信账号。
- App 未运行、账号未连接或账号不一致时，工具明确返回错误，不切换账号、不伪造结果、不降级。
