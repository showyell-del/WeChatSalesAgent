# 微信客户成交 Agent

## What This Is

一款运行在 macOS Apple Silicon 上的专业桌面 Agent，面向街舞店等依靠微信私聊成交的本地商家。它从本机微信读取聊天，从大量历史客户中找出值得再激活的线索，展示可追溯证据和关键信息，并在人工确认后完成个性化批量触达。

产品只保留直接产生商业价值的功能：数据连接、线索筛选、成交意向判断、客户表、仪表盘和受控发信。

## Core Value

从真实微信私聊中准确找到值得再激活的客户，给出可审计的业务证据，并安全完成触达闭环。

## Requirements

### Validated

- ✓ Chatlog 本地会话列表和私聊历史 API 可读取真实聊天数据 — 基础设施验证
- ✓ 本机 WeChat 4.1.11.55 已建立精确版本、完整 dylib 和 arm64 slice 哈希门禁 — Spike 001
- ✓ 原生异步发送对象必须使用 `calloc`/`mmap` 持久内存 — Spike 001
- ✓ `uploadappattach -> sendappmsg` 简单文件路径在 4.1.11.55 上已被实测否定 — Spike 001

### Active

- [ ] 自动发现微信账号，完成取钥、逐库验证、解密和增量同步
- [ ] 按时间范围筛选真人一对一私聊，确定性提取需求、联系方式、预算、时间、区域和阻碍
- [ ] 通过 DeepSeek 严格 JSON 输出成交意向分、证据、建议动作和个性化激活文案
- [ ] 提供专业 macOS 桌面面板、仪表盘、线索客户表、证据详情和 Excel 导出
- [ ] 完成文本、图片、视频和任意文件四种经过真实 Ack 验证的原生发送适配器
- [ ] 通过单一会话所有者串行执行批量触达，记录每个客户的队列、Ack、失败、取消和清理状态
- [ ] 使用真实业务账号完成半年私聊到客户激活的全链路验收和 100 目标连续发送测试

### Out of Scope

- Web 控制台 — 最终产品是专业桌面程序
- 群聊大盘、群成员排行和群聊对比 — 不直接服务私聊客户成交
- 朋友圈、收藏、裸数据库、SQL、通用搜索、时间知识图谱和通用 RAG — 无首版商业必要性
- Hermes、系统分享、剪贴板和键鼠模拟发信 — 不是可验证的原生产品路径
- Windows、Intel Mac 和未精确验证的微信版本 — 首版只锁定 macOS Apple Silicon 与 WeChat 4.1.11.55
- 未经预览和人工确认的自动群发 — 避免错发和虚构承诺

## Context

- 初始场景是街舞店老板在半年约 1000 个微信客户中找出有成交潜力的人，并获得一张可立即跟进的表。
- Chatlog Alpha 只作为底层数据和原生微信能力来源，不复制其通用 Web 后台。
- 当前 Chatlog 上游原生发送仅支持文本和图片；视频和文件必须建立独立适配器。
- 评分在获得真实成交标签校准前只能称为“成交意向分”，不宣称统计成交概率。

## Constraints

- **完成度**: 禁止降级、禁止兜底，所有可见功能必须真实完成并经过验证
- **简洁性**: 不保留失效路径、兼容分支或无商业价值功能
- **兼容性**: 首版精确锁定 WeChat 4.1.11.55 build 269111 和已验证哈希
- **隐私**: 原始聊天默认本机处理，只向 DeepSeek 上传候选客户的必要证据片段
- **发信**: 只有真实送达、可识别 Ack 且清理完整的类型才能出现在产品中
- **并发**: 所有 native 发信由单一会话所有者串行化，不允许共享原生状态并发操作

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| 使用桌面面板，不使用 Web UI | 更符合商业工具专业感和本地数据边界 | — Pending |
| 保留 Chatlog 数据层、仪表盘概念和原生发信核心 | 它们直接支撑客户发现与触达 | ✓ Good |
| DeepSeek 采用本地规则预筛选后的必要证据输入 | 控制 Token 成本与聊天数据暴露 | — Pending |
| 发信实行精确版本和哈希失败关闭 | 原生偏移不匹配会造成崩溃或错发 | ✓ Good |
| 不继续投入 `uploadappattach` 简单文件路径 | 已在本机 4.1.11.55 上证明不进入 Req2Buf/Buf2Resp | ✓ Good |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition**:
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone**:
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-07-23 after initialization*
