<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api'

const d = ref(null)
const err = ref('')
async function load() {
  err.value = ''
  try { d.value = await api.dashboard() } catch (e) { err.value = e.message }
}
function fmt(n) { return Number(n || 0).toFixed(2) }
onMounted(load)
</script>
<template>
  <div class="panel">
    <div class="grid" v-if="d">
      <div class="stat"><div class="k">业务日</div><div class="v">{{ d.business_day }}</div></div>
      <div class="stat"><div class="k">今日事件</div><div class="v">{{ d.event_count }}</div></div>
      <div class="stat"><div class="k">核销事实</div><div class="v ticket">{{ d.fact_count }}</div></div>
      <div class="stat"><div class="k">待钉 open</div><div class="v">{{ d.open_fact_count }}</div></div>
      <div class="stat"><div class="k">今日核销额</div><div class="v ticket">{{ fmt(d.redeem_total_today) }}</div></div>
      <div class="stat"><div class="k">已钉活动</div><div class="v">{{ d.sealed_campaign_count }}</div></div>
    </div>
    <div class="grid ledger" v-if="d?.ledger">
      <div class="stat"><div class="k">open 合计</div><div class="v">{{ fmt(d.ledger.open_total_amount) }}</div></div>
      <div class="stat"><div class="k">已钉活动批合计</div><div class="v">{{ fmt(d.ledger.campaign_batch_total_amount) }}</div></div>
      <div class="stat">
        <div class="k">合计等式</div>
        <div class="v"><span class="tag" :class="d.ledger.balanced ? 'ok' : 'warn'">{{ d.ledger.balanced ? '平' : '不平' }}</span></div>
      </div>
      <div class="stat"><div class="k">钉扎粒度</div><div class="v scope">按活动分批</div></div>
    </div>
    <p class="msg" v-if="!err">
      票根洋红标出核销侧数字。钉扎粒度全局唯一：按活动分批钉；已钉活动禁止再写该活动核销，未钉活动不受影响。
    </p>
    <p class="msg err" v-if="err">{{ err }}</p>
  </div>
</template>
