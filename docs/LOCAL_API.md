# 本机 REST API

本机 API 只监听 `127.0.0.1`，用于把仪表盘、会话、消息检索和智能分析接入其他本机 Agent 或自动化工作流。它不会对局域网或公网开放。

安装版 App 打开后会自动启动当前账号的 Chatlog 和 API，默认地址为 `http://127.0.0.1:8765`，API 进程随 App 退出。点击智能分析页顶部的“Agent 接入”，可查看 MCP 配置、WorkBuddy 连接器、OpenAPI 地址、Bearer token 和调用示例。MCP 使用方式见 [LOCAL_MCP.md](LOCAL_MCP.md)。

## 命令行启动（开发调试）

首次生成 Bearer token；token 保存在 macOS Keychain 的 `com.wechat-sales-agent.local-api` service 下：

```bash
python3 -m agent_core.local_api token
```

需要废止旧 token 时：

```bash
python3 -m agent_core.local_api token --rotate
```

启动服务：

```bash
python3 -m agent_core.local_api serve --port 8765
```

若使用项目运行时数据库，可显式传入：

```bash
python3 -m agent_core.local_api serve \
  --db runtime/agent_state.sqlite3 \
  --chatlog-addr 127.0.0.1:5030 \
  --port 8765
```

完整契约在 `GET /openapi.json`。除 `GET /v1/health` 和 `GET /openapi.json` 外，所有请求都需要：

```text
Authorization: Bearer <token>
```

每次业务读取和分析执行前，服务都会读取 Chatlog 的 `/api/v1/db`，并要求它只包含状态库 `active_account` 对应的账号。两者不完全一致时返回 `409 ACCOUNT_MISMATCH`，不会读取其他账号的数据。

## 示例

```bash
TOKEN="$(python3 -m agent_core.local_api token)"

curl -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8765/v1/status

curl -H "Authorization: Bearer $TOKEN" \
  'http://127.0.0.1:8765/v1/conversations?limit=50'

curl -H "Authorization: Bearer $TOKEN" \
  --get http://127.0.0.1:8765/v1/messages \
  --data-urlencode 'chat=wxid_example' \
  --data-urlencode 'keyword=报价' \
  --data-urlencode 'limit=50'
```

分页响应中的 `pagination.next_cursor` 原样放入下一次请求的 `cursor`。消息检索分页覆盖最近 1000 条匹配结果，这是底层检索接口的确定性读取上限。

智能分析必须提供 `Idempotency-Key`，接口立即返回 `202`。相同键和相同请求体会返回同一个操作；相同键配不同请求体返回 `409`。

```bash
curl -i \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: workflow-20260919-001' \
  --data '{"question":"找出近半年和我有创业讨论的人"}' \
  http://127.0.0.1:8765/v1/analyses

curl -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8765/v1/operations/op_xxx
```

分析由单工作队列串行执行。操作状态依次为 `queued`、`running`、`succeeded` 或 `failed`；成功结果位于 `result`，失败信息位于 `error`。

## 错误和限制

- 错误统一使用 `application/problem+json`，字段符合 RFC 7807，并附带稳定的 `code`。
- JSON 请求体最多 1 MiB。
- 默认速率限制为每个本机客户端每分钟 120 次请求。
- 列表接口使用游标分页，单页最多 200 条。
- API 进程重启后，进程内的分析操作和幂等记录会清空；已完成的分析结果仍由现有分析状态库保存。
