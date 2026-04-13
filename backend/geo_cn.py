"""
中国注册地 / 省市字段推断。

- 导出 entities.csv、bundle 入库时：用 normalize_geo 尽量从 reg_location 补全 city（及省）。
- 读侧（分析统计等）：用 city_display_label / province_display_label 兜底。
"""
from __future__ import annotations

import re
from typing import Optional

# 先匹配长名称，避免「黑龙江」被「黑」误伤
PROVINCE_NAMES: tuple[str, ...] = (
    "内蒙古",
    "黑龙江",
    "新疆",
    "宁夏",
    "广西",
    "西藏",
    "北京",
    "天津",
    "上海",
    "重庆",
    "河北",
    "山西",
    "辽宁",
    "吉林",
    "江苏",
    "浙江",
    "安徽",
    "福建",
    "江西",
    "山东",
    "河南",
    "湖北",
    "湖南",
    "广东",
    "海南",
    "四川",
    "贵州",
    "云南",
    "陕西",
    "甘肃",
    "青海",
    "香港",
    "澳门",
    "台湾",
)

# 注册地无「XX省」前缀、常以市名起笔时，按前缀长度降序匹配
CITY_PREFIX_TO_FULL: dict[str, str] = {
    "乌鲁木齐": "乌鲁木齐市",
    "呼和浩特": "呼和浩特市",
    "石家庄": "石家庄市",
    "哈尔滨": "哈尔滨市",
    "连云港": "连云港市",
    "张家界": "张家界市",
    "马鞍山": "马鞍山市",
    "厦门": "厦门市",
    "深圳": "深圳市",
    "青岛": "青岛市",
    "大连": "大连市",
    "宁波": "宁波市",
    "苏州": "苏州市",
    "无锡": "无锡市",
    "佛山": "佛山市",
    "东莞": "东莞市",
    "珠海": "珠海市",
    "海口": "海口市",
    "三亚": "三亚市",
    "福州": "福州市",
    "温州": "温州市",
    "唐山": "唐山市",
    "徐州": "徐州市",
    "常州": "常州市",
    "绍兴": "绍兴市",
    "嘉兴": "嘉兴市",
    "台州": "台州市",
    "金华": "金华市",
    "惠州": "惠州市",
    "中山": "中山市",
    "江门": "江门市",
    "兰州": "兰州市",
    "贵阳": "贵阳市",
    "昆明": "昆明市",
    "南昌": "南昌市",
    "长沙": "长沙市",
    "郑州": "郑州市",
    "济南": "济南市",
    "太原": "太原市",
    "沈阳": "沈阳市",
    "长春": "长春市",
    "合肥": "合肥市",
    "南宁": "南宁市",
    "拉萨": "拉萨市",
    "西宁": "西宁市",
    "银川": "银川市",
    "成都": "成都市",
    "武汉": "武汉市",
    "西安": "西安市",
    "南京": "南京市",
    "杭州": "杭州市",
    "广州": "广州市",
    "天津": "天津市",
}

_MUNICIPALITIES_FULL = ("北京市", "天津市", "上海市", "重庆市")
_DIRECT_PROV = frozenset({"北京", "上海", "天津", "重庆"})
_SORTED_PREFIXES = tuple(sorted(CITY_PREFIX_TO_FULL.keys(), key=len, reverse=True))


def normalize_geo(
    reg_location: Optional[str],
    api_city: Optional[str],
    api_district: Optional[str],
    *,
    hint_province: Optional[str] = None,
) -> tuple[str, str, str]:
    """
    从注册地 + 天眼 city/district 得到 (province, city, district)。
    目标：凡 reg_location 非空，尽量写出非空的 city（与导出 CSV / 入库一致）。
    """
    reg = (reg_location or "").strip()
    city_api = (api_city or "").strip()
    dist = (api_district or "").strip()
    text = f"{reg}{city_api}{dist}"

    prov = ""
    for p in PROVINCE_NAMES:
        if p in text:
            prov = p
            break
    if not prov:
        hp = (hint_province or "").strip()
        if hp:
            prov = hp

    city_out = city_api
    if city_out:
        return prov, city_out, dist

    if not reg:
        return prov, city_out, dist

    for muni in _MUNICIPALITIES_FULL:
        if muni in reg:
            city_out = muni
            break
    if not city_out and prov in _DIRECT_PROV:
        city_out = f"{prov}市"
    if not city_out:
        m = re.search(r"(?:省|自治区)([^省]{1,18}?市)", reg)
        if m:
            city_out = m.group(1).strip()
    if not city_out:
        m2 = re.match(r"^([^省]+?市(?:[^省市区县]{0,10})?)", reg)
        if m2:
            seg = m2.group(1).strip()
            if "省" not in seg and len(seg) <= 22 and "自治区" not in seg:
                city_out = seg
    if not city_out:
        for pref in _SORTED_PREFIXES:
            if reg.startswith(pref):
                city_out = CITY_PREFIX_TO_FULL[pref]
                break
    if not city_out and "市" in reg:
        for m in re.finditer(r"([\u4e00-\u9fff]{2,15}市)", reg):
            s = m.group(1)
            if "省" in s or "自治区" in s:
                continue
            city_out = s
            break

    return prov, city_out, dist


def geo_hint_from_company_name(company_name: Optional[str]) -> tuple[str, str]:
    """
    工商库缺省时，从公司名抽取弱提示（直辖市开头、括号地名）。
    例：「北京比特漫步科技有限公司」「新美星空（北京）数字科技有限公司」。
    """
    n = (company_name or "").strip()
    if not n:
        return "", ""
    for p in _DIRECT_PROV:
        if n.startswith(p):
            return p, f"{p}市"
    m = re.search(r"[（(](北京|上海|天津|重庆)[）)]", n)
    if m:
        p = m.group(1)
        return p, f"{p}市"
    return "", ""


def city_display_label(
    city: Optional[str],
    reg_location: Optional[str],
    province: Optional[str],
    *,
    company_name: Optional[str] = None,
) -> str:
    """读侧兜底：列上已有 city 则直接用，否则按注册地推断，再尝试公司名弱提示。"""
    c = (city or "").strip()
    if c:
        return c
    _, infer_c, _ = normalize_geo(reg_location, "", "", hint_province=province)
    if (infer_c or "").strip():
        return (infer_c or "").strip()
    _, city_nm = geo_hint_from_company_name(company_name)
    return (city_nm or "").strip()


def province_display_label(
    province: Optional[str],
    reg_location: Optional[str],
    *,
    company_name: Optional[str] = None,
) -> str:
    p = (province or "").strip()
    if p:
        return p
    infer_p, _, _ = normalize_geo(reg_location or "", "", "")
    if (infer_p or "").strip():
        return (infer_p or "").strip()
    prov_nm, _ = geo_hint_from_company_name(company_name)
    return (prov_nm or "").strip()
