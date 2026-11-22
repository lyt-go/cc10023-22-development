"""场景知识库归档服务：把已发布的场景版本固化为可下载、可回查的知识库包。

核心约束：
- 知识库包只能读取完整的、已生效（已发布）的场景版本；草稿字段永不入包。
- 规则文本、字段组合、来源挖掘结果编号取自同一份不可变发布快照，
  任何导出都不会把新规则与旧字段（或新字段与旧来源）拼在一起。
- 归档号一旦生成，包内容即被冻结，后续发布新版本不会改动旧包。
"""
from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from typing import Any

from app.store import store

# 完整知识库包必须具备的键；缺任一项即视为文件不完整。
REQUIRED_PACKET_KEYS = (
    "archive_no", "label_id", "label_code", "scene", "version",
    "rule_text", "fields", "source", "exported_at",
)
REQUIRED_SOURCE_KEYS = ("mining_result_id", "mining_result_code")


class KnowledgeArchiveService:
    """场景知识库包归档仓库（内存实现，接口语义对齐长期对象存储）。"""

    def __init__(self) -> None:
        self._archives: dict[str, dict[str, Any]] = {}

    @staticmethod
    def split_fields(value: Any) -> list[str]:
        """把逗号分隔（兼容中文逗号）的字段组合拆成去空白后的列表。"""
        return [
            part.strip()
            for part in str(value or "").replace("，", ",").split(",")
            if part.strip()
        ]

    @staticmethod
    def _packet_complete(packet: dict[str, Any]) -> bool:
        if any(not packet.get(key) for key in REQUIRED_PACKET_KEYS):
            return False
        source = packet.get("source") or {}
        if any(not source.get(key) for key in REQUIRED_SOURCE_KEYS):
            return False
        return bool(packet.get("fields")) and bool(packet.get("rule_text"))

    def list_archives(self) -> list[dict[str, Any]]:
        return [copy.deepcopy(packet) for packet in self._archives.values()]

    # ── 导出：读取完整的已发布版本并冻结为知识库包 ──
    def export_knowledge_base(self, label_id: int) -> dict[str, Any]:
        label = store.find("scenario_label", label_id)
        if label is None:
            return {"ok": False, "reason": f"场景标注 {label_id} 不存在或已归档"}

        published = [v for v in (label.get("versions") or []) if v.get("published")]
        if not published:
            return {"ok": False, "reason": "该场景标注尚无已生效的发布版本，知识库包只能读取已发布版本"}

        # 并发安全语义：导出永远取发布链上的不可变快照，草稿工作区不在读取范围内，
        # 因此即使导出与新版发布交错，也只会读到完整的旧发布版或完整的新发布版。
        version = max(published, key=lambda v: int(v.get("version_seq", 0)))
        fields = list(version.get("fields") or [])
        rule_text = str(version.get("rule_text") or "")
        source = version.get("source") or {}
        if not fields or not rule_text or not source.get("mining_result_id"):
            return {"ok": False, "reason": "发布版本内容不完整：规则文本、字段组合或挖掘来源缺失，禁止导出"}

        archive_no = (
            f"KB-{label_id:04d}-V{int(version['version_seq']):02d}-{len(self._archives) + 1:04d}"
        )
        packet = {
            "archive_no": archive_no,
            "label_id": label_id,
            "label_code": label.get("标注编号"),
            "scene": label.get("场景名称"),
            "version": version.get("version"),
            "version_seq": version.get("version_seq"),
            # 三项内容同属该次发布快照，从结构上杜绝跨版本拼装。
            "rule_text": rule_text,
            "fields": fields,
            "source": {
                "mining_result_id": source.get("mining_result_id"),
                "mining_result_code": source.get("mining_result_code"),
                "topic": source.get("topic"),
            },
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "integrity": "complete",
        }
        # 深拷贝入库，之后任何标签草稿/发布改动都影响不到已归档包。
        self._archives[archive_no] = copy.deepcopy(packet)
        return {"ok": True, "archive_no": archive_no, "packet": copy.deepcopy(packet)}

    # ── 重下：归档号回查原文件 ──
    def download_archive(self, archive_no: str) -> dict[str, Any]:
        packet = self._archives.get(archive_no)
        if packet is None:
            return {"ok": False, "reason": f"归档号 {archive_no} 不存在"}
        if not self._packet_complete(packet):
            return {"ok": False, "reason": "知识库文件不完整，禁止下载"}
        return {
            "ok": True,
            "archive_no": archive_no,
            "filename": f"{archive_no}.json",
            "content": json.dumps(packet, ensure_ascii=False, indent=2),
            "packet": copy.deepcopy(packet),
        }

    # ── 分群关联：用文件内的同版字段重新匹配当前聚类配置 ──
    def link_archive_to_clusters(self, archive_no: str) -> dict[str, Any]:
        packet = self._archives.get(archive_no)
        if packet is None:
            return {"ok": False, "linkable": False,
                    "reason": f"归档号 {archive_no} 不存在，不可关联",
                    "archive_no": archive_no, "related_clusters": [], "count": 0}
        if not self._packet_complete(packet):
            return {"ok": False, "linkable": False, "reason": "知识库文件不完整，不可关联",
                    "archive_no": archive_no, "related_clusters": [], "count": 0}

        # 注意：参与匹配的是归档文件内冻结的同版字段，而不是标签当前工作区字段，
        # 因此旧归档始终按旧版规则/字段重做关联。
        archive_fields = set(packet.get("fields") or [])
        matched: list[dict[str, Any]] = []
        for cfg in store.rows("cluster_config"):
            cfg_fields = set(self.split_fields(cfg.get("特征集")))
            if cfg_fields and cfg_fields.issubset(archive_fields):
                matched.append({
                    "cluster_id": cfg.get("id"),
                    "config_code": cfg.get("配置编号"),
                    "features": sorted(cfg_fields),
                    "algorithm": cfg.get("算法类型"),
                })
        return {
            "ok": True,
            "linkable": True,
            "archive_no": archive_no,
            "label_code": packet.get("label_code"),
            "version": packet.get("version"),
            "fields": sorted(archive_fields),
            "related_clusters": matched,
            "count": len(matched),
        }


knowledge_archive_service = KnowledgeArchiveService()
