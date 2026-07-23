import re
from typing import Dict, Iterable, List


MOBILE = re.compile(r"(?<!\d)(?:\+?86[- ]?)?(1[3-9]\d{9})(?!\d)")
LANDLINE = re.compile(r"(?<!\d)(0\d{2,3}[- ]?\d{7,8})(?!\d)")
WECHAT_ID = re.compile(r"(?:微信(?:号)?|wx|vx|v信)\s*(?:号|是|[:：])\s*([A-Za-z][A-Za-z0-9_-]{5,19})|加我\s+([A-Za-z][A-Za-z0-9_-]{5,19})", re.IGNORECASE)
AGE = re.compile(r"(?<!\d)([3-9]|[1-7]\d)\s*岁")
GRADE = re.compile(r"(幼儿园|学前班|小学[一二三四五六]年级|[一二三四五六]年级|初[一二三]|高[一二三]|大[一二三四])")
BUDGET = re.compile(r"(?:预算|价位|能接受|大概)\D{0,8}(\d{2,6})\s*(?:元|块)?|(?<!\d)(\d{2,6})\s*(?:元|块)(?!\d)")
KNOWN_REGION_NAMES = (
    "北京|上海|天津|重庆|江苏|浙江|安徽|福建|江西|山东|河南|湖北|湖南|广东|海南|四川|贵州|云南|陕西|甘肃|青海|台湾|"
    "内蒙古|广西|西藏|宁夏|新疆|香港|澳门|苏州|杭州|南京|无锡|常州|南通|扬州|镇江|昆山|太仓|常熟|张家港|"
    "广州|深圳|成都|武汉|西安|郑州|长沙|合肥|厦门|福州|青岛|济南|宁波|温州|嘉兴|绍兴|金华|台州|南昌|"
    "沈阳|大连|长春|哈尔滨|石家庄|太原|昆明|贵阳|南宁|海口|兰州|西宁|银川|乌鲁木齐|拉萨|呼和浩特|"
    "姑苏|吴中|相城|虎丘|吴江|工业园"
)
KNOWN_REGION = re.compile(r"((?:" + KNOWN_REGION_NAMES + r")(?:省|市|自治区|特别行政区|区|县|镇|街道)?)")
CONTEXT_REGION = re.compile(r"(?:住在|位于|地址(?:是|在)?|家在|店在|公司在|学校在|来自)\s*([\u4e00-\u9fff]{2,10}(?:省|市|区|县|镇|街道|小区))")

NEED_TERMS = ("街舞", "爵士舞", "hiphop", "hip-hop", "少儿舞蹈", "成人舞蹈", "舞蹈体验", "体验街舞", "试听舞蹈", "学舞", "舞蹈课", "舞蹈班")
TIME_SIGNAL = re.compile(r"(?:周[一二三四五六日天]|周末|工作日|晚上|白天|上午|下午|放学后?|下班后?|寒假|暑假|\d{1,2}[点时])[^。！？\n]{0,16}(?:有空|方便|可以|能|体验|试听|上课|过来|到店)|(?:有空|方便|可以|能)[^。！？\n]{0,16}(?:周[一二三四五六日天]|周末|工作日|晚上|白天|上午|下午|放学后?|下班后?|寒假|暑假|\d{1,2}[点时])")
OBSTACLE_TERMS = ("太贵", "没时间", "有点远", "考虑一下", "不方便上课", "时间冲突", "家长不同意", "先不报")


def _fact(field: str, value: str, evidence_id: str, extractor: str) -> Dict[str, str]:
    return {"field": field, "value": value.strip(), "evidence_id": evidence_id, "extractor": extractor}


def extract_facts(content: str, evidence_id: str) -> List[Dict[str, str]]:
    text = content.strip()
    facts = []
    seen = set()

    def add(field: str, value: str, extractor: str) -> None:
        key = (field, value.strip())
        if value.strip() and key not in seen:
            facts.append(_fact(field, value, evidence_id, extractor))
            seen.add(key)

    for value in MOBILE.findall(text):
        add("mobile", value, "mobile_regex_v1")
    for value in LANDLINE.findall(text):
        add("landline", value.replace(" ", ""), "landline_regex_v1")
    for match in WECHAT_ID.finditer(text):
        add("wechat_id", match.group(1) or match.group(2), "wechat_id_regex_v2")
    for value in AGE.findall(text):
        add("age", value, "age_regex_v1")
    for value in GRADE.findall(text):
        add("grade", value, "grade_regex_v1")
    for match in BUDGET.finditer(text):
        value = match.group(1) or match.group(2)
        add("budget_cny", value, "budget_regex_v1")
    for value in KNOWN_REGION.findall(text):
        add("region", value, "known_region_v3")
    for value in CONTEXT_REGION.findall(text):
        add("region", value, "context_region_v3")
    lowered = text.lower()
    if any(term in lowered for term in NEED_TERMS):
        add("explicit_need", text[:240], "dance_need_terms_v1")
    if TIME_SIGNAL.search(text):
        add("available_time", text[:240], "availability_pattern_v2")
    if any(term in text for term in OBSTACLE_TERMS):
        add("obstacle", text[:240], "obstacle_terms_v1")
    return facts
