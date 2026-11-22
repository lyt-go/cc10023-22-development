<template>
  <section class="page" :data-module="meta.key">
    <header class="page-head">
      <div>
        <h2>{{ meta.name }}</h2>
        <p class="page-desc">{{ meta.desc }}</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" data-testid="open-create" type="button" @click="openCreate">
          登记{{ meta.entity }}
        </button>
        <button class="btn" data-testid="export" type="button" @click="exportRows">
          导出{{ meta.name }}清单
        </button>
        <button
          v-if="meta.key === 'scenario_label'"
          class="btn"
          data-testid="open-knowledge-panel"
          type="button"
          @click="openKnowledgePanel"
        >
          场景知识库归档
        </button>
        <button
          v-if="meta.key === 'data_export'"
          class="btn"
          data-testid="open-export-archive-panel"
          type="button"
          @click="openExportArchivePanel"
        >
          知识库导出登记
        </button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <p class="status-legend">
      <span v-for="item in statusSummary" :key="item.status" class="legend-item">
        {{ item.status }}：{{ item.count }}
      </span>
    </p>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :data-testid="`filter-${field}`" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" data-testid="query" type="submit">查询</button>
      <button class="btn ghost" data-testid="reset" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in meta.fields" :key="column">{{ column }}</th>
          <th>当前状态</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)" :data-testid="`row-${row.id}`" :data-status="String(row.status)">
          <td v-for="column in meta.fields" :key="column">{{ row[column] ?? '—' }}</td>
          <td>{{ row.status }}</td>
          <td class="row-actions">
            <button
              v-for="action in meta.actions"
              :key="action"
              class="link"
              type="button"
              :data-testid="`action-${row.id}-${action}`"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
            <button
              v-if="meta.key === 'mining_result'"
              class="link"
              type="button"
              :data-testid="`convert-${row.id}`"
              @click="openConvertDialog(row)"
            >
              转场景标注
            </button>
            <template v-if="meta.key === 'scenario_label'">
              <button class="link" type="button" :data-testid="`versions-${row.id}`" @click="inspectVersions(row)">
                版本链
              </button>
              <button class="link" type="button" :data-testid="`publish-${row.id}`" @click="publishRow(row)">
                发布版本
              </button>
              <button class="link" type="button" :data-testid="`kb-export-${row.id}`" @click="exportKb(row)">
                导出知识库包
              </button>
            </template>
            <button
              v-if="meta.key === 'data_export' && row['归档号']"
              class="link"
              type="button"
              :data-testid="`redownload-${row.id}`"
              @click="redownloadRow(row)"
            >
              重下知识库文件
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="meta.fields.length + 2" class="empty-state">
            暂无{{ meta.name }}数据，可先登记{{ meta.entity }}
          </td>
        </tr>
      </tbody>
    </table>

    <div v-if="showCreate" class="modal-backdrop" data-testid="create-modal">
      <form class="modal" @submit.prevent="submitCreate">
        <h3>登记{{ meta.entity }}</h3>
        <label v-for="field in meta.fields" :key="field" class="create-field">
          <span>{{ field }}</span>
          <input v-model="createValues[field]" :data-testid="`create-${field}`" required />
        </label>
        <div class="page-actions">
          <button class="btn" type="button" @click="showCreate = false">取消</button>
          <button class="btn primary" data-testid="submit-create" type="submit" :disabled="creating">
            {{ creating ? '提交中…' : '确认登记' }}
          </button>
        </div>
      </form>
    </div>

    <!-- 挖掘结果转场景知识库标签 -->
    <div v-if="convertDialog.open" class="modal-backdrop" data-testid="convert-modal">
      <form class="modal" @submit.prevent="submitConvert">
        <h3>挖掘结果转场景标注（{{ convertDialog.resultCode }}）</h3>
        <p class="page-desc">规则文本、字段组合与挖掘结果编号将绑定为 v1 草稿，发布后才可导出知识库包。</p>
        <label class="create-field">
          <span>字段组合（逗号分隔，如 age）</span>
          <input v-model="convertDialog.fields" data-testid="convert-fields" required />
        </label>
        <div class="page-actions">
          <button class="btn" type="button" @click="convertDialog.open = false">取消</button>
          <button class="btn primary" data-testid="submit-convert" type="submit" :disabled="creating">
            {{ creating ? '提交中…' : '生成标注草稿' }}
          </button>
        </div>
      </form>
    </div>

    <!-- 版本链查看 -->
    <div v-if="versionDialog.open" class="modal-backdrop" data-testid="version-modal">
      <div class="modal">
        <h3>场景版本链 · {{ versionDialog.labelCode }}</h3>
        <p class="page-desc">草稿工作区与已发布快照分开保存；知识库包只读取已发布快照。</p>
        <article class="kb-card">
          <strong>当前草稿（未发布不入包）</strong>
          <p>规则：{{ versionDialog.draft.rule_text || '—' }}</p>
          <p>字段：{{ (versionDialog.draft.fields || []).join(', ') || '—' }}</p>
          <p>来源：{{ versionDialog.draft.source?.mining_result_code || '—' }}</p>
        </article>
        <article v-for="ver in versionDialog.versions" :key="ver.version" class="kb-card" :data-testid="`version-${ver.version}`">
          <strong>{{ ver.version }}（已发布，不可变）</strong>
          <p>规则：{{ ver.rule_text }}</p>
          <p>字段：{{ ver.fields.join(', ') }}</p>
          <p>来源：{{ ver.source.mining_result_code }}（挖掘结果 #{{ ver.source.mining_result_id }}）</p>
        </article>
        <div class="page-actions">
          <button class="btn primary" type="button" @click="versionDialog.open = false">关闭</button>
        </div>
      </div>
    </div>

    <!-- 场景知识库归档面板：归档清单 + 归档号分群关联 -->
    <div v-if="archivePanel.open" class="modal-backdrop" data-testid="archive-panel">
      <div class="modal modal-wide">
        <h3>场景知识库归档</h3>
        <p class="page-desc">每个归档号对应一份冻结的已发布版本，规则、字段、来源同版，可随时重下或重做分群关联。</p>
        <table class="data-table">
          <thead>
            <tr><th>归档号</th><th>场景标注</th><th>版本</th><th>字段</th><th>来源</th><th>操作</th></tr>
          </thead>
          <tbody>
            <tr v-for="item in archivePanel.items" :key="item.archive_no" :data-testid="`archive-row-${item.archive_no}`">
              <td>{{ item.archive_no }}</td>
              <td>{{ item.label_code }}</td>
              <td>{{ item.version }}</td>
              <td>{{ item.fields.join(', ') }}</td>
              <td>{{ item.source.mining_result_code }}</td>
              <td class="row-actions">
                <button class="link" type="button" @click="redownloadArchiveNo(item.archive_no)">重下</button>
                <button class="link" type="button" @click="linkArchiveNo(item.archive_no)">分群关联</button>
              </td>
            </tr>
            <tr v-if="!archivePanel.items.length">
              <td colspan="6" class="empty-state">暂无知识库归档，请先发布场景版本并导出</td>
            </tr>
          </tbody>
        </table>
        <div v-if="archivePanel.linkResult" class="kb-card" data-testid="archive-link-result">
          <strong v-if="archivePanel.linkResult.ok">
            归档 {{ archivePanel.linkResult.archive_no }} 关联到 {{ archivePanel.linkResult.count }} 个分群
          </strong>
          <strong v-else class="error-text">不可关联：{{ archivePanel.linkResult.reason }}</strong>
          <p v-if="archivePanel.linkResult.ok">
            分群：{{ archivePanel.linkResult.related_clusters.map((c) => c.config_code).join(', ') || '（无匹配聚类配置）' }}
          </p>
        </div>
        <div class="page-actions">
          <button class="btn primary" type="button" @click="archivePanel.open = false">关闭</button>
        </div>
      </div>
    </div>

    <!-- 数据导出管理：知识库导出登记清单与重下 -->
    <div v-if="exportArchivePanel.open" class="modal-backdrop" data-testid="export-archive-panel">
      <div class="modal modal-wide">
        <h3>知识库导出登记</h3>
        <table class="data-table">
          <thead>
            <tr><th>导出任务</th><th>归档号</th><th>场景版本</th><th>字段映射</th><th>挖掘来源</th><th>状态</th><th>操作</th></tr>
          </thead>
          <tbody>
            <tr v-for="item in exportArchivePanel.items" :key="item.archive_no">
              <td>{{ item.task_code }}</td>
              <td>{{ item.archive_no }}</td>
              <td>{{ item.version }}</td>
              <td>{{ item.fields }}</td>
              <td>{{ item.source }}</td>
              <td>{{ item.status }}</td>
              <td class="row-actions">
                <button class="link" type="button" @click="redownloadArchiveNo(item.archive_no)">重下知识库文件</button>
              </td>
            </tr>
            <tr v-if="!exportArchivePanel.items.length">
              <td colspan="7" class="empty-state">暂无知识库导出登记</td>
            </tr>
          </tbody>
        </table>
        <div class="page-actions">
          <button class="btn primary" type="button" @click="exportArchivePanel.open = false">关闭</button>
        </div>
      </div>
    </div>

    <footer class="page-foot">
      <span>共 {{ total }} 条{{ meta.name }}记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import {
  convertMiningResult,
  createEntry,
  downloadEntries,
  exportKnowledgeBase,
  linkArchiveToClusters,
  listEntries,
  listKnowledgeArchives,
  listKnowledgeExports,
  loadVersionChain,
  moduleMeta,
  publishLabelVersion,
  redownloadArchive,
  runAction as applyAction,
  type ArchiveLinkResult,
  type KnowledgePacket,
} from '@/api/backend-service'
import type { EntryRow } from '@/data/types'

const props = defineProps<{ moduleKey: string }>()
const meta = moduleMeta(props.moduleKey)
const rows = ref<EntryRow[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = meta.fields.slice(0, 3)
const showCreate = ref(false)
const creating = ref(false)
const createValues = ref<Record<string, string>>({})

// 挖掘结果 → 场景标注草稿
const convertDialog = reactive<{ open: boolean; miningId: number | null; resultCode: string; fields: string }>({
  open: false, miningId: null, resultCode: '', fields: '',
})
// 场景版本链
const versionDialog = reactive<{
  open: boolean
  labelCode: string
  draft: { rule_text?: string; fields?: string[]; source?: { mining_result_code?: string } }
  versions: { version: string; rule_text: string; fields: string[]; source: { mining_result_id: number; mining_result_code: string } }[]
}>({ open: false, labelCode: '', draft: {}, versions: [] })
// 场景知识库归档清单与关联结果
const archivePanel = reactive<{ open: boolean; items: KnowledgePacket[]; linkResult: ArchiveLinkResult | null }>({
  open: false, items: [], linkResult: null,
})
// 数据导出管理中的知识库导出登记
const exportArchivePanel = reactive<{
  open: boolean
  items: { task_code: string; archive_no: string; version: string; fields: string; source: string; status: string }[]
}>({ open: false, items: [] })
const stats = computed(() => [
  { label: meta.metrics[0], value: total.value },
  { label: meta.metrics[1], value: rows.value.filter((row) => row.status === meta.statuses[1]).length },
  {
    label: meta.metrics[2],
    value: rows.value.filter((row) => row.status === meta.statuses[meta.statuses.length - 1]).length,
  },
])
const statusSummary = computed(() =>
  meta.statuses.map((status) => ({
    status,
    count: rows.value.filter((row) => String(row.status) === status).length,
  })),
)

function resetFilters() {
  filters.value = {}
  void reload()
}

async function exportRows() {
  errorMessage.value = ''
  try {
    await downloadEntries(meta.key, filters.value)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '导出失败'
  }
}

function openCreate() {
  createValues.value = Object.fromEntries(meta.fields.map((field) => [field, '']))
  errorMessage.value = ''
  showCreate.value = true
}

async function submitCreate() {
  creating.value = true
  errorMessage.value = ''
  try {
    const result = await createEntry(meta.key, createValues.value)
    if (!result.ok) throw new Error(result.message)
    showCreate.value = false
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '登记失败'
  } finally {
    creating.value = false
  }
}

async function runAction(action: string, row: EntryRow) {
  errorMessage.value = ''
  try {
    const result = await applyAction(meta.key, Number(row.id), action)
    if (!result.ok) throw new Error(result.message)
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '操作失败'
  }
}

// ── 场景知识库相关交互 ──
function openConvertDialog(row: EntryRow) {
  convertDialog.open = true
  convertDialog.miningId = Number(row.id)
  convertDialog.resultCode = String(row['结果编号'] ?? row.id)
  convertDialog.fields = String(row['关键分群'] ?? '')
  errorMessage.value = ''
}

async function submitConvert() {
  if (convertDialog.miningId === null) return
  creating.value = true
  errorMessage.value = ''
  try {
    const result = await convertMiningResult(convertDialog.miningId, convertDialog.fields)
    if (!result.ok) throw new Error('转标注失败')
    convertDialog.open = false
    errorMessage.value = `已生成场景标注草稿 #${result.label_id}（${result.version}），发布后即可导出知识库包`
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '转标注失败'
  } finally {
    creating.value = false
  }
}

async function inspectVersions(row: EntryRow) {
  errorMessage.value = ''
  try {
    const chain = await loadVersionChain(Number(row.id))
    versionDialog.open = true
    versionDialog.labelCode = chain.label_code
    versionDialog.draft = chain.draft
    versionDialog.versions = chain.published_versions
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '版本链读取失败'
  }
}

async function publishRow(row: EntryRow) {
  errorMessage.value = ''
  try {
    const result = await publishLabelVersion(Number(row.id))
    if (!result.ok) throw new Error('发布失败')
    errorMessage.value = `版本 ${result.version.version} 已发布并冻结，可导出知识库包`
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '发布失败'
  }
}

async function exportKb(row: EntryRow) {
  errorMessage.value = ''
  try {
    const result = await exportKnowledgeBase(Number(row.id))
    if (!result.ok) throw new Error('知识库包导出失败')
    errorMessage.value = `知识库包已导出并登记，归档号：${result.archive_no}（版本 ${result.packet.version}）`
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '知识库包导出失败'
  }
}

async function openKnowledgePanel() {
  errorMessage.value = ''
  try {
    const data = await listKnowledgeArchives()
    archivePanel.items = data.items ?? []
    archivePanel.linkResult = null
    archivePanel.open = true
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '归档清单读取失败'
  }
}

async function openExportArchivePanel() {
  errorMessage.value = ''
  try {
    const data = await listKnowledgeExports()
    exportArchivePanel.items = data.items ?? []
    exportArchivePanel.open = true
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '导出登记读取失败'
  }
}

async function redownloadArchiveNo(archiveNo: string) {
  errorMessage.value = ''
  try {
    await redownloadArchive(archiveNo)
    errorMessage.value = `归档 ${archiveNo} 原文件已开始下载`
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '重下失败'
  }
}

async function redownloadRow(row: EntryRow) {
  await redownloadArchiveNo(String(row['归档号']))
}

async function linkArchiveNo(archiveNo: string) {
  errorMessage.value = ''
  try {
    archivePanel.linkResult = await linkArchiveToClusters(archiveNo)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '分群关联失败'
  }
}

async function reload() {
  errorMessage.value = ''
  try {
    const payload = await listEntries(meta.key, filters.value)
    rows.value = payload.items
    total.value = payload.total
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '业务列表读取失败'
  }
}

onMounted(reload)
</script>
