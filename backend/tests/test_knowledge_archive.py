"""场景知识库版本化导出与归档号分群关联验收测试。

覆盖题述两条主线：
1. v1 已发布 / v2 仅草稿交错时，导出只能读到完整已发布版本；v2 发布后旧归档
   仍可重下原文件，并可凭旧归档号按旧版字段重做分群关联。
2. M1(age)/M2(income) 两次发布各自导出，包内规则、字段、来源严格同版；
   聚类配置 A(age)/B(income)/C(age) 下，两份归档分别关联到正确的分群集合。

可直接 `python tests/test_knowledge_archive.py` 运行，也兼容 pytest。
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services import service_for
from app.services.knowledge_archive import knowledge_archive_service
from app.store import store


# ── 测试隔离工具：记录本用例新增的仓库行与归档，结束后清理 ──
class Isolation:
    def __init__(self) -> None:
        self.created: dict[str, list[int]] = {}
        self.archives: list[str] = []

    def add_mining(self, code: str, topic: str, insight: str, segment: str) -> int:
        rows = store.rows("mining_result")
        new_id = max((int(r["id"]) for r in rows), default=0) + 1
        rows.append({
            "id": new_id, "status": "已采纳", "pending": False, "abnormal": False,
            "结果编号": code, "分析主题": topic, "算法类型": "kmeans",
            "洞察摘要": insight, "关键分群": segment, "置信度": "0.9",
            "结果文件": f"{code}.json", "结果版本": "v1",
        })
        self.created.setdefault("mining_result", []).append(new_id)
        return new_id

    def add_cluster(self, code: str, features: str) -> int:
        rows = store.rows("cluster_config")
        new_id = max((int(r["id"]) for r in rows), default=0) + 1
        rows.append({
            "id": new_id, "status": "已完成", "pending": False, "abnormal": False,
            "配置编号": code, "特征集": features, "算法类型": "kmeans",
            "目标簇数": "3", "距离度量": "euclidean", "初始化方式": "kmeans++",
            "收敛阈值": "0.001", "配置版本": "v1",
        })
        self.created.setdefault("cluster_config", []).append(new_id)
        return new_id

    def track_archive(self, archive_no: str) -> str:
        self.archives.append(archive_no)
        return archive_no

    def cleanup(self) -> None:
        for module, ids in self.created.items():
            rows = store.rows(module)
            rows[:] = [r for r in rows if int(r["id"]) not in ids]
        for archive_no in self.archives:
            knowledge_archive_service._archives.pop(archive_no, None)
        # 清理本用例登记的导出任务
        export_rows = store.rows("data_export")
        export_rows[:] = [r for r in export_rows if not str(r.get("任务编号", "")).startswith("KBEX-")]


def _ids(link_result: dict) -> set[int]:
    return {c["cluster_id"] for c in link_result.get("related_clusters", [])}


# ── 主线1：v1 已发布、v2 仅草稿交错，导出只读完整已发布版本 ──
def test_draft_v2_does_not_mix_into_v1_export():
    iso = Isolation()
    try:
        label_svc = service_for("scenario_label")
        export_svc = service_for("data_export")

        m1 = iso.add_mining("M1", "高价值客群", "rule_v1_age", "age")
        m2 = iso.add_mining("M2", "收入偏好客群", "rule_v2_income", "income")
        cluster_a = iso.add_cluster("CLUS-A", "age")
        cluster_b = iso.add_cluster("CLUS-B", "income")

        # M1 转标注（使用 age）并发布 v1
        conv = label_svc.convert_mining_result_to_label(m1, fields="age")
        assert conv["ok"], conv
        label_id = conv["label_id"]
        pub1 = label_svc.publish_version(label_id)
        assert pub1["ok"] and pub1["version"]["version"] == "v1"

        # 导出 v1，登记归档号 A1
        ex1 = export_svc.export_scenario_knowledge_base(label_id)
        assert ex1["ok"], ex1
        a1 = iso.track_archive(ex1["archive_no"])
        pkt1 = ex1["packet"]
        assert pkt1["fields"] == ["age"]
        assert pkt1["rule_text"] == "rule_v1_age"
        assert pkt1["source"]["mining_result_id"] == m1
        assert pkt1["source"]["mining_result_code"] == "M1"

        # v2 只保存草稿字段（income + 来源 M2），不发布
        draft = label_svc.save_draft_fields(label_id, fields="income", mining_result_id=m2)
        assert draft["ok"] and draft["published_versions"] == 1

        # 再次导出：仍只能读到完整的旧发布版 v1，绝不能把草稿新字段拼进来
        ex1b = export_svc.export_scenario_knowledge_base(label_id)
        assert ex1b["ok"], ex1b
        iso.track_archive(ex1b["archive_no"])
        assert ex1b["packet"]["version"] == "v1"
        assert ex1b["packet"]["fields"] == ["age"]
        assert ex1b["packet"]["source"]["mining_result_code"] == "M1"

        # 旧归档 A1 仍可重下原文件
        back1 = export_svc.redownload_archive(a1)
        assert back1["ok"], back1
        assert "rule_v1_age" in back1["content"] and "age" in back1["content"]

        # v2 发布后再导出，得到完整 v2 包
        pub2 = label_svc.publish_version(label_id)
        assert pub2["ok"] and pub2["version"]["version"] == "v2"
        ex2 = export_svc.export_scenario_knowledge_base(label_id)
        assert ex2["ok"], ex2
        a2 = iso.track_archive(ex2["archive_no"])
        pkt2 = ex2["packet"]
        assert pkt2["fields"] == ["income"]
        assert pkt2["rule_text"] == "rule_v2_income"
        assert pkt2["source"]["mining_result_code"] == "M2"

        # 旧归档重下仍是 v1 原文件，未被 v2 覆盖
        back1_again = export_svc.redownload_archive(a1)
        assert back1_again["ok"]
        old = back1_again["packet"]
        assert old["version"] == "v1" and old["fields"] == ["age"]
        assert old["rule_text"] == "rule_v1_age" and old["source"]["mining_result_code"] == "M1"

        # 旧归档号直接用于旧版规则的分群关联：只匹配 age 的 A
        link1 = label_svc.link_archive_to_clusters(a1)
        assert link1["ok"] and link1["linkable"]
        assert _ids(link1) == {cluster_a}
        # 新归档只匹配 income 的 B
        link2 = label_svc.link_archive_to_clusters(a2)
        assert _ids(link2) == {cluster_b}

        # 新增第二个匹配 age 的聚类配置 C，旧包重做关联应包含 A 和 C
        cluster_c = iso.add_cluster("CLUS-C", "age")
        link1_re = label_svc.link_archive_to_clusters(a1)
        assert _ids(link1_re) == {cluster_a, cluster_c}
        # v2 包不受影响，仍只含 B
        assert _ids(label_svc.link_archive_to_clusters(a2)) == {cluster_b}
    finally:
        iso.cleanup()


# ── 主线2：两份独立知识库包各自保留 M1/M2 的来源、规则和字段 ──
def test_two_packages_keep_own_version_contents():
    iso = Isolation()
    try:
        label_svc = service_for("scenario_label")
        export_svc = service_for("data_export")

        m1 = iso.add_mining("M1", "年龄主题", "rule_from_m1", "age")
        m2 = iso.add_mining("M2", "收入主题", "rule_from_m2", "income")
        cluster_a = iso.add_cluster("CLUS-A2", "age")
        cluster_b = iso.add_cluster("CLUS-B2", "income")

        # 标签 L1：M1 + age，发布 v1 并导出
        c1 = label_svc.convert_mining_result_to_label(m1, fields="age")
        label1 = c1["label_id"]
        assert label_svc.publish_version(label1)["ok"]
        e1 = export_svc.export_scenario_knowledge_base(label1)
        assert e1["ok"], e1
        arc1 = iso.track_archive(e1["archive_no"])

        # 标签 L2：M2 + income，发布 v1 并导出（与 L1 的导出并发语义互不干扰）
        c2 = label_svc.convert_mining_result_to_label(m2, fields="income")
        label2 = c2["label_id"]
        assert label_svc.publish_version(label2)["ok"]
        e2 = export_svc.export_scenario_knowledge_base(label2)
        assert e2["ok"], e2
        arc2 = iso.track_archive(e2["archive_no"])

        # 包内规则、字段、来源必须同属一个版本，禁止跨版本拼装
        p1, p2 = e1["packet"], e2["packet"]
        assert (p1["rule_text"], p1["fields"], p1["source"]["mining_result_code"]) == \
            ("rule_from_m1", ["age"], "M1")
        assert (p2["rule_text"], p2["fields"], p2["source"]["mining_result_code"]) == \
            ("rule_from_m2", ["income"], "M2")

        # 重下两份包，内容各自保留
        d1 = export_svc.redownload_archive(arc1)
        d2 = export_svc.redownload_archive(arc2)
        assert d1["packet"]["source"]["mining_result_code"] == "M1"
        assert d2["packet"]["source"]["mining_result_code"] == "M2"

        # 分别用归档号关联，分群只包含 A / B
        assert _ids(label_svc.link_archive_to_clusters(arc1)) == {cluster_a}
        assert _ids(label_svc.link_archive_to_clusters(arc2)) == {cluster_b}

        # 数据导出管理已登记两次导出，且可按任务重下
        listing = export_svc.list_knowledge_exports()
        assert listing["total"] == 2
        task_id = listing["items"][0]["export_id"]
        via_task = export_svc.redownload_task_archive(task_id)
        assert via_task["ok"] and via_task["archive_no"] == listing["items"][0]["archive_no"]
    finally:
        iso.cleanup()


# ── 异常路径：无发布版本、归档号不存在、文件不完整、未登记不可重下 ──
def test_invalid_archives_and_unpublished_export():
    iso = Isolation()
    try:
        label_svc = service_for("scenario_label")
        export_svc = service_for("data_export")

        m1 = iso.add_mining("M1X", "主题X", "rule_x", "age")
        conv = label_svc.convert_mining_result_to_label(m1, fields="age")
        label_id = conv["label_id"]

        # 只有草稿、没有发布版本：禁止导出知识库包
        blocked = knowledge_archive_service.export_knowledge_base(label_id)
        assert not blocked["ok"] and "已发布版本" in blocked["reason"]

        assert label_svc.publish_version(label_id)["ok"]
        ok_export = export_svc.export_scenario_knowledge_base(label_id)
        archive_no = iso.track_archive(ok_export["archive_no"])

        # 归档号不存在：不可关联
        missing = label_svc.link_archive_to_clusters("KB-9999-V99-9999")
        assert not missing["ok"] and not missing["linkable"]
        assert missing["related_clusters"] == []

        # 文件不完整：不可关联、不可下载
        knowledge_archive_service._archives[archive_no]["fields"] = []
        broken_link = label_svc.link_archive_to_clusters(archive_no)
        assert not broken_link["ok"] and not broken_link["linkable"]
        broken_dl = export_svc.redownload_archive(archive_no)
        assert not broken_dl["ok"] and "不完整" in broken_dl["reason"]

        # 未在导出管理登记的归档号不能通过导出管理重下
        ghost = knowledge_archive_service.export_knowledge_base(label_id)
        assert ghost["ok"]
        ghost_no = iso.track_archive(ghost["archive_no"])
        unregistered = export_svc.redownload_archive(ghost_no)
        assert not unregistered["ok"] and "未在数据导出管理登记" in unregistered["reason"]
    finally:
        iso.cleanup()


if __name__ == "__main__":
    tests = [
        test_draft_v2_does_not_mix_into_v1_export,
        test_two_packages_keep_own_version_contents,
        test_invalid_archives_and_unpublished_export,
    ]
    passed = failed = 0
    for test in tests:
        try:
            test()
            print(f"[PASS] {test.__name__}")
            passed += 1
        except Exception as exc:  # noqa: BLE001
            print(f"[FAIL] {test.__name__}: {exc}")
            failed += 1
    print(f"\n总测试: {len(tests)}, 通过: {passed}, 失败: {failed}")
    if failed:
        sys.exit(1)
