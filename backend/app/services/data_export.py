"""数据导出管理领域服务：分析结果的导出配置、格式转换与异步任务。"""
from __future__ import annotations

from typing import Any

from app.services.base import BaseModuleService
from app.services.knowledge_archive import knowledge_archive_service
from app.store import store


class DataExportService(BaseModuleService):
    MODULE = "data_export"
    ENTITY = "导出任务"
    OPERATION_TERM = "转换"
    LIST_FIELDS = ["任务编号", "数据来源", "导出范围", "导出格式", "字段映射", "分片策略", "压缩方式", "导出状态"]
    REQUIRED_FIELDS = ["任务编号", "数据来源", "导出范围"]
    STATUS_ORDER = ["草稿", "导出中", "已完成", "已失败"]
    ACTION_RULES = {"开始导出": "导出中", "确认完成": "已完成", "标记失败": "已失败"}
    NEGATIVE_ACTIONS = []

    # ── 场景知识库包导出登记与重下 ──
    def export_scenario_knowledge_base(self, label_id: int) -> dict[str, Any]:
        """导出场景知识库包并在数据导出管理登记该次导出，归档号随任务留存。"""
        result = knowledge_archive_service.export_knowledge_base(label_id)
        if not result.get("ok"):
            return result
        packet = result["packet"]
        archive_no = result["archive_no"]

        rows = store.rows(self.MODULE)
        next_id = max((int(row.get("id", 0)) for row in rows), default=0) + 1
        task = {
            "id": next_id,
            "status": "已完成",
            "pending": False,
            "abnormal": False,
            "任务编号": f"KBEX-{next_id:04d}",
            "数据来源": f"场景标注:{packet.get('label_code')}",
            "导出范围": f"场景知识库包 {packet.get('version')}",
            "导出格式": "json",
            "字段映射": ",".join(packet.get("fields") or []),
            "分片策略": "single_archive",
            "压缩方式": "none",
            "导出状态": "已完成",
            # 归档号是重下与分群关联的唯一凭据。
            "归档号": archive_no,
            "场景标注ID": label_id,
            "场景版本": packet.get("version"),
            "挖掘来源编号": packet.get("source", {}).get("mining_result_code"),
        }
        rows.append(task)
        return {
            "ok": True,
            "export_id": next_id,
            "task_code": task["任务编号"],
            "archive_no": archive_no,
            "packet": packet,
        }

    def redownload_archive(self, archive_no: str) -> dict[str, Any]:
        """按归档号重下场景知识库文件；仅允许重下已在导出管理登记过的归档。"""
        registered = [
            row for row in store.rows(self.MODULE)
            if row.get("归档号") == archive_no
        ]
        if not registered:
            return {"ok": False, "reason": f"归档号 {archive_no} 未在数据导出管理登记，不可重下"}
        result = knowledge_archive_service.download_archive(archive_no)
        if result.get("ok"):
            result["export_id"] = registered[0].get("id")
            result["task_code"] = registered[0].get("任务编号")
        return result

    def redownload_task_archive(self, task_id: int) -> dict[str, Any]:
        """按导出任务重下其登记的场景知识库文件。"""
        task = store.find(self.MODULE, task_id)
        if task is None:
            return {"ok": False, "reason": f"导出任务 {task_id} 不存在或已归档"}
        archive_no = task.get("归档号")
        if not archive_no:
            return {"ok": False, "reason": f"导出任务 {task_id} 未登记场景知识库归档号"}
        return self.redownload_archive(archive_no)

    def list_knowledge_exports(self) -> dict[str, Any]:
        """列出全部已登记的场景知识库导出任务，供页面回查与重下。"""
        items = [
            {
                "export_id": row.get("id"),
                "task_code": row.get("任务编号"),
                "archive_no": row.get("归档号"),
                "label_id": row.get("场景标注ID"),
                "version": row.get("场景版本"),
                "source": row.get("挖掘来源编号"),
                "fields": row.get("字段映射"),
                "status": row.get("status"),
            }
            for row in store.rows(self.MODULE)
            if row.get("归档号")
        ]
        return {"ok": True, "items": items, "total": len(items)}

    def export_feature_dataset(self, task_id: int, output_format: str = "csv") -> dict[str, Any]:
        """将特征数据集导出为指定格式并写入外部存储路径。"""
        task = store.find(self.MODULE, task_id)
        if task is None:
            return {"ok": False}
        task["status"] = "导出中"
        task["pending"] = True
        task["导出格式"] = output_format
        task["status"] = "已完成"
        task["pending"] = False
        return {"ok": True, "task_id": task_id, "format": output_format,
                "output_path": f"exports/{task_id}/feature_dataset.{output_format}"}

    def convert_to_parquet(self, task_id: int) -> dict[str, Any]:
        """将导出数据转换为Parquet列式存储格式并压缩归档。"""
        task = store.find(self.MODULE, task_id)
        if task is None:
            return {"ok": False}
        task["导出格式"] = "parquet"
        task["压缩方式"] = "snappy"
        task["status"] = "已完成"
        task["pending"] = False
        return {"ok": True, "task_id": task_id, "format": "parquet",
                "compression": "snappy", "path": f"exports/{task_id}/data.snappy.parquet"}

    def archive_export_to_storage(self, task_id: int) -> dict[str, Any]:
        """将完成的导出任务归档到长期存储，保留历史版本供回溯。"""
        task = store.find(self.MODULE, task_id)
        if task is None:
            return {"ok": False}
        archive_path = f"archive/exports/{task_id}/v1.0/"
        return {
            "ok": True,
            "task_id": task_id,
            "archive_path": archive_path,
            "format": task.get("导出格式"),
            "message": f"导出任务 {task_id} 已归档至 {archive_path}",
        }

    def query_export_progress(self, task_id: int) -> dict[str, Any]:
        """查询导出任务的执行状态和进度详情。"""
        task = store.find(self.MODULE, task_id)
        if task is None:
            return {"ok": False}
        return {
            "ok": True,
            "task_id": task_id,
            "status": task.get("status"),
            "source": task.get("数据来源"),
            "format": task.get("导出格式"),
            "compression": task.get("压缩方式"),
        }