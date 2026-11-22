import { request } from './client'
import { moduleMeta } from '@/data/modules'
import type { ActionResult, EntryRow, OverviewResult, PageResult } from '@/data/types'

export { moduleMeta }

export async function listEntries(
  key: string,
  filters: Record<string, string> = {},
): Promise<PageResult> {
  const query = new URLSearchParams(filters).toString()
  const response = await request(`/api/${key}?${query}`)
  if (!response.ok) throw new Error('业务数据读取失败')
  return await response.json()
}

export async function createEntry(
  key: string,
  values: Record<string, string>,
): Promise<ActionResult> {
  const response = await request(`/api/${key}`, {
    method: 'POST',
    body: JSON.stringify({ values }),
  })
  return await response.json()
}

export async function runAction(
  key: string,
  id: number,
  action: string,
): Promise<ActionResult> {
  const response = await request(`/api/${key}/${id}/actions`, {
    method: 'POST',
    body: JSON.stringify({ action }),
  })
  return await response.json()
}

export async function downloadEntries(
  key: string,
  filters: Record<string, string> = {},
): Promise<void> {
  const query = new URLSearchParams(filters).toString()
  const response = await request(`/api/${key}/export?${query}`)
  if (!response.ok) throw new Error('业务数据导出失败')
  const url = URL.createObjectURL(await response.blob())
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `${key}.csv`
  document.body.appendChild(anchor)
  anchor.click()
  document.body.removeChild(anchor)
  URL.revokeObjectURL(url)
}

export async function loadOverview(): Promise<OverviewResult> {
  const response = await request('/api/overview')
  if (!response.ok) throw new Error('运营概览读取失败')
  return await response.json()
}

// ── 场景知识库：版本化标注、知识库包导出/重下、归档号分群关联 ──

export type KnowledgePacket = {
  archive_no: string
  label_id: number
  label_code: string
  scene: string
  version: string
  rule_text: string
  fields: string[]
  source: { mining_result_id: number; mining_result_code: string; topic: string }
  exported_at: string
  integrity: string
}

export type ArchiveLinkResult = {
  ok: boolean
  linkable: boolean
  reason?: string
  archive_no: string
  version?: string
  fields?: string[]
  related_clusters: { cluster_id: number; config_code: string; features: string[]; algorithm: string }[]
  count: number
}

async function postJson<T>(path: string, body: Record<string, unknown>): Promise<T> {
  const response = await request(path, { method: 'POST', body: JSON.stringify(body) })
  return (await response.json()) as T
}

/** 挖掘结果转场景知识库标签草稿（规则、字段、来源编号一起绑定）。 */
export function convertMiningResult(miningResultId: number, fields?: string) {
  return postJson<{ ok: boolean; label_id: number; version: string; fields: string[] }>(
    '/api/scenario-label/mining-results/convert',
    { mining_result_id: miningResultId, fields },
  )
}

/** 只保存草稿字段/规则/来源，已发布版本保持冻结。 */
export function saveDraftFields(
  labelId: number,
  payload: { fields?: string; rule_text?: string; mining_result_id?: number },
) {
  return postJson<{ ok: boolean; published_versions: number }>(
    `/api/scenario-label/${labelId}/draft`,
    payload,
  )
}

/** 发布当前草稿为不可变版本快照。 */
export function publishLabelVersion(labelId: number) {
  return postJson<{ ok: boolean; version: { version: string; fields: string[] } }>(
    `/api/scenario-label/${labelId}/publish`,
    {},
  )
}

/** 回查草稿工作区与已发布版本链。 */
export async function loadVersionChain(labelId: number) {
  const response = await request(`/api/scenario-label/${labelId}/versions`)
  if (!response.ok) throw new Error('版本链读取失败')
  return await response.json()
}

/** 导出知识库包并在数据导出管理登记，返回归档号与包内容。 */
export function exportKnowledgeBase(labelId: number) {
  return postJson<{ ok: boolean; archive_no: string; packet: KnowledgePacket }>(
    '/api/scenario-label/knowledge-base/export',
    { label_id: labelId },
  )
}

/** 凭归档号用文件内同版字段重新匹配当前聚类配置。 */
export function linkArchiveToClusters(archiveNo: string) {
  return postJson<ArchiveLinkResult>(
    '/api/scenario-label/knowledge-base/link',
    { archive_no: archiveNo },
  )
}

/** 数据导出管理：列出已登记的场景知识库导出。 */
export async function listKnowledgeExports() {
  const response = await request('/api/data-export/knowledge-base')
  if (!response.ok) throw new Error('知识库导出登记读取失败')
  return await response.json()
}

/** 列出全部已冻结的场景知识库归档包。 */
export async function listKnowledgeArchives() {
  const response = await request('/api/scenario-label/knowledge-base/archives')
  if (!response.ok) throw new Error('知识库归档清单读取失败')
  return (await response.json()) as { ok: boolean; items: KnowledgePacket[]; total: number }
}

/** 按归档号重下场景知识库文件。 */
export async function redownloadArchive(archiveNo: string): Promise<void> {
  const response = await request(`/api/data-export/knowledge-base/${archiveNo}/download`)
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}))
    throw new Error(detail.detail ?? '知识库文件重下失败')
  }
  const url = URL.createObjectURL(await response.blob())
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `${archiveNo}.json`
  document.body.appendChild(anchor)
  anchor.click()
  document.body.removeChild(anchor)
  URL.revokeObjectURL(url)
}
