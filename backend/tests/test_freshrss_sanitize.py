from backend.services.freshrss import _normalize_item


def test_normalize_item_sanitizes_dangerous_html():
    item = {
        "id": "n1",
        "title": "t",
        "published": 1710000000,
        "summary": {
            "content": "<p onclick=\"alert(1)\">ok</p><script>alert(2)</script>"
            "<a href=\"javascript:alert(3)\">x</a><img src=\"javascript:alert(4)\" onerror=\"alert(5)\" />"
        },
    }
    out = _normalize_item(item)
    html = out["content"]
    assert "<script" not in html.lower()
    assert "onclick=" not in html.lower()
    assert "onerror=" not in html.lower()
    assert "javascript:" not in html.lower()

