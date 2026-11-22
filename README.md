# 特征工程与数据挖掘工作台

面向特征构建、特征选择、数据切片、模型训练与挖掘结果管理的数据分析特征工程平台。

这是一个前后端分离的管理平台：前端 Vue 3 + Vite + TypeScript，后端 FastAPI（Python）。
两边各自独立启动，前端 dev server 已关掉自动打开页面，启动后按终端打印的地址手工打开。

## 目录结构

```text
.
├── frontend/                 Vue 3 + Vite + TypeScript 前端
│   ├── src/views/WorkbenchView.vue|tsx  全部模块共享工作台
│   ├── src/data/modules.ts              18个业务模块配置
│   ├── src/api/              统一请求封装
│   └── vite.config.ts        dev server 配置（open: false）
├── backend/                  FastAPI（Python） 后端
│   ├── app/routers/resource.py  通用查询/导出/登记/动作接口
│   ├── app/services/<key>.py    每个模块独立领域逻辑
│   ├── app/services/base.py     共享服务骨架
│   └── app/store.py          内存数据仓库与示例数据
├── .gitignore
└── docker-compose.yml
```

## 启动

### 后端

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
./run.sh
```

健康检查：`curl http://127.0.0.1:8000/api/health`

### 前端

```bash
cd frontend
npm ci
npm run dev
```

前端默认监听 `http://127.0.0.1:5173/`，dev server 不会自动打开浏览器，
需要自己访问。`/api` 由 vite 代理到后端 `http://127.0.0.1:8000`。

## 业务模块

| 模块 | 目录 | 业务对象 | 主要字段 |
| --- | --- | --- | --- |
| 特征源管理 | `feature_source` | 特征源 | 源编号、源名称、数据表名 |
| 特征定义 | `feature_define` | 特征定义 | 特征编号、特征名称、特征类型 |
| 特征组管理 | `feature_group` | 特征组 | 组编号、组名称、包含特征 |
| 数据切片配置 | `data_slice` | 切片配置 | 切片编号、切片名称、数据来源 |
| 特征计算任务 | `feature_compute` | 计算任务 | 任务编号、关联特征、数据切片 |
| 特征筛选策略 | `feature_selection` | 筛选策略 | 策略编号、特征集、筛选方法 |
| 特征重要性分析 | `feature_iv` | 重要性评估 | 评估编号、关联特征、信息值IV |
| 特征快照管理 | `feature_snapshot` | 特征快照 | 快照编号、特征集、快照日期 |
| 训练流水线 | `train_pipeline` | 流水线配置 | 流水线编号、流水线名称、特征集 |
| 模型注册中心 | `model_registry` | 模型注册 | 模型编号、模型名称、算法类型 |
| 批量预测任务 | `predict_batch` | 预测任务 | 任务编号、模型编号、数据切片 |
| 挖掘结果管理 | `mining_result` | 挖掘结果 | 结果编号、分析主题、算法类型 |
| 聚类分析配置 | `cluster_config` | 聚类配置 | 配置编号、特征集、算法类型 |
| 特征相关性矩阵 | `feature_corr` | 相关性矩阵 | 矩阵编号、特征集、计算方法 |
| 特征漂移监控 | `drift_monitor` | 漂移监控 | 监控编号、关联特征、基准分布 |
| 数据导出管理 | `data_export` | 导出任务 | 任务编号、数据来源、导出范围 |
| 流水线调度 | `pipeline_schedule` | 调度配置 | 调度编号、关联流水线、Cron表达式 |
| 业务场景标注 | `scenario_label` | 场景标注 | 标注编号、场景名称、关联特征 |

## 约定

- 全部模块共享`frontend/src/views/WorkbenchView.vue|tsx`和一套资源路由。
- 每个模块仍保留独立`backend/app/services/<模块>.py`；纯前端保留
  `frontend/src/domain/<模块>.ts`，用于承载真实业务差异并维持36题位容量。
- 列表接口统一返回 `{ items, total, page, size }`，动作接口统一返回 `{ ok, message }`。
- 状态流转只允许在 `app/services` 里改，路由层不做业务判断。

## 场景知识库：版本化导出与归档号分群关联

业务场景标注在普通导出记录之外，提供可下载、可回查规则版本的场景知识库包：

- **挖掘转标注**：`POST /api/scenario-label/mining-results/convert` 把挖掘结果转成
  场景知识库标签草稿，规则文本、字段组合、来源挖掘结果编号三者一同绑定。
- **草稿与发布分离**：`POST /api/scenario-label/{id}/draft` 只改草稿工作区；
  `POST /api/scenario-label/{id}/publish` 把规则、字段、来源整体固化为不可变版本快照。
  已发布版本永不回写，`GET /api/scenario-label/{id}/versions` 可回查整条版本链。
- **知识库包导出**：`POST /api/scenario-label/knowledge-base/export` 只读取完整的
  已生效版本并冻结为归档包（含规则、字段、来源），同时在数据导出管理登记一条
  导出任务并留存归档号。草稿字段不会入包，任何导出都不会把新规则与旧字段拼在一起；
  仅保存草稿时，旧发布版仍可正常导出。
- **重下**：`GET /api/data-export/knowledge-base/{归档号}/download` 按归档号重下原文件，
  旧归档内容不随新版本发布而改变；也可按导出任务重下
  `GET /api/data-export/tasks/{任务id}/knowledge-base/download`。
- **归档号分群关联**：`POST /api/scenario-label/knowledge-base/link` 接收归档号，
  用文件内冻结的同版字段重新匹配当前聚类配置，返回此次关联到的分群。
  归档号不存在或文件不完整时返回 `ok=false` 并说明不可关联原因。

实现位于 `backend/app/services/knowledge_archive.py`（归档仓库与同版匹配）、
`scenario_label.py`（版本链）、`data_export.py`（导出登记与重下），
路由见 `backend/app/routers/knowledge.py`；验收用例见
`backend/tests/test_knowledge_archive.py`。

领域：数据工程
子方向：数据分析与数据应用
