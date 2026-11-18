<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'

const all = ref(null)
const detail = ref(null)
const selected = ref('')
const msg = ref('')
const err = ref('')

const ledger = computed(() => all.value?.ledger || null)
const campaigns = computed(() => all.value?.campaigns || [])
const facts = computed(() => (detail.value || all.value)?.facts || [])
const selectedRow = computed(
  () => campaigns.value.find((c) => c.campaign_code === selected.value) || null
)

async function loadDetail() {
  detail.value = selected.value ? await api.preview(undefined, selected.value) : null
}

async function load() {
  err.value = ''
  try {
    all.value = await api.preview()
    if (!selected.value || !all.value.campaigns.some((c) => c.campaign_code === selected.value)) {
      selected.value = all.value.campaigns[0]?.campaign_code || ''
    }
    await loadDetail()
  } catch (e) { err.value = e.message }
}

async function choose(code) {
  selected.value = code
  msg.value = ''
  err.value = ''
  try { await loadDetail() } catch (e) { err.value = e.message }
}

async function seal(code) {
  msg.value = ''; err.value = ''
  const target = code || selected.value
  if (!target) { err.value = '请先选择要钉扎的活动'; return }
  try {
    const r = await api.seal({ campaign_code: target })
    msg.value = `已钉扎活动 ${r.campaign_code} · 批次 #${r.batch_id} · ${r.fact_count} 笔 · 合计 ${r.total_amount}`
    selected.value = target
    await load()
  } catch (e) { err.value = e.message }
}

function fmt(n) { return Number(n || 0).toFixed(2) }
onMounted(load)
</script>
<template>
  <div class="panel" v-if="all">
    <p class="msg policy">
      钉扎粒度：按活动分批钉扎（全局唯一，与整日钉扎互斥）。已钉活动禁止再写该活动核销；未钉活动仍可核销、仍可钉扎。
    </p>
    <div class="grid">
      <div class="stat"><div class="k">业务日</div><div class="v">{{ all.business_day }}</div></div>
      <div class="stat"><div class="k">日核销额</div><div class="v ticket">{{ fmt(ledger?.day_total_amount) }}</div></div>
      <div class="stat"><div class="k">open 合计</div><div class="v">{{ fmt(ledger?.open_total_amount) }}</div></div>
      <div class="stat"><div class="k">已钉活动批合计</div><div class="v">{{ fmt(ledger?.campaign_batch_total_amount) }}</div></div>
      <div class="stat">
        <div class="k">合计等式</div>
        <div class="v">
          <span class="tag" :class="ledger?.balanced ? 'ok' : 'warn'">{{ ledger?.balanced ? '平' : '不平' }}</span>
        </div>
      </div>
      <div class="stat">
        <div class="k">整日钉扎</div>
        <div class="v">{{ all.day_sealed ? '已启用' : '未启用（已禁用）' }}</div>
      </div>
    </div>
    <p class="msg">
      {{ ledger?.equation }}：
      {{ fmt(ledger?.day_total_amount) }} = {{ fmt(ledger?.open_total_amount) }} + {{ fmt(ledger?.campaign_batch_total_amount) }}
      <template v-if="ledger?.legacy_day_batch_total_amount">（含历史整日批 {{ fmt(ledger.legacy_day_batch_total_amount) }}）</template>
    </p>
  </div>

  <div class="panel" v-if="all">
    <table>
      <thead>
        <tr>
          <th>活动</th><th>事实</th><th>open 笔</th><th>open 合计</th>
          <th>已钉笔</th><th>已钉合计</th><th>活动批</th><th>写闸</th><th></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="c in campaigns" :key="c.campaign_code" :class="{ picked: c.campaign_code === selected }">
          <td>{{ c.campaign_code }} <small>{{ c.campaign_title }}</small></td>
          <td>{{ c.fact_count }}</td>
          <td>{{ c.open_count }}</td>
          <td>{{ fmt(c.open_total) }}</td>
          <td>{{ c.sealed_count }}</td>
          <td>{{ fmt(c.sealed_total) }}</td>
          <td>{{ c.batch_id ? `#${c.batch_id} · ${fmt(c.batch_total_amount)}` : '—' }}</td>
          <td>
            <span class="tag" :class="c.sealed ? 'warn' : 'ok'">{{ c.sealed ? '已封（禁写核销）' : '可核销' }}</span>
          </td>
          <td class="ops">
            <button type="button" class="ghost" @click="choose(c.campaign_code)">预览</button>
            <button type="button" @click="seal(c.campaign_code)" :disabled="!c.can_seal">钉扎</button>
            <small v-if="!c.can_seal">{{ c.block_reason }}</small>
          </td>
        </tr>
        <tr v-if="!campaigns.length"><td colspan="9" class="muted">本业务日没有核销事实</td></tr>
      </tbody>
    </table>
    <p class="msg" v-if="msg">{{ msg }}</p>
    <p class="msg err" v-if="err">{{ err }}</p>
  </div>

  <div class="panel" v-if="all">
    <div class="row head">
      <strong>待钉明细 · {{ selected || '全部' }}</strong>
      <span v-if="selectedRow">open {{ selectedRow.open_count }} 笔 / {{ fmt(selectedRow.open_total) }}</span>
    </div>
    <table>
      <thead><tr><th>事实ID</th><th>券码</th><th>活动</th><th>金额</th><th>状态</th></tr></thead>
      <tbody>
        <tr v-for="f in facts" :key="f.id">
          <td>{{ f.id }}</td>
          <td>{{ f.coupon_code }}</td>
          <td>{{ f.campaign_code }}</td>
          <td>{{ f.amount }}</td>
          <td><span class="tag warn">{{ f.status }}</span></td>
        </tr>
        <tr v-if="!facts.length"><td colspan="5" class="muted">该范围内没有 open 核销事实</td></tr>
      </tbody>
    </table>
  </div>
</template>
