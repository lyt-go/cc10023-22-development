"""业务路由汇总：知识库固定路由先注册，通用资源路由兜底动态模块路径。"""
from __future__ import annotations

from app.routers import knowledge, resource

# knowledge 含 /api/scenario-label/... 等固定领域路径，必须排在 resource 前，
# 否则会被 /api/{module}/{entry_id} 动态段抢先匹配。
ROUTERS = [knowledge, resource]
