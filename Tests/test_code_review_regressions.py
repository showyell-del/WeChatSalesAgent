import json
import struct
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
        info_plist = (ROOT / "app/Phase0App/Info.plist").read_text(encoding="utf-8")
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
        self.assertIn('snapshot.schema_version === "agent.query.v2"', workbook)

    def test_successful_agent_query_clears_startup_error_and_publishes_task_result(self):
        source = (ROOT / "app/Phase0App/main.m").read_text(encoding="utf-8")
        agent = source.split("- (void)askCustomerAgent:", 1)[1].split(
            "- (NSString *)currentDBPath:", 1
        )[0]
        self.assertIn("self.startupError = nil", agent)
        self.assertIn("[self agentLeadSummary]", agent)
        self.assertIn('self.statusLabel.stringValue = [NSString stringWithFormat:@"完成 · %@"', agent)
        self.assertIn('object[@"analysis_trace"]', agent)
        self.assertIn('object[@"answer"]', agent)
        self.assertIn("self.lastAgentResult = object", agent)

    def test_customer_workspace_uses_hidden_scrollers_and_visible_agent_timeline(self):
        source = (ROOT / "app/Phase0App/main.m").read_text(encoding="utf-8")
        workspace = source.split("- (void)buildWindow", 1)[1].split(
            "- (NSInteger)numberOfRowsInTableView", 1
        )[0]
        self.assertNotIn(
            'NSTextField *title = Label(@"微信客户分析 Agent"', workspace
        )
        self.assertIn("agentTranscriptScroll.hasVerticalScroller = NO", workspace)
        self.assertIn("agentTranscriptScroll.hasHorizontalScroller = NO", workspace)
        self.assertIn("agentInputScroll.hasVerticalScroller = NO", workspace)
        self.assertIn("agentInputScroll.hasHorizontalScroller = NO", workspace)
        self.assertIn("agentInputScroll.borderType = NSNoBorder", workspace)
        self.assertNotIn("准备就绪", source)
        self.assertIn("NSString *initialStatus = [self startupDetailText]", workspace)
        self.assertIn(
            "self.agentSendButton.centerYAnchor constraintEqualToAnchor:composer.centerYAnchor",
            workspace,
        )
        self.assertIn("NSProgressIndicatorStyleSpinning", workspace)
        self.assertIn("[self.agentActivityIndicator startAnimation:nil]", source)
        self.assertIn("[self.agentActivityIndicator stopAnimation:nil]", source)
        self.assertIn("agentProgressTranscriptForQuestion", source)
        self.assertIn('@"planning", @"title": @"理解任务"', source)
        self.assertIn('@"retrieval", @"title": @"证据召回"', source)
        self.assertIn('@"analysis", @"title": @"语义复核"', source)
        self.assertIn('@"audit", @"title": @"覆盖审计"', source)
        self.assertIn('@"正在处理这项任务\\n"', source)
        self.assertIn('@"执行完成\\n"', source)

    def test_agent_composer_return_sends_and_shift_return_inserts_a_newline(self):
        source = (ROOT / "app/Phase0App/main.m").read_text(encoding="utf-8")
        handler = source.split(
            "- (BOOL)textView:(NSTextView *)textView doCommandBySelector:", 1
        )[1].split("- (NSString *)agentLeadSummary", 1)[0]
        self.assertIn("self.agentInput.hasMarkedText", handler)
        self.assertIn("@selector(insertNewline:)", handler)
        self.assertIn("@selector(insertNewlineIgnoringFieldEditor:)", handler)
        self.assertIn("NSEventModifierFlagShift", handler)
        self.assertIn("[self askCustomerAgent:textView]", handler)
        self.assertIn("return YES", handler)

    def test_native_edit_menu_routes_standard_copy_and_paste_shortcuts(self):
        source = (ROOT / "app/Phase0App/main.m").read_text(encoding="utf-8")
        self.assertIn("static void InstallMainMenu(void)", source)
        self.assertIn("action:@selector(copy:)", source)
        self.assertIn('keyEquivalent:@"c"', source)
        self.assertIn("action:@selector(paste:)", source)
        self.assertIn('keyEquivalent:@"v"', source)
        launch = source.split(
            "- (void)applicationDidFinishLaunching:(NSNotification *)notification", 1
        )[1].split("- (NSString *)storedAgentModel", 1)[0]
        self.assertIn("InstallMainMenu();", launch)

    def test_agent_input_clears_before_background_analysis_starts(self):
        source = (ROOT / "app/Phase0App/main.m").read_text(encoding="utf-8")
        handler = source.split("- (void)askCustomerAgent:", 1)[1].split(
            "- (void)newAgentAnalysis:", 1
        )[0]
        clear_index = handler.index('self.agentInput.string = @"";')
        dispatch_index = handler.index("dispatch_async(dispatch_get_global_queue")
        self.assertLess(clear_index, dispatch_index)
        success = handler.split("if (status != 0", 1)[1]
        self.assertNotIn('self.agentInput.string = @"";', success)

    def test_full_history_progress_uses_semantic_label_not_day_sentinel(self):
        source = (ROOT / "app/Phase0App/main.m").read_text(encoding="utf-8")
        progress = source.split("- (NSString *)agentProgressText:", 1)[1].split(
            "- (NSDictionary *)lastJSONObjectFromLines:", 1
        )[0]
        self.assertIn('stats[@"time_window_label"]', progress)
        self.assertNotIn('stats[@"time_window_days"]', progress)

    def test_agent_transcript_places_user_above_right_aligned_agent_block(self):
        source = (ROOT / "app/Phase0App/main.m").read_text(encoding="utf-8")
        self.assertIn("@interface AgentTranscriptView : NSTextView", source)
        self.assertIn("@interface AgentTranscriptScrollView : NSScrollView", source)
        self.assertIn("frame.size.width = width", source)
        self.assertIn("bezierPathWithRoundedRect", source)
        self.assertIn("ApplyAgentMessageBubble", source)
        self.assertIn('[target addAttribute:AgentBubbleAttributeName value:kind range:range]', source)
        self.assertIn("self.agentTranscript.autoresizingMask = NSViewWidthSizable", source)
        self.assertIn("self.agentTranscript.horizontallyResizable = NO", source)
        for start, end in (
            (
                "- (NSAttributedString *)agentProgressTranscriptForQuestion:",
                "- (NSAttributedString *)agentCompletedTranscriptForQuestion:",
            ),
            (
                "- (NSAttributedString *)agentCompletedTranscriptForQuestion:",
                "- (NSAttributedString *)agentFailureTranscriptForQuestion:",
            ),
        ):
            transcript = source.split(start, 1)[1].split(end, 1)[0]
            question = transcript.index("AppendAgentTextAligned(content")
            agent = transcript.index('AppendAgentText(content, @"✦  Agent\\n"')
            self.assertLess(question, agent)
            self.assertIn("NSTextAlignmentRight", transcript[question:agent])
            self.assertIn('@"user"', transcript[question:agent])
            self.assertIn('@"agent"', transcript[agent:])
            self.assertNotIn('@"你\\n"', transcript)

    def test_workspace_rebuild_keeps_a_window_alive(self):
        source = (ROOT / "app/Phase0App/main.m").read_text(encoding="utf-8")
        rebuild = source.split("- (void)rebuildWorkspaceWithMessage:", 1)[1].split(
            "- (NSString *)messageFromEvent:", 1
        )[0]
        self.assertIn("NSWindow *previousWindow = self.window", rebuild)
        self.assertLess(rebuild.index("[self buildWindow]"), rebuild.index("[previousWindow orderOut:nil]"))

    def test_only_native_dashboard_and_message_search_are_exposed(self):
        source = (ROOT / "app/Phase0App/main.m").read_text(encoding="utf-8")
        info_plist = (ROOT / "app/Phase0App/Info.plist").read_text(encoding="utf-8")
        build = (ROOT / "scripts/build_phase0_app.sh").read_text(encoding="utf-8")
        self.assertIn(
            'buttonWithTitle:@"▦  仪表盘" target:self action:@selector(openAnalyticsDashboard:)',
            source,
        )
        self.assertIn('buttonWithTitle:@"☷  智能分析"', source)
        message_search = source.split("- (void)openMessageSearch:", 1)[1].split(
            "- (NSDictionary *)loadSnapshotAtPath:", 1
        )[0]
        self.assertIn('buttonWithTitle:@"≡  消息检索"', source)
        self.assertIn("chatlogReadAPIIsReady", message_search)
        self.assertIn("startChatlogServiceForAccount:accountID", message_search)
        self.assertIn('@[@"action", @"start-http", @"--history", accountID]', source)
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
        self.assertIn('Label(@"微信客户分析 Agent"', source)
        self.assertIn("WeChatCustomerAnalysis.icns", info_plist + build)
        self.assertIn("微信客户分析 Agent", info_plist)
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

    def test_smart_analysis_tools_are_fixed_to_the_sidebar_bottom(self):
        source = (ROOT / "app/Phase0App/main.m").read_text(encoding="utf-8")
        workspace = source.split("- (void)buildWindow", 1)[1].split(
            "- (NSInteger)numberOfRowsInTableView", 1
        )[0]
        self.assertIn(
            "self.sipStatusLabel.bottomAnchor constraintEqualToAnchor:sidebar.bottomAnchor constant:-22",
            workspace,
        )
        self.assertIn(
            "connectButton.bottomAnchor constraintEqualToAnchor:sipButton.topAnchor constant:-8",
            workspace,
        )
        self.assertNotIn(
            "connectButton.topAnchor constraintEqualToAnchor:customerButton.bottomAnchor",
            workspace,
        )

    def test_smart_analysis_export_uses_task_specific_sheets(self):
        source = (ROOT / "scripts/build_lead_workbook.mjs").read_text(encoding="utf-8")
        for task_type, sheet_name in (
            ("customer_search", "客户清单"),
            ("opportunity_analysis", "机会清单"),
            ("reengagement_analysis", "激活建议"),
            ("customer_risk", "风险清单"),
            ("commitment_tracker", "承诺待办"),
            ("person_profile", "人物画像"),
            ("relationship_insight", "关系洞察"),
            ("comparison", "多人比较"),
            ("topic_analysis", "话题分析"),
            ("timeline", "事件时间线"),
            ("general_search", "相关结果"),
        ):
            self.assertIn(f'{task_type}: "{sheet_name}"', source)
        self.assertIn('workbook.worksheets.add("证据明细")', source)
        app = (ROOT / "app/Phase0App/main.m").read_text(encoding="utf-8")
        self.assertIn('@"导出报告"', app)
        self.assertIn('@"Excel 工作簿", @"PDF 报告", @"文字摘要"', app)
        self.assertIn('reportOptions[@"include_statistics"]', app)
        self.assertIn('reportOptions[@"include_evidence"]', app)
        self.assertIn('@"证据明细\\n"', app)

    def test_saved_analysis_loads_the_result_and_refreshes_only_new_messages(self):
        app = (ROOT / "app/Phase0App/main.m").read_text(encoding="utf-8")
        refresh = app.split("- (void)refreshSelectedAnalysis:", 1)[1].split(
            "- (NSString *)currentDBPath", 1
        )[0]
        self.assertIn('@"--refresh-saved", savedID', refresh)
        self.assertIn("BOOL unchanged", refresh)
        self.assertIn("applySavedAnalysis:object", refresh)
        self.assertIn("没有相关新消息", refresh)
        self.assertIn('@"--load-saved", savedID', app)
        self.assertIn('@selector(loadSelectedAnalysis:)', app)
        self.assertIn('@selector(deleteSelectedAnalysis:)', app)
        store = (ROOT / "agent_core/analysis_store.py").read_text(encoding="utf-8")
        self.assertIn("_account_corpus_watermark", store)
        self.assertIn("coalesce(max(timestamp),0) AS watermark", store)

    def test_review_fixes_keep_ui_work_off_the_main_thread_and_chat_out_of_temp_files(self):
        app = (ROOT / "app/Phase0App/main.m").read_text(encoding="utf-8")
        self.assertIn('dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0)', app)
        self.assertIn('@"正在构建完整历史分析语料…"', app)
        self.assertIn('@"--all-history"', app)
        self.assertNotIn('stringByAppendingPathComponent:[NSString stringWithFormat:@"wechat-leads-', app)
        self.assertIn('task.arguments = @[[resourcePath stringByAppendingPathComponent:@"Export/build_lead_workbook.mjs"], @"-", outputPath]', app)
        self.assertIn('rangeOfString:@"\\n\\n" options:NSBackwardsSearch', app)

    def test_task_specific_exports_do_not_reuse_customer_intent_columns(self):
        source = (ROOT / "scripts/build_lead_workbook.mjs").read_text(encoding="utf-8")
        self.assertIn('snapshot.task_type === "opportunity_analysis"', source)
        self.assertIn('"机会强度", "机会阶段"', source)
        self.assertIn('snapshot.task_type === "reengagement_analysis"', source)
        self.assertIn('"激活优先级", "触达建议"', source)
        self.assertIn('snapshot.task_type === "customer_risk"', source)
        self.assertIn('"风险严重度", "风险等级"', source)
        self.assertIn('[["置信度", "支持证据", "反例证据"]]', source)
        self.assertIn('"支持证据", "反例证据"', source)
        self.assertIn('detailDateColumn = "E"', source)
        self.assertIn('detailDateColumn = "I"', source)
        self.assertIn('detailDateColumn = "F"', source)
        self.assertIn('detailDateColumn = "H"', source)
        self.assertIn('format.numberFormat = "yyyy-mm-dd hh:mm"', source)
        self.assertIn('snapshotPath !== "-"', source)

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

    def test_first_install_prepares_chatlog_before_http_start(self):
        source = (ROOT / "app/Phase0App/main.m").read_text(encoding="utf-8")
        connect = source.split("- (void)connectWeChatData:", 1)[1].split(
            "- (NSArray<NSString *> *)commaSeparatedValues:", 1
        )[0]
        self.assertLess(
            connect.index('prepare-runtime'),
            connect.index('startChatlogServiceForAccount:selectedAccountID'),
        )

    def test_app_environment_always_exposes_required_macos_process_tools(self):
        source = (ROOT / "app/Phase0App/main.m").read_text(encoding="utf-8")
        environment = source.split("- (NSMutableDictionary *)agentEnvironment", 1)[1].split(
            "- (NSData *)drainPipe:", 1
        )[0]
        self.assertIn("/usr/sbin:/sbin", environment)
        self.assertNotIn("inheritedPath", environment)

    def test_account_selection_is_bound_through_http_and_sync(self):
        source = (ROOT / "app/Phase0App/main.m").read_text(encoding="utf-8")
        finish = source.split("- (void)finishWeChatSyncWithBinary:", 1)[1].split(
            "- (void)connectWeChatData:", 1
        )[0]
        connect = source.split("- (void)connectWeChatData:", 1)[1].split(
            "- (void)saveDeepSeekKey:", 1
        )[0]
        self.assertNotIn('agent_core.sync_cli", @"--db", self.currentDBPath, @"--chatlog-bin", chatlogBinary, @"accounts"', finish)
        self.assertIn("finishWeChatSyncWithBinary:chatlogBinary accountID:selectedAccountID", connect)
        self.assertIn('@[@"action", @"start-http", @"--history", accountID]', source)
        self.assertIn("chatlogReadAPIIsReadyForAccount:selectedAccountID", connect)
        self.assertIn("chatlogServiceAccountID", source)

    def test_account_picker_and_workspace_identify_bound_account(self):
        source = (ROOT / "app/Phase0App/main.m").read_text(encoding="utf-8")
        picker = source.split("- (NSString *)selectedAccountIDFromLines:", 1)[1].split(
            "- (void)finishWeChatSyncWithBinary:", 1
        )[0]
        self.assertIn('@"当前登录"', picker)
        self.assertIn('@"历史账号"', picker)
        self.assertIn('@"账号 %@ · 已同步 %@ 个对话，可以开始提问。"', source)

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

    def test_app_icon_master_is_rgba_and_uses_standard_canvas(self):
        icon = (ROOT / "app/Phase0App/WeChatCustomerAnalysisIcon.png").read_bytes()
        self.assertEqual(icon[:8], b"\x89PNG\r\n\x1a\n")
        width, height = struct.unpack(">II", icon[16:24])
        self.assertEqual((width, height), (1024, 1024))
        self.assertEqual(icon[25], 6)
        self.assertTrue((ROOT / "app/Phase0App/WeChatCustomerAnalysisArtwork.png").is_file())
        self.assertTrue((ROOT / "scripts/prepare_app_icon.m").is_file())

    def test_chatlog_license_and_release_cleanup_are_required(self):
        build = (ROOT / "scripts/build_phase0_app.sh").read_text(encoding="utf-8")
        dmg = (ROOT / "scripts/build_dmg.sh").read_text(encoding="utf-8")
        self.assertIn('cp chatlog/LICENSE "$RESOURCES_DIR/Chatlog/LICENSE"', build)
        self.assertIn(
            'test -f "$MOUNT_DIR/WeChatSalesAgent.app/Contents/Resources/Chatlog/LICENSE"',
            dmg,
        )
        self.assertIn(
            'cmp app/Phase0App/WeChatCustomerAnalysis.icns "$MOUNT_DIR/WeChatSalesAgent.app/Contents/Resources/WeChatCustomerAnalysis.icns"',
            dmg,
        )
        self.assertIn('rm -rf "$APP_DIR"', dmg)
        self.assertLess(
            dmg.index('mv -f "$DMG_CANDIDATE" "$DMG_PATH"'), dmg.index("SHA256=")
        )
        self.assertNotIn('rm -f "$DMG_PATH"', dmg)

    def test_workbook_rejects_every_scanned_formula_error(self):
        source = (ROOT / "scripts/build_lead_workbook.mjs").read_text(encoding="utf-8")
        self.assertIn('["#REF!", "#DIV/0!", "#VALUE!", "#NAME?", "#N/A", "#NUM!", "#NULL!", "#SPILL!", "#CALC!"]', source)
        self.assertIn("formulaErrors.some", source)

    def test_phase4_negative_case_uses_isolated_fixture(self):
        validator = (ROOT / "scripts/phase4_validate.sh").read_text(encoding="utf-8")
        self.assertIn("missing.sqlite3", validator)
        self.assertNotIn("wxid_3prysbeqgvci22_9f8d", validator)

    def test_native_pages_are_reused_and_refresh_without_clearing_visible_data(self):
        source = (ROOT / "app/Phase0App/main.m").read_text(encoding="utf-8")
        self.assertIn("@property NSView *customerRootView;", source)
        self.assertIn("@property NSView *dashboardRootView;", source)
        self.assertIn("@property NSView *messageSearchRootView;", source)
        dashboard = source.split("- (void)showAnalyticsDashboardView", 1)[1].split(
            "- (void)openAnalyticsDashboard", 1
        )[0]
        search = source.split("- (void)showMessageSearchView", 1)[1].split(
            "- (void)runMessageSearch", 1
        )[0]
        customer = source.split("- (void)showCustomerWorkspace", 1)[1].split(
            "- (void)renderDashboardGroupCards", 1
        )[0]
        self.assertIn("if (self.dashboardRootView)", dashboard)
        self.assertIn("if (self.messageSearchRootView)", search)
        self.assertNotIn("self.messageSearchResults = @[]", search)
        self.assertIn("self.window.contentView = self.customerRootView", customer)
        self.assertNotIn("rebuildWorkspaceWithMessage", customer)
        self.assertIn("dispatch_get_global_queue", source.split("- (void)loadAnalyticsDashboard", 1)[1].split("- (void)generateDashboardSummary", 1)[0])
        self.assertIn("dispatch_get_global_queue", source.split("- (void)loadMessageSearchSessions", 1)[1].split("- (void)showMessageSearchView", 1)[0])
        self.assertEqual(source.count("runBackgroundAgentCommand:"), 4)
        self.assertNotIn(
            "runAgentCommand:@[@\"-m\", @\"agent_core.message_search_cli\"",
            source,
        )
        self.assertIn("navigationRevision == self.navigationRevision", source)
        self.assertIn("ownedService == self.chatlogServiceTask", source)
        self.assertEqual(source.count("NSTextAlignmentRight);\n    ApplyAgentMessageBubble"), 2)
        self.assertEqual(source.count(", 34, NSTextAlignmentRight);"), 2)

    def test_app_exposes_authenticated_loopback_api_and_stops_it_on_exit(self):
        source = (ROOT / "app/Phase0App/main.m").read_text(encoding="utf-8")
        self.assertIn('buttonWithTitle:@"Agent 接入"', source)
        self.assertIn('@"--host", @"127.0.0.1", @"--port", @"8765"', source)
        self.assertIn('@"-m", @"agent_core.local_api", @"token"', source)
        self.assertIn("[self startIntegrationServices]", source)
        self.assertIn("- (BOOL)prepareOwnedLocalAPIPort", source)
        self.assertIn('@"-m agent_core.local_api serve"', source)
        self.assertIn('[command containsString:self.currentDBPath]', source)
        self.assertIn('NSLocalizedDescriptionKey: @"8765 端口被其他程序占用"', source)
        self.assertIn("if (self.localAPIServiceTask.running)", source)
        self.assertTrue((ROOT / "agent_core/local_api_openapi.json").is_file())
        self.assertTrue((ROOT / "agent_core/local_mcp.py").is_file())
        self.assertTrue((ROOT / "docs/LOCAL_API.md").is_file())
        self.assertTrue((ROOT / "docs/LOCAL_MCP.md").is_file())
        self.assertIn('integrations/workbuddy "$RESOURCES_DIR/Integrations/WorkBuddy"', (ROOT / "scripts/build_phase0_app.sh").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
