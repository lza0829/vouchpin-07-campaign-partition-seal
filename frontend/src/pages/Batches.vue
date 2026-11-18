<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api'
const rows = ref([])
const err = ref('')
async function load() {
  try { rows.value = await api.batches() } catch (e) { err.value = e.message }
}
onMounted(load)
</script>
<template>
  <div class="panel">
    <p class="msg policy">批次粒度：活动级 sealed 批（按 campaign_code 分批钉扎）；不存在整日级批次。</p>
    <p class="msg err" v-if="err">{{ err }}</p>
    <table>
      <thead>
        <tr><th>批次</th><th>业务日</th><th>粒度</th><th>活动</th><th>状态</th><th>笔数</th><th>合计</th><th>钉扎时刻</th></tr>
      </thead>
      <tbody>
        <tr v-for="b in rows" :key="b.id">
          <td>{{ b.id }}</td>
          <td>{{ b.business_day }}</td>
          <td><span class="tag">{{ b.scope === 'campaign' ? '活动批' : '整日批' }}</span></td>
          <td>{{ b.campaign_code || '—' }}</td>
          <td><span class="tag ok">{{ b.status }}</span></td>
          <td>{{ b.fact_count }}</td>
          <td>{{ Number(b.total_amount || 0).toFixed(2) }}</td>
          <td>{{ b.sealed_at }}</td>
        </tr>
        <tr v-if="!rows.length"><td colspan="8" class="muted">暂无钉扎批次</td></tr>
      </tbody>
    </table>
  </div>
</template>
