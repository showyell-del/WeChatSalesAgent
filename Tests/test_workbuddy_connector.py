import json
import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONNECTOR = ROOT / "integrations" / "workbuddy"
EXPECTED_TOOLS = {
    "search_wechat_messages",
    "list_conversations",
    "get_dashboard",
    "analyze_conversation",
    "get_analysis_result",
}


class WorkBuddyConnectorTest(unittest.TestCase):
    def test_official_connector_bundle_shape_and_metadata(self):
        required = {
            "connector-meta.json",
            "mcp.json",
            "icon.svg",
            "skills/wechat-analysis/SKILL.md",
        }
        for relative_path in required:
            self.assertTrue((CONNECTOR / relative_path).is_file(), relative_path)

        metadata = json.loads((CONNECTOR / "connector-meta.json").read_text(encoding="utf-8"))
        self.assertEqual(metadata["type"], "mcp")
        self.assertEqual(metadata["source"], "wechat-customer-analysis")
        self.assertRegex(metadata["source"], r"^[a-z0-9-]+$")
        self.assertRegex(metadata["version"], r"^\d+\.\d+\.\d+$")
        self.assertGreaterEqual(tuple(map(int, metadata["minWorkbuddyVersion"].split("."))), (4, 24, 0))
        for key in ("name", "name_zh", "name_en", "description", "description_zh", "description_en"):
            self.assertIsInstance(metadata[key], str)
            self.assertTrue(metadata[key].strip())
        self.assertGreaterEqual(len(metadata["examples_zh"]), 2)
        self.assertLessEqual(len(metadata["examples_zh"]), 5)
        self.assertGreaterEqual(len(metadata["examples_en"]), 2)
        self.assertLessEqual(len(metadata["examples_en"]), 5)

    def test_mcp_config_declares_one_local_stdio_server(self):
        config = json.loads((CONNECTOR / "mcp.json").read_text(encoding="utf-8"))
        self.assertEqual(set(config), {"mcpServers"})
        self.assertEqual(len(config["mcpServers"]), 1)
        server = config["mcpServers"]["wechat-customer-analysis"]
        self.assertEqual(server, {
            "type": "stdio",
            "command": "/Applications/WeChatSalesAgent.app/Contents/Resources/PythonRuntime/bin/python3",
            "args": ["-m", "agent_core.local_mcp"],
            "env": {
                "PYTHONHOME": "/Applications/WeChatSalesAgent.app/Contents/Resources/PythonRuntime",
                "PYTHONPATH": "/Applications/WeChatSalesAgent.app/Contents/Resources/Python",
            },
            "timeout": 30000,
        })

    def test_skill_frontmatter_and_tool_contract_are_complete(self):
        content = (CONNECTOR / "skills" / "wechat-analysis" / "SKILL.md").read_text(encoding="utf-8")
        match = re.match(r"\A---\n(.*?)\n---\n", content, flags=re.DOTALL)
        self.assertIsNotNone(match)
        frontmatter = {}
        for line in match.group(1).splitlines():
            key, value = line.split(":", 1)
            frontmatter[key.strip()] = value.strip()
        for key in ("description", "description_zh", "description_en", "version", "author"):
            self.assertTrue(frontmatter.get(key), key)
        allowed_tools = {item.strip() for item in frontmatter["allowed-tools"].split(",")}
        self.assertEqual(allowed_tools, EXPECTED_TOOLS)
        for tool in EXPECTED_TOOLS:
            self.assertIn("`%s`" % tool, content)
        self.assertIn("ACCOUNT_MISMATCH", content)
        self.assertIn("pagination.next_cursor", content)
        self.assertIn("不得缩写、翻译或只传关键词", content)
        self.assertIn("不展示工具名、operation ID、轮询过程、失败重试、调试经验", content)
        self.assertIn("不得自动创建 Skill、记忆或规则文件", content)
        self.assertIn("先调用一次 `list_conversations`", content)
        self.assertIn("每 10 秒查询一次", content)

    def test_icon_is_a_parseable_square_svg(self):
        root = ET.parse(CONNECTOR / "icon.svg").getroot()
        self.assertEqual(root.tag, "{http://www.w3.org/2000/svg}svg")
        self.assertEqual(root.attrib["viewBox"], "0 0 512 512")

    def test_bundle_contains_no_embedded_secret(self):
        combined = "\n".join(
            path.read_text(encoding="utf-8")
            for path in CONNECTOR.rglob("*")
            if path.is_file()
        )
        secret_patterns = (
            r"sk-[A-Za-z0-9]{16,}",
            r"Bearer\s+[A-Za-z0-9._-]{16,}",
            r"ghp_[A-Za-z0-9]{20,}",
        )
        for pattern in secret_patterns:
            self.assertIsNone(re.search(pattern, combined), pattern)


if __name__ == "__main__":
    unittest.main()
