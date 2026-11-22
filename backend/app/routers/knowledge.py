"""场景知识库路由：版本化标注、知识库包导出/重下与归档号分群关联。

与通用资源路由分开注册，并先于资源路由挂载，避免 /api/{module}/{id} 动态段
抢占这些固定的领域路径。
"""
from __future__ import annotations

import io
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.schemas import (
    ArchivePayload,
    DraftFieldsPayload,
    KnowledgeExportPayload,
    MiningConvertPayload,
)
from app.services.data_export import DataExportService
from app.services.knowledge_archive import knowledge_archive_service
from app.services.scenario_label import ScenarioLabelService

router = APIRouter(prefix="/api", tags=["场景知识库"])

label_service = ScenarioLabelService()
export_service = DataExportService()


def _ensure_ok(result: dict[str, Any], status: int = 409) -> dict[str, Any]:
    if not result.get("ok"):
        raise HTTPException(status_code=status, detail=result.get("reason", "操作失败"))
    return result


# ── 场景标注：挖掘转标注、草稿、发布、版本链 ──
@router.post("/scenario-label/mining-results/convert")
def convert_mining_result(payload: MiningConvertPayload) -> dict[str, Any]:
    return _ensure_ok(
        label_service.convert_mining_result_to_label(payload.mining_result_id, payload.fields),
        status=404,
    )


@router.post("/scenario-label/{label_id}/draft")
def save_draft(label_id: int, payload: DraftFieldsPayload) -> dict[str, Any]:
    return _ensure_ok(
        label_service.save_draft_fields(
            label_id, payload.fields, payload.rule_text, payload.mining_result_id
        )
    )


@router.post("/scenario-label/{label_id}/publish")
def publish_label(label_id: int) -> dict[str, Any]:
    return _ensure_ok(label_service.publish_version(label_id))


@router.get("/scenario-label/{label_id}/versions")
def version_chain(label_id: int) -> dict[str, Any]:
    return _ensure_ok(label_service.list_version_chain(label_id), status=404)


# ── 场景知识库包：导出、归档清单、归档号分群关联 ──
@router.post("/scenario-label/knowledge-base/export")
def export_knowledge_base(payload: KnowledgeExportPayload) -> dict[str, Any]:
    """导出知识库包并在数据导出管理登记，返回归档号与包内容。"""
    return _ensure_ok(export_service.export_scenario_knowledge_base(payload.label_id))


@router.get("/scenario-label/knowledge-base/archives")
def list_archives() -> dict[str, Any]:
    items = knowledge_archive_service.list_archives()
    return {"ok": True, "items": items, "total": len(items)}


@router.post("/scenario-label/knowledge-base/link")
def link_archive(payload: ArchivePayload) -> dict[str, Any]:
    """凭归档号用文件内同版字段重新匹配当前聚类配置；不可关联时返回 ok=false。"""
    # 业务上属于"不可关联"，保留 200 + 结构化原因与空分群列表，便于前端直接展示。
    return knowledge_archive_service.link_archive_to_clusters(payload.archive_no)


# ── 数据导出管理：知识库导出登记清单与重下 ──
@router.get("/data-export/knowledge-base")
def list_knowledge_exports() -> dict[str, Any]:
    return export_service.list_knowledge_exports()


@router.get("/data-export/knowledge-base/{archive_no}/download")
def redownload_archive(archive_no: str) -> StreamingResponse:
    result = export_service.redownload_archive(archive_no)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("reason", "文件不可下载"))
    return StreamingResponse(
        io.StringIO(result["content"]),
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{result["filename"]}"'},
    )


@router.get("/data-export/tasks/{task_id}/knowledge-base/download")
def redownload_task_archive(task_id: int) -> StreamingResponse:
    result = export_service.redownload_task_archive(task_id)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("reason", "文件不可下载"))
    return StreamingResponse(
        io.StringIO(result["content"]),
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{result["filename"]}"'},
    )
