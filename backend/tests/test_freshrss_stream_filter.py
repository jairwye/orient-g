"""FreshRSS 按 label 过滤：服务端可能返回混排 reading-list，客户端必须严格按 categories 归类。"""

from backend.services.freshrss import _item_belongs_to_stream, _select_items_for_label


def _item(item_id: str, labels: list[str]) -> dict:
    cats = [f"user/-/state/com.google/reading-list"]
    cats.extend(f"user/-/label/{lb}" for lb in labels)
    cats.append("user/-/state/org.freshrss/main")
    return {
        "id": item_id,
        "title": item_id,
        "categories": cats,
        "origin": {"streamId": "feed/1", "title": "src"},
        "published": 1710000000,
    }


def test_item_belongs_to_stream_matches_string_categories():
    stream_id = "user/-/label/游戏观点"
    assert _item_belongs_to_stream(_item("a", ["游戏观点"]), stream_id, "游戏观点")
    assert not _item_belongs_to_stream(_item("b", ["游戏新闻"]), stream_id, "游戏观点")
    assert not _item_belongs_to_stream(_item("c", ["AI新闻"]), stream_id, "游戏观点")


def test_item_belongs_to_stream_matches_dict_categories():
    stream_id = "user/-/label/游戏观点"
    item = {
        "id": "d",
        "categories": [
            {"id": "user/-/state/com.google/reading-list", "label": "reading-list"},
            {"id": "user/-/label/游戏观点", "label": "游戏观点"},
        ],
    }
    assert _item_belongs_to_stream(item, stream_id, "游戏观点")


def test_select_items_keeps_only_matching_label_when_mixed_page():
    """FreshRSS label stream 可能返回全站混排；不得把其他类条目塞进目标类。"""
    items = [
        _item("news1", ["游戏新闻"]),
        _item("ai1", ["AI新闻"]),
        _item("view1", ["游戏观点"]),
        _item("news2", ["游戏新闻"]),
    ]
    selected = _select_items_for_label(items, "user/-/label/游戏观点", "游戏观点")
    assert [it["id"] for it in selected] == ["view1"]


def test_select_items_returns_empty_when_page_has_labels_but_none_match():
    """有 categories 元数据但本页无目标 label 时，应返回空，禁止回退整页混排。"""
    items = [
        _item("news1", ["游戏新闻"]),
        _item("ai1", ["AI新闻"]),
    ]
    selected = _select_items_for_label(items, "user/-/label/游戏观点", "游戏观点")
    assert selected == []


def test_select_items_trusts_stream_when_no_category_metadata():
    """完全没有 categories/directStreamIds 时，信任 stream/contents 已按 label 过滤。"""
    items = [
        {"id": "x1", "title": "t", "origin": {"streamId": "feed/9"}},
        {"id": "x2", "title": "t2"},
    ]
    selected = _select_items_for_label(items, "user/-/label/游戏观点", "游戏观点")
    assert [it["id"] for it in selected] == ["x1", "x2"]
