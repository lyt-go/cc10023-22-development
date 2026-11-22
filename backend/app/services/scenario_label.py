"""业务场景标注领域服务：数据分析场景的业务标注、规则表达与知识管理。

版本管理语义：
- 挖掘结果转标注时生成 v1 草稿，规则、字段、来源编号三者一同登记；
- 草稿阶段只能通过 save_draft_fields 改工作区字段/规则，发布链上的旧版本不受影响；
- publish_version 把当前工作区固化成不可变快照（规则文本+字段组合+来源编号同属一次发布），
  之后草稿再怎么改都不会污染已发布版本；
- 知识库包导出只读取已发布快照，因此草稿与发布、新旧版本永远不会被拼装。
"""
from __future__ import annotations

import copy
from typing import Any

from app.services.base import BaseModuleService
from app.services.knowledge_archive import knowledge_archive_service
from app.store import store


class ScenarioLabelService(BaseModuleService):
    MODULE = "scenario_label"
    ENTITY = "场景标注"
    OPERATION_TERM = "关联"
    LIST_FIELDS = ["标注编号", "场景名称", "关联特征", "业务规则", "标注时间", "标注人", "标注状态", "场景版本"]
    REQUIRED_FIELDS = ["标注编号", "场景名称", "关联特征"]
    STATUS_ORDER = ["草稿", "待校验", "已生效", "已废弃"]
    ACTION_RULES = {"提交校验": "待校验", "标记生效": "已生效", "标记废弃": "已废弃"}
    NEGATIVE_ACTIONS = []

    # ── 挖掘结果 → 场景知识库标签（含来源编号的版本化标注） ──
    def convert_mining_result_to_label(self, result_id: int, fields: str | None = None) -> dict[str, Any]:
        """把挖掘结果转成场景知识库标签草稿，规则、字段、来源编号一同绑定为 v1 草稿。"""
        result = store.find("mining_result", result_id)
        if result is None:
            return {"ok": False, "reason": f"挖掘结果 {result_id} 不存在或已归档"}

        label_rows = store.rows(self.MODULE)
        next_id = max((int(r.get("id", 0)) for r in label_rows), default=0) + 1
        field_list = knowledge_archive_service.split_fields(
            fields if fields is not None else result.get("关键分群", "")
        )
        rule_text = str(result.get("洞察摘要", "") or f"挖掘结果{result.get('结果编号')}转标注规则")
        source = {
            "mining_result_id": result_id,
            "mining_result_code": result.get("结果编号"),
            "topic": result.get("分析主题"),
        }
        label = {
            "id": next_id,
            "status": "草稿",
            "pending": True,
            "abnormal": False,
            "标注编号": f"LABEL-M{result_id:04d}-{next_id:04d}",
            "场景名称": f"挖掘场景_{result.get('分析主题', 'unknown')}",
            # 工作区字段：草稿可改，未发布前不进入任何知识库包。
            "关联特征": ",".join(field_list),
            "业务规则": rule_text,
            "标注时间": "2026-11-22",
            "标注人": "mining_convert",
            "标注状态": "草稿",
            "场景版本": "v1（草稿）",
            "draft_source": dict(source),
            # 已发布版本链：每项均为不可变快照，发布后不再回写。
            "versions": [],
        }
        label_rows.append(label)
        return {
            "ok": True,
            "label_id": next_id,
            "mining_result_id": result_id,
            "version": "v1",
            "fields": field_list,
            "rule_text": rule_text,
            "source": source,
        }

    def save_draft_fields(
        self,
        label_id: int,
        fields: str | None = None,
        rule_text: str | None = None,
        mining_result_id: int | None = None,
    ) -> dict[str, Any]:
        """只保存草稿工作区字段/规则/来源；已发布版本保持冻结，旧发布版仍可导出。"""
        label = store.find(self.MODULE, label_id)
        if label is None:
            return {"ok": False, "reason": f"场景标注 {label_id} 不存在或已归档"}

        if fields is not None:
            label["关联特征"] = ",".join(knowledge_archive_service.split_fields(fields))
        if rule_text is not None:
            label["业务规则"] = rule_text
        if mining_result_id is not None:
            result = store.find("mining_result", mining_result_id)
            if result is None:
                return {"ok": False, "reason": f"挖掘结果 {mining_result_id} 不存在或已归档"}
            label["draft_source"] = {
                "mining_result_id": mining_result_id,
                "mining_result_code": result.get("结果编号"),
                "topic": result.get("分析主题"),
            }
            # 换绑来源时同步刷新草稿规则文本，保证规则、字段、来源在同一草稿版本内一致，
            # 已发布快照不受影响。
            label["业务规则"] = str(
                result.get("洞察摘要", "") or f"挖掘结果{result.get('结果编号')}转标注规则"
            )
        label["status"] = "草稿"
        label["pending"] = True
        label["场景版本"] = f"v{len(label.get('versions') or []) + 1}（草稿）"
        return {
            "ok": True,
            "label_id": label_id,
            "draft_fields": knowledge_archive_service.split_fields(label.get("关联特征")),
            "draft_rule": label.get("业务规则"),
            "draft_source": label.get("draft_source"),
            "published_versions": len(label.get("versions") or []),
        }

    def publish_version(self, label_id: int) -> dict[str, Any]:
        """发布当前草稿：把规则、字段、来源整体固化为一个不可变版本快照。"""
        label = store.find(self.MODULE, label_id)
        if label is None:
            return {"ok": False, "reason": f"场景标注 {label_id} 不存在或已归档"}

        fields = knowledge_archive_service.split_fields(label.get("关联特征"))
        rule_text = str(label.get("业务规则") or "")
        source = label.get("draft_source") or {}
        # 发布完整性：三项缺一不可，保证任何已发布版本都能独立导出完整知识库包。
        if not fields or not rule_text or not source.get("mining_result_id"):
            label["abnormal"] = True
            return {"ok": False, "reason": "草稿内容不完整：规则文本、字段组合或挖掘来源编号缺失，禁止发布"}

        versions = label.setdefault("versions", [])
        version_seq = len(versions) + 1
        snapshot = {
            "version": f"v{version_seq}",
            "version_seq": version_seq,
            "rule_text": rule_text,
            "fields": fields,
            "source": copy.deepcopy(source),
            "published_at": "2026-11-22",
            "published": True,
        }
        # 深拷贝快照，后续草稿修改与新版本发布都不会回写该版本。
        versions.append(copy.deepcopy(snapshot))
        label["status"] = "已生效"
        label["pending"] = False
        label["abnormal"] = False
        label["标注状态"] = "已生效"
        label["场景版本"] = snapshot["version"]
        return {"ok": True, "label_id": label_id, "version": snapshot,
                "published_versions": len(versions)}

    def list_version_chain(self, label_id: int) -> dict[str, Any]:
        """回查场景标签的版本链，草稿工作区与各已发布快照分开呈现。"""
        label = store.find(self.MODULE, label_id)
        if label is None:
            return {"ok": False, "reason": f"场景标注 {label_id} 不存在或已归档"}
        return {
            "ok": True,
            "label_id": label_id,
            "label_code": label.get("标注编号"),
            "draft": {
                "fields": knowledge_archive_service.split_fields(label.get("关联特征")),
                "rule_text": label.get("业务规则"),
                "source": label.get("draft_source"),
            },
            "published_versions": copy.deepcopy(label.get("versions") or []),
        }

    def export_knowledge_base(self, label_id: int) -> dict[str, Any]:
        """导出指定场景标注当前最新已发布版本的知识库包，返回归档号。"""
        return knowledge_archive_service.export_knowledge_base(label_id)

    def link_archive_to_clusters(self, archive_no: str) -> dict[str, Any]:
        """凭归档号，用知识库文件内的同版字段重新匹配当前聚类配置。"""
        return knowledge_archive_service.link_archive_to_clusters(archive_no)

    # ── 链路6: 聚类配置 → 分群 → 场景标注（保留原有链路能力） ──
    def validate_label_rules(self, label_id: int) -> dict[str, Any]:
        """校验场景标注的业务规则合法性，检查关联特征是否存在且可查询。"""
        label = store.find(self.MODULE, label_id)
        if label is None:
            return {"ok": False}
        feats = label.get("关联特征", "")
        define_rows = store.rows("feature_define")
        matched = [r for r in define_rows if r.get("特征名称", "") in feats.split(",")]
        if len(matched) == 0:
            label["status"] = "待校验"
            label["abnormal"] = True
            return {"ok": False, "reason": "关联特征均不存在于特征定义中"}
        label["status"] = "已生效"
        label["abnormal"] = False
        return {"ok": True, "label_id": label_id, "matched_features": len(matched)}

    def link_to_cluster_segments(self, label_id: int) -> dict[str, Any]:
        """将场景标注与聚类分群关联，形成聚类→分群→标注的完整链路。"""
        label = store.find(self.MODULE, label_id)
        if label is None:
            return {"ok": False}
        cluster_rows = store.rows("cluster_config")
        related = []
        for c in cluster_rows:
            if c.get("特征集") and label.get("关联特征") and any(
                f.strip() in str(c.get("特征集", "")) for f in str(label.get("关联特征", "")).split(",")
            ):
                related.append({"cluster_id": c.get("id"), "algorithm": c.get("算法类型")})
        return {"ok": True, "label_id": label_id, "related_clusters": related, "count": len(related)}

    def export_label_knowledge_base(self) -> dict[str, Any]:
        """导出全量场景标注知识库，按业务主题聚合后供给外部系统查询。"""
        rows = store.rows(self.MODULE)
        by_status = {}
        for r in rows:
            st = r.get("status", "unknown")
            if st not in by_status:
                by_status[st] = []
            by_status[st].append({
                "id": r.get("id"),
                "scene": r.get("场景名称"),
                "features": r.get("关联特征"),
                "rules": r.get("业务规则"),
                "annotator": r.get("标注人"),
            })
        return {"ok": True, "total_labels": len(rows), "by_status": by_status}

    def standardize_label_format(self, label_id: int) -> dict[str, Any]:
        """标准化场景标注的格式，确保规则表达符合统一的标注规范。"""
        label = store.find(self.MODULE, label_id)
        if label is None:
            return {"ok": False}
        raw_rules = label.get("业务规则", "")
        standardized = raw_rules.replace(" ", "_").replace("，", ",").lower()
        label["业务规则"] = standardized
        return {"ok": True, "label_id": label_id, "raw": raw_rules, "standardized": standardized}
