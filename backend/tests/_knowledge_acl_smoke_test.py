import time

import jwt

from backend.config import settings
from backend.services.knowledge_acl import load_fixtures
from backend.services.knowledge_retrieve_testharness import ask_knowledge_testharness


def tok(sub: str) -> str:
    payload = {"sub": sub, "iat": int(time.time()), "exp": int(time.time()) + 3600}
    return jwt.encode(payload, settings.auth_secret, algorithm="HS256")


def main() -> None:
    fixtures = load_fixtures()
    print("tenant_id:", fixtures.get("tenant_id"))

    admin_res = ask_knowledge_testharness(tok("admin"), "财务审核 T+2 是什么？")
    print("admin denied:", admin_res.get("denied"), "citations:", admin_res.get("citations"))

    bob_token = tok("bob")
    finance_cid = "c_finance_public_1"
    res2 = ask_knowledge_testharness(bob_token, "财务审核 T+2 是什么？", selected_collection_ids=[finance_cid])
    print("bob select finance denied:", res2.get("denied"), "reason:", res2.get("deny_reason"))

    res3 = ask_knowledge_testharness(bob_token, "公司制度 报销 流程 怎么走？")
    print("bob company denied:", res3.get("denied"), "citations:", res3.get("citations"))

    proj_table = "t_project_profit_1"
    res4 = ask_knowledge_testharness(
        bob_token, "项目核算 本年累计净利润 是多少？", selected_table_ids=[proj_table]
    )
    print("bob select proj table denied:", res4.get("denied"), "reason:", res4.get("deny_reason"))

    alice_res = ask_knowledge_testharness(tok("alice"), "项目核算 本年累计净利润 是多少？")
    print("alice denied:", alice_res.get("denied"), "reply:", alice_res.get("reply"))
    print("alice citations:", alice_res.get("citations"))


if __name__ == "__main__":
    main()

