<script setup lang="ts">
import { ref, computed, nextTick, onMounted, onUnmounted } from 'vue'
import * as echarts from 'echarts'
import type { ECharts } from 'echarts'
import { getLatestFactorScores, getFactorScoresHistory} from '../api/analysis'
import type { FactorDetail } from '../api/analysis'

const factorDetail = ref<FactorDetail[]>([])
const compositeIndex = ref<number | null>(null)
const factorUpdatedAt = ref('')
const compositeHistory = ref<{ x: string; y: number }[]>([])

// 维度说明
const FACTOR_DESCRIPTIONS: Record<string, string> = {
  geopolitical:       '地缘政治：中东局势、盟友关系、制裁与军事部署等外部压力（含 Brent-WTI 价差反映地缘溢价）',
  domestic_political: '国内政治：支持率、国会博弈、弹劾风险及党内凝聚力',
  financial_market:   '金融市场：股指、VIX波动率、国债收益率等市场情绪',
  energy_market:      '能源市场：油价走势、通胀压力等能源供应与成本压力',
  decision_team:      '决策团队：核心幕僚稳定性、鹰派/鸽派力量对比',
}

// 自定义权重（初始为 null，表示使用服务端权重）
const customWeights = ref<Record<string, number> | null>(null)
const weightEditMode = ref(false)
const editingWeights = ref<{ key: string; label: string; weight: number }[]>([])

// 基于自定义权重计算综合指数
const customCompositeIndex = computed(() => {
  if (!customWeights.value || !factorDetail.value.length) return null
  const total = Object.values(customWeights.value).reduce((s, v) => s + v, 0)
  if (total === 0) return null
  return factorDetail.value.reduce((sum, d) => {
    const w = (customWeights.value![d.key] ?? 0) / total
    return sum + d.score * w
  }, 0)
})

const displayCompositeIndex = computed(() =>
  customCompositeIndex.value !== null ? customCompositeIndex.value : compositeIndex.value
)

const weightSum = computed(() =>
  editingWeights.value.reduce((s, w) => s + w.weight, 0)
)

const openWeightEditor = () => {
  const base = customWeights.value
  editingWeights.value = factorDetail.value.map(d => ({
    key: d.key,
    label: d.label,
    weight: base ? (base[d.key] ?? d.weight) : d.weight,
  }))
  weightEditMode.value = true
}

const applyWeights = () => {
  if (Math.abs(weightSum.value - 100) > 0.01) return
  customWeights.value = Object.fromEntries(editingWeights.value.map(w => [w.key, w.weight]))
  weightEditMode.value = false
  // 用自定义权重更新雷达图标签
  const merged = factorDetail.value.map(d => ({
    ...d,
    weight: customWeights.value![d.key] ?? d.weight,
  }))
  updateRadarChart(merged)
}

const resetWeights = () => {
  customWeights.value = null
  weightEditMode.value = false
  updateRadarChart(factorDetail.value)
}

// 统一转北京时间（UTC+8）
const toBeijing = (iso: string): Date | null => {
  if (!iso) return null
  const d = new Date(iso)
  return isNaN(d.getTime()) ? null : d
}

const formatTime = (iso: string) => {
  const d = toBeijing(iso)
  if (!d) return '--'
  return d.toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false })
}

let radarChart: ECharts | null = null
let compositeLineChart: ECharts | null = null

const fetchAndUpdateRadarChart = async () => {
  try {
    const res = await getLatestFactorScores()
    if (res) {
      factorDetail.value = res.detail
      compositeIndex.value = res.composite_index
      factorUpdatedAt.value = res.computed_at
      // 若有自定义权重，合并后渲染
      const merged = customWeights.value
        ? res.detail.map(d => ({ ...d, weight: customWeights.value![d.key] ?? d.weight }))
        : res.detail
      updateRadarChart(merged)
      return
    }
  } catch (e) {
    console.error('获取因子得分失败:', e)
  }
  updateRadarChart([])
}

const fetchCompositeHistory = async () => {
  try {
    const history = await getFactorScoresHistory(120)
    compositeHistory.value = history.map(h => ({
      x: new Date(h.computed_at).toLocaleString('zh-CN', {
        timeZone: 'Asia/Shanghai',
        month: 'numeric', day: 'numeric',
        hour: 'numeric', minute: 'numeric',
        hour12: false
      }),
      y: h.composite_index
    }))
    renderCompositeLineChart()
  } catch (e) {
    console.error('获取综合指数历史失败:', e)
  }
}

const renderCompositeLineChart = () => {
  const dom = document.getElementById('composite-line-chart')
  if (!dom) return
  if (!compositeLineChart) {
    compositeLineChart = echarts.init(dom, 'dark')
  }
  const xData = compositeHistory.value.map(h => h.x)
  const yData = compositeHistory.value.map(h => h.y)
  const lo = yData.length ? Math.min(...yData) : 0
  const hi = yData.length ? Math.max(...yData) : 10
  const pad = (hi - lo) * 0.25 || 1
  compositeLineChart.setOption({
    backgroundColor: 'transparent',
    grid: { left: 36, right: 8, top: 8, bottom: 36 },
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#1a2235',
      borderColor: '#2d3f55',
      textStyle: { color: '#e2e8f0', fontSize: 18 }, /* 原 12 → 18 */
      formatter: (params: any) => `${params[0].axisValue}<br/><b>${params[0].value.toFixed(1)}</b>`
    },
    xAxis: {
      type: 'category',
      data: xData,
      axisLabel: { show: false },
      axisLine: { lineStyle: { color: '#2d3f55' } },
      splitLine: { show: false },
    },
    yAxis: {
      type: 'value',
      min: Math.floor(lo - pad),
      max: Math.ceil(hi + pad),
      axisLabel: { color: '#7a90a8', fontSize: 15, formatter: (v: number) => v.toFixed(0) }, /* 原 10 → 15 */
      splitLine: { lineStyle: { color: '#1e2d45', type: 'dashed' } },
    },
    series: [{
      type: 'line',
      data: yData,
      smooth: true,
      symbol: 'none',
      lineStyle: { color: '#3b82f6', width: 2 },
      areaStyle: {
        color: {
          type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [
            { offset: 0, color: 'rgba(59,130,246,0.3)' },
            { offset: 1, color: 'rgba(59,130,246,0.02)' }
          ]
        }
      },
    }],
  }, true)
}


const CHART_DARK = {
  bg: 'transparent',
  textColor: '#7a90a8',
  titleColor: '#e2e8f0',
  splitLineColor: '#1e2d45',
  axisLineColor: '#2d3f55',
}
// ── 指标趋势弹框 ──────────────────────────────────────────────

const updateRadarChart = (detail: FactorDetail[]) => {
  const indicator = detail.length
    ? detail.map(d => ({ name: `${d.label}(${d.weight}%)`, max: 100 }))
    : ['地缘政治','国内政治','金融市场','能源市场','决策团队'].map(n => ({ name: n, max: 100 }))

  const values = detail.length ? detail.map(d => d.score) : [0, 0, 0, 0, 0]

  radarChart?.setOption({
    backgroundColor: 'transparent',
    title: { text: '因子贡献度', textStyle: { color: CHART_DARK.titleColor, fontSize: 24, fontWeight: 700 }, }, /* 原 16 → 24 */
    tooltip: {
      trigger: 'item',
      backgroundColor: '#1a2235',
      borderColor: '#2d3f55',
      textStyle: { color: '#e2e8f0', fontSize: 20 }, /* 原 13 → 20 */
      formatter: (params: any) => {
        if (!detail.length) return ''
        const vals: number[] = params.value
        return detail.map((d, i) => `${d.label}：<b>${(vals[i] ?? 0).toFixed(1)}</b>　权重 ${d.weight}%`).join('<br/>')
      }
    },
    radar: {
      indicator,
      splitNumber: 4,
      axisName: { fontSize: 20, color: CHART_DARK.textColor }, /* 原 13 → 20 */
      splitLine: { lineStyle: { color: CHART_DARK.splitLineColor } },
      splitArea: { areaStyle: { color: ['rgba(30,45,69,0.3)', 'rgba(30,45,69,0.1)'] } },
      axisLine: { lineStyle: { color: CHART_DARK.axisLineColor } },
    },
    series: [{
      type: 'radar',
      data: [{
        value: values,
        name: '当前影响因子',
        itemStyle: { color: '#3b82f6' },
        lineStyle: { color: '#3b82f6', width: 2 },
        areaStyle: { color: 'rgba(59,130,246,0.2)' },
        label: { show: true, formatter: (p: any) => p.value.toFixed(1), fontSize: 20, fontWeight: 700, color: '#60a5fa' }, /* 原 13 → 20 */
      }]
    }]
  })
}

const scoreColor = (score: number) => {
  if (score >= 70) return '#f56c6c'
  if (score >= 40) return '#e6a23c'
  return '#67c23a'
}

const onResize = () => {
  radarChart?.resize()
  compositeLineChart?.resize()
}


let intervals: ReturnType<typeof setInterval>[] = []

onMounted(async () => {
  await nextTick()

  const radarChartDom = document.getElementById('radar-chart') as HTMLElement
  radarChart = echarts.init(radarChartDom, 'dark')
  fetchAndUpdateRadarChart()
  fetchCompositeHistory()
  intervals.push(setInterval(fetchAndUpdateRadarChart, 30000))
  intervals.push(setInterval(fetchCompositeHistory, 60000))

  window.addEventListener('resize', onResize)
})

onUnmounted(() => {
  intervals.forEach(clearInterval)
  window.removeEventListener('resize', onResize)
})
</script>

<template>
  <div class="dashboard">

    <!-- <div class="section-title">决策压力分析</div> -->
    <el-card class="factor-card-wrap" style="margin-bottom:20px;">
      <el-row :gutter="16">

        <!-- 左：综合指数趋势 -->
        <el-col :span="10">
          <div class="composite-trend-header">
            <div class="composite-trend-title">
              综合决策压力指数
              <span v-if="displayCompositeIndex !== null"
                class="composite-badge"
                :style="{ background: scoreColor(displayCompositeIndex) + '22', color: scoreColor(displayCompositeIndex), borderColor: scoreColor(displayCompositeIndex) + '55' }">
                {{ displayCompositeIndex.toFixed(1) }}
              </span>
              <span v-if="customWeights" class="custom-weight-tag">自定义权重</span>
            </div>
            <div class="composite-trend-desc">
              综合 5 个维度的加权得分（0–100），反映当前特朗普采取强硬行动的综合压力。
              <b style="color:#ef4444;">≥70</b> 高压，
              <b style="color:#e6a23c;">40–70</b> 中压，
              <b style="color:#67c23a;">&lt;40</b> 低压。
            </div>
          </div>
          <div id="composite-line-chart" style="width:100%; height:220px;"></div>
          <div class="composite-trend-footer">
            更新于 {{ formatTime(factorUpdatedAt) }}
          </div>
        </el-col>

        <!-- 中：雷达图 + 维度说明 -->
        <el-col :span="8">
          <div id="radar-chart" style="width:100%; height:300px;"></div>
          <div class="factor-desc-list">
            <div v-for="item in factorDetail" :key="item.key" class="factor-desc-item">
              <span class="factor-desc-dot" :style="{ background: scoreColor(item.score) }"></span>
              <span class="factor-desc-text">{{ FACTOR_DESCRIPTIONS[item.key] || item.label }}</span>
            </div>
          </div>
        </el-col>

        <!-- 右：权重调整 -->
        <el-col :span="6" style="display:flex; flex-direction:column; justify-content:center;">
          <div v-if="factorDetail.length" class="factor-inline-col">
            <div v-if="weightEditMode" class="weight-editor">
              <div class="weight-editor-title">
                调整权重
                <span :class="['weight-sum-badge', Math.abs(weightSum - 100) < 0.01 ? 'ok' : 'err']">
                  合计 {{ weightSum }}%
                </span>
              </div>
              <div v-for="w in editingWeights" :key="w.key" class="weight-row">
                <span class="weight-row-label">{{ w.label }}</span>
                <el-input-number
                  v-model="w.weight"
                  :min="0" :max="100" :step="1" :precision="0"
                  size="small"
                  controls-position="right"
                  style="width:100px;"
                />
                <span class="weight-row-pct">%</span>
              </div>
              <div class="weight-editor-actions">
                <el-button size="small" type="primary" :disabled="Math.abs(weightSum - 100) > 0.01" @click="applyWeights">应用</el-button>
                <el-button size="small" @click="weightEditMode = false">取消</el-button>
              </div>
            </div>

            <template v-else>
              <div class="factor-card-inline" v-for="item in factorDetail" :key="item.key">
                <div class="factor-label-row">
                  <span class="factor-label">{{ item.label }}</span>
                  <span class="factor-weight">{{ customWeights ? customWeights[item.key] : item.weight }}%</span>
                </div>
                <div class="factor-score-inline" :style="{ color: scoreColor(item.score) }">{{ item.score.toFixed(1) }}</div>
                <el-progress :percentage="item.score" :color="scoreColor(item.score)" :show-text="false" style="margin:4px 0 0;" />
              </div>
              <div class="weight-btn-row">
                <el-button size="small" plain @click="openWeightEditor">调整权重</el-button>
                <el-button v-if="customWeights" size="small" plain @click="resetWeights">重置</el-button>
              </div>
            </template>
          </div>
        </el-col>

      </el-row>
    </el-card>

  </div>
</template>


<style scoped>
.dashboard { padding: 4px 0; }

.section-title {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary, #e2e8f0);
  margin: 0 0 12px 2px;
  letter-spacing: 0.5px;
}

.factor-inline-col {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
}

.factor-card-inline {
  flex: 1;
  min-width: 0;
  text-align: center;
  padding: 8px 10px;
  border-radius: 6px;
  background: var(--bg-card, #111827);
  border: 1px solid var(--border, #1e2d45);
}

.factor-label-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 2px;
}

.factor-label {
  font-size: 17px; /* 原 11px 加大 50% */
  font-weight: 600;
  color: var(--text-secondary, #7a90a8);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.factor-score-inline {
  font-size: 27px; /* 原 18px 加大 50% */
  font-weight: 800;
  line-height: 1.2;
}

.factor-weight {
  font-size: 15px; /* 原 10px 加大 50% */
  color: var(--text-muted, #4a5a6e);
}

.composite-trend-header { padding: 0 0 8px 0; }

.composite-trend-title {
  font-size: 21px; /* 原 14px 加大 50% → 21 */
  font-weight: 700;
  color: var(--text-primary, #e2e8f0);
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.composite-badge {
  font-size: 27px; /* 原 18px 加大 50% → 27 */
  font-weight: 800;
  padding: 1px 10px;
  border-radius: 6px;
  border: 1px solid;
  line-height: 1.4;
}

.composite-trend-desc {
  font-size: 17px; /* 原 11px 加大 50% → 17 */
  color: var(--text-muted, #4a5a6e);
  line-height: 1.6;
}

.composite-trend-footer {
  font-size: 15px; /* 原 10px 加大 50% → 15 */
  color: var(--text-muted, #4a5a6e);
  text-align: right;
  margin-top: 4px;
}

.factor-desc-list {
  margin-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 5px;
  padding: 0 4px;
}

.factor-desc-item {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  font-size: 17px; /* 原 11px 加大 50% → 17 */
  color: var(--text-muted, #4a5a6e);
  line-height: 1.5;
}

.factor-desc-dot {
  flex-shrink: 0;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  margin-top: 4px;
}

.factor-desc-text { flex: 1; }

.custom-weight-tag {
  font-size: 15px; /* 原 10px 加大 50% → 15 */
  font-weight: 600;
  color: #f59e0b;
  background: rgba(245,158,11,0.12);
  border: 1px solid rgba(245,158,11,0.3);
  border-radius: 4px;
  padding: 1px 6px;
}

.weight-editor {
  background: var(--bg-card, #111827);
  border: 1px solid var(--border, #1e2d45);
  border-radius: 8px;
  padding: 10px 12px;
  width: 100%;
}

.weight-editor-title {
  font-size: 18px; /* 原 12px 加大 50% → 18 */
  font-weight: 700;
  color: var(--text-secondary, #7a90a8);
  margin-bottom: 10px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.weight-sum-badge {
  font-size: 17px; /* 原 11px 加大 50% → 17 */
  font-weight: 600;
  padding: 1px 7px;
  border-radius: 4px;
}
.weight-sum-badge.ok { color: #67c23a; background: rgba(103,194,58,0.12); border: 1px solid rgba(103,194,58,0.3); }
.weight-sum-badge.err { color: #f56c6c; background: rgba(245,108,108,0.12); border: 1px solid rgba(245,108,108,0.3); }

.weight-row { display: flex; align-items: center; gap: 6px; margin-bottom: 7px; }

.weight-row-label {
  flex: 1;
  font-size: 17px; /* 原 11px 加大 50% → 17 */
  color: var(--text-secondary, #7a90a8);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.weight-row-pct { font-size: 17px; /* 原 11px 加大 50% → 17 */ color: var(--text-muted, #4a5a6e); }

.weight-editor-actions { display: flex; gap: 6px; margin-top: 10px; justify-content: flex-end; }

.weight-btn-row { display: flex; gap: 6px; margin-top: 6px; justify-content: flex-end; }

.factor-card-wrap :deep(.el-card__body) { padding: 16px; }
</style>
