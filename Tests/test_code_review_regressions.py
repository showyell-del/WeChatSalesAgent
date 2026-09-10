import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from agent_core.sync_cli import command_sync
from agent_core.sync_store import SyncStore


ROOT = Path(__file__).parents[1]


class CodeReviewRegressionTests(unittest.TestCase):
    def test_native_send_surface_is_completely_removed(self):
        removed = [
            "agent_core/native_send_session.py",
            "agent_core/send_cli.py",
            "agent_core/send_daemon.py",
            "agent_core/send_dispatch.py",
            "agent_core/send_store.py",
            "agent_core/send_statuses.json",
            "agent_core/send_limits.py",
            "native-worker/phase0_worker.py",
            "native-worker/profile_loader.py",
            "native-worker/send/native_send_once.py",
            "native-worker/send/native/single_send_agent.js",
            "scripts/phase0_worker.sh",
            "scripts/phase6_send.sh",
            "scripts/phase6_validate.sh",
        ]
        for relative in removed:
            self.assertFalse((ROOT / relative).exists(), relative)

        app = (ROOT / "app/Phase0App/main.m").read_text(encoding="utf-8")
        build = (ROOT / "scripts/build_phase0_app.sh").read_text(encoding="utf-8")
        workbook = (ROOT / "scripts/build_lead_workbook.mjs").read_text(
            encoding="utf-8"
        )
        for forbidden in (
            "dispatchSendBatch",
            "send_daemon",
            "nativeSendService",
            "NativeWorker",
        ):
            self.assertNotIn(forbidden, app + build)
        self.assertNotIn("发送状态", workbook)
        self.assertNotIn("send_status", workbook)
        workspace = (ROOT / "agent_core/workspace_service.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('"schema_version": "workspace.v2"', workspace)
        self.assertIn('snapshot.schema_version === "workspace.v2"', workbook)
        self.assertIn('snapshot.schema_version === "agent.query.v1"', workbook)

    def test_successful_agent_query_clears_startup_error_and_publishes_task_result(self):
        source = (ROOT / "app/Phase0App/main.m").read_text(encoding="utf-8")
        agent = source.split("- (void)askCustomerAgent:", 1)[1].split(
            "- (NSString *)currentDBPath:", 1
        )[0]
        self.assertIn("self.startupError = nil", agent)
        self.assertIn("[self agentLeadSummary]", agent)
        self.assertIn('self.statusLabel.stringValue = [NSString stringWithFormat:@"完成 · %lu 位"', agent)
        self.assertIn('object[@"analysis_trace"]', agent)

    def test_workspace_rebuild_keeps_a_window_alive(self):
        source = (ROOT / "app/Phase0App/main.m").read_text(encoding="utf-8")
        rebuild = source.split("- (void)rebuildWorkspaceWithMessage:", 1)[1].split(
            "- (NSString *)messageFromEvent:", 1
        )[0]
        self.assertIn("NSWindow *previousWindow = self.window", rebuild)
        self.assertLess(rebuild.index("[self buildWindow]"), rebuild.index("[previousWindow orderOut:nil]"))

    def test_only_native_dashboard_and_message_search_are_exposed(self):
        source = (ROOT / "app/Phase0App/main.m").read_text(encoding="utf-8")
        self.assertIn(
            'buttonWithTitle:@"▦  仪表盘" target:self action:@selector(openAnalyticsDashboard:)',
            source,
        )
        self.assertIn('buttonWithTitle:@"☷  客户表"', source)
        message_search = source.split("- (void)openMessageSearch:", 1)[1].split(
            "- (NSDictionary *)loadSnapshotAtPath:", 1
        )[0]
        self.assertIn('buttonWithTitle:@"≡  消息检索"', source)
        self.assertIn("chatlogReadAPIIsReady", message_search)
        self.assertIn('@[@"action", @"start-http"]', message_search)
        self.assertIn("ownedService.running", message_search)
        self.assertIn("agent_core.message_search_cli", source)
        self.assertIn("agent_core.dashboard_cli", source)
        self.assertIn("NativeBarChartView", source)
        self.assertIn("dashboardTypeChart", source)
        self.assertIn("dashboardHourChart", source)
        self.assertIn('Label(@"当前可查询数据库"', source)
        self.assertIn("prepareOwnedChatlogPortForBinary", source)
        self.assertIn('Label(@"群聊对比表"', source)
        self.assertIn('Label(@"发言人排行榜"', source)
        self.assertNotIn('buttonWithTitle:@"查看客户表"', source)
        self.assertNotIn("WKWebView", source)
        self.assertNotIn("openURL:", source)
        self.assertIn('Label(@"客户 Agent"', source)
        self.assertIn('AgentComposerTextView', source)
        self.assertIn('deepseek-v4-flash', source)
        self.assertNotIn('Label(@"任务记录"', source)
        self.assertIn('agent_progress', source)
        self.assertIn('覆盖审计', source)
        self.assertIn('AgentComposerTextView', source)
        self.assertIn('agentLeadSummary', source)
        self.assertIn('@"customer_total": @0', source)
        self.assertIn("已同步 %@ 个对话，可以开始提问", source)
        self.assertNotIn("这些聊天不会被预先标记或批量分析", source)

    def test_chatlog_health_requires_owned_listener_process(self):
        source = (ROOT / "app/Phase0App/main.m").read_text(encoding="utf-8")
        connect = source.split("- (void)connectWeChatData:", 1)[1].split(
            "- (NSArray<NSString *> *)commaSeparatedValues:", 1
        )[0]
        self.assertIn('@"/usr/sbin/lsof"', source)
        self.assertIn("ownedService.running", connect)
        self.assertIn("process:ownedService.processIdentifier listensOnTCPPort:5030", connect)
        self.assertIn("chatlogReadAPIIsReady", connect)

    def test_chatlog_readiness_wait_is_async_and_has_no_false_timeout(self):
        source = (ROOT / "app/Phase0App/main.m").read_text(encoding="utf-8")
        connect = source.split("- (void)connectWeChatData:", 1)[1].split(
            "- (NSArray<NSString *> *)commaSeparatedValues:", 1
        )[0]
        self.assertIn("dispatch_get_global_queue", connect)
        self.assertIn("while (ownedService.running)", connect)
        self.assertNotIn("attempt <", connect)
        self.assertNotIn("请先完成微信重新登录", connect)

    def test_keychain_secret_is_never_passed_in_process_arguments(self):
        source = (ROOT / "agent_core/keychain.py").read_text(encoding="utf-8")
        self.assertNotIn('"-w", secret', source)
        self.assertIn("SecKeychainAddGenericPassword", source)
        self.assertIn("SecKeychainItemModifyAttributesAndData", source)
        self.assertIn("SecKeychainItemFreeContent", source)

    def test_customer_agent_has_no_manual_business_or_batch_analysis_controls(self):
        source = (ROOT / "app/Phase0App/main.m").read_text(encoding="utf-8")
        self.assertNotIn('buttonWithTitle:@"业务设置"', source)
        self.assertNotIn('buttonWithTitle:@"批准传输"', source)
        self.assertNotIn('buttonWithTitle:@"估算成本"', source)
        self.assertNotIn('buttonWithTitle:@"运行 DeepSeek"', source)
        self.assertIn("agent_core.customer_agent_cli", source)
        self.assertIn("runCustomerAgentCommand", source)
        self.assertIn("覆盖审计", source)
        self.assertNotIn("针对本次问题检索和分析聊天", source)

    def test_build_has_one_artifact_tool_resolution_path(self):
        source = (ROOT / "scripts/build_phase0_app.sh").read_text(encoding="utf-8")
        section = source.split("artifact-tool-ok", 1)[0][-300:]
        self.assertNotIn("||", section)
        self.assertIn('cd "$RESOURCES_DIR/Export"', source)

    def test_full_chatlog_smoke_fails_closed(self):
        smoke = (ROOT / "scripts/phase0_chatlog_smoke.sh").read_text(encoding="utf-8")
        validator = (ROOT / "scripts/phase0_validate.sh").read_text(encoding="utf-8")
        self.assertIn('"failed" "CHATLOG_SERVICE_UNAVAILABLE"', smoke)
        self.assertIn("exit 1", smoke)
        self.assertIn("CHATLOG_HTTP_LIST_CALLABLE", validator)
        self.assertNotIn("run_worker", validator)

    def test_sync_failure_preserves_discovered_data_root(self):
        class Client:
            def __init__(self, *_):
                pass

            def health(self):
                return {"status": "ok"}

            def databases(self):
                return {
                    "message": [
                        "/tmp/xwechat_files/wxid_demo/db_storage/message/message_0.db"
                    ]
                }

        class Runtime:
            def __init__(self, *_):
                pass

            def status(self, _):
                return {"data_key": ""}

            def obtain_key(self, _):
                return None

        with tempfile.TemporaryDirectory() as tmpdir:
            db = str(Path(tmpdir) / "state.sqlite3")
            args = SimpleNamespace(
                addr="127.0.0.1:5030",
                timeout=1,
                chatlog_bin="chatlog",
                db=db,
                account_id="wxid_demo",
                limit=10,
            )
            with (
                mock.patch("agent_core.sync_cli.ChatlogClient", Client),
                mock.patch("agent_core.sync_cli.ChatlogRuntime", Runtime),
            ):
                self.assertEqual(command_sync(args), 1)
            store = SyncStore(db)
            try:
                account = store.conn.execute(
                    "SELECT data_root,status FROM accounts WHERE account_id='wxid_demo'"
                ).fetchone()
                self.assertEqual(account["data_root"], "/tmp/xwechat_files/wxid_demo")
                self.assertEqual(account["status"], "failed")
            finally:
                store.close()

    def test_build_manifest_is_exact_and_fail_closed(self):
        manifest = json.loads(
            (ROOT / "config/build_inputs.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["node"]["version"], "v24.14.0")
        self.assertEqual(manifest["artifact_tool"]["version"], "2.8.36")
        self.assertEqual(
            manifest["schema_version"], "wechat-sales-agent.build-inputs.v3"
        )
        self.assertEqual(manifest["python_runtime"]["python_runtime_arch"], "arm64")
        self.assertIn("python_stdlib_tree_sha256", manifest["python_runtime"])
        self.assertEqual(manifest["python_packages"]["pydantic_version"], "2.12.5")
        self.assertEqual(manifest["python_packages"]["pydantic_core_version"], "2.41.5")
        self.assertEqual(manifest["python_packages"]["frida_version"], "16.7.19")
        self.assertIn("tree_sha256", manifest["artifact_tool"])
        build = (ROOT / "scripts/build_phase0_app.sh").read_text(encoding="utf-8")
        self.assertNotIn("CODEX_PRIMARY_NODE_ROOT", build)
        self.assertNotIn(".cache/codex-runtimes", build)
        self.assertIn("verify_build_inputs.py", build)
        self.assertIn('pydantic.VERSION == "2.12.5"', build)

    def test_chatlog_license_and_release_cleanup_are_required(self):
        build = (ROOT / "scripts/build_phase0_app.sh").read_text(encoding="utf-8")
        dmg = (ROOT / "scripts/build_dmg.sh").read_text(encoding="utf-8")
        self.assertIn('cp chatlog/LICENSE "$RESOURCES_DIR/Chatlog/LICENSE"', build)
        self.assertIn(
            'test -f "$MOUNT_DIR/WeChatSalesAgent.app/Contents/Resources/Chatlog/LICENSE"',
            dmg,
        )
        self.assertIn('rm -rf "$APP_DIR"', dmg)
        self.assertLess(
            dmg.index('mv -f "$DMG_CANDIDATE" "$DMG_PATH"'), dmg.index("SHA256=")
        )
        self.assertNotIn('rm -f "$DMG_PATH"', dmg)

    def test_workbook_rejects_every_scanned_formula_error(self):
        source = (ROOT / "scripts/build_lead_workbook.mjs").read_text(encoding="utf-8")
        self.assertIn('["#REF!", "#DIV/0!", "#VALUE!", "#NAME?", "#N/A"]', source)
        self.assertIn("formulaErrors.some", source)

    def test_phase4_negative_case_uses_isolated_fixture(self):
        validator = (ROOT / "scripts/phase4_validate.sh").read_text(encoding="utf-8")
        self.assertIn("missing.sqlite3", validator)
        self.assertNotIn("wxid_3prysbeqgvci22_9f8d", validator)


if __name__ == "__main__":
    unittest.main()
