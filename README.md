# 微信客户激活 Agent（内测）

面向 macOS Apple Silicon 的本地桌面工具：读取用户明确连接的微信私聊，通过 DeepSeek 生成可追溯到真实对话证据的线索客户表，并导出 Excel 供经营跟进。

## 安装与使用

1. 使用授权的 Apple Silicon 内测 Mac，安装并登录微信。
2. 打开 `dist/WeChatSalesAgent-MVP-macOS-arm64.dmg`，将 App 拖到“应用程序”。
3. 打开 App，点击“关闭 SIP 指引”，按界面步骤进入 macOS 恢复模式完成操作。
4. 重启并再次打开 App，确认左侧显示“SIP 已关闭”，再点击“连接并同步微信”。
5. 填写业务设置，保存 DeepSeek API Key，确认外部传输后先估算成本，再运行分析。
6. 在客户详情中核对需求、阻碍、联系方式、建议动作和真实聊天证据，或导出 Excel。

当前 MVP 不包含任何微信消息发送、图片、视频、文件或拖放入口，也不使用剪贴板、键鼠模拟等替代方案。

当前包是 ad-hoc 签名的本地内测 MVP，不作为大规模商用发行包。

关闭 SIP 会降低 macOS 系统保护。在替换掉当前密钥提取方案之前，该 MVP 不属于默认 Mac 上开箱即用的普通用户发行版。

## 数据与安全边界

- 原始聊天和分析状态保存在用户本机。
- DeepSeek API Key 保存在 macOS Keychain。
- 只有用户明确批准后，候选聊天证据才会发送给 DeepSeek。
- “意向分”是可解释的业务分级，不冒充经转化标签校准的付费概率。

## 开发验证

```bash
python3 -m unittest discover -s Tests -p 'test_*.py'
scripts/phase0_validate.sh --no-fallback-scan
scripts/phase4_validate.sh
scripts/build_dmg.sh
```

已验证的运行时路径、数据边界和重建规则见 [Agent.md](Agent.md)。
