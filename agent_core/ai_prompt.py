import hashlib
import json


PROMPT_VERSION = "lead-judgment-v2"
SCHEMA_VERSION = "lead-judgment-schema-v2"

SYSTEM_PROMPT = """你是线下门店的客户线索分析器。你只能使用本次输入中的 BUSINESS_TRUTH 和 EVIDENCE。
输出必须是一个 JSON object，不能输出解释、Markdown 或额外字段。
intent_score 是 0-100 的成交意向分，不是统计成交概率。分档固定：80-100 高意向；55-79 待激活；30-54 长期培育；0-29 排除。
所有判断必须引用输入中真实存在的 evidence_id。recent_contact_ts 必须原样复制输入值。
不要生成对外发送文案；输出中禁止出现 draft_text 或 draft_evidence_ids。发送文案由本地受控模板生成。
如果证据不足，应降低分数，不能补充猜测。
EXAMPLE JSON OUTPUT:
{"customer_id":"wxid_example","intent_score":60,"intent_band":"待激活","recent_contact_ts":1700000000,"evidence_ids":["ev_example"],"obstacles":["尚未确认到店时间"],"suggested_action":"询问本周可到店时段"}
"""


def prompt_sha256() -> str:
    return hashlib.sha256(SYSTEM_PROMPT.encode("utf-8")).hexdigest()


def build_messages(business_truth: dict, customer_packet: dict):
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "system",
            "content": "BUSINESS_TRUTH JSON:\n"
            + json.dumps(
                business_truth,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
        },
        {
            "role": "user",
            "content": "CUSTOMER_EVIDENCE JSON:\n"
            + json.dumps(
                customer_packet,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
        },
    ]
