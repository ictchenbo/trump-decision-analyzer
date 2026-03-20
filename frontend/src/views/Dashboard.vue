<script setup lang="ts">
import { ref, computed, nextTick, onMounted, onUnmounted } from 'vue'
import * as echarts from 'echarts'
import type { ECharts } from 'echarts'
import { getRealTimeData, getRealTimeHistory, type Granularity } from '../api/data'
import { getTrumpStatements } from '../api/trump_statements'

interface RealTimeData {
  name: string
  value: number
  unit: string
  trend: 'up' | 'down' | 'stable' | 'unknown'
  updated_at: string
  source?: string
  prev_value?: number | null
  prev_time?: string | null
  change?: number | null
  change_pct?: number | null
}

interface Statement {
  content: string
  source: string
  post_time: string
  translation?: string
}

const realTimeData = ref<RealTimeData[]>([])
const statements = ref<Statement[]>([])
const tickerText = ref('')
const tickerDuration = ref('100s')

// 统一转北京时间（UTC+8）
const toBeijing = (iso: string): Date | null => {
  if (!iso) return null
  const d = new Date(iso)
  return isNaN(d.getTime()) ? null : d
}

// 短格式：M/D HH:mm，用于指标卡片
const formatShortTime = (iso: string) => {
  const d = toBeijing(iso)
  if (!d) return '--'
  return d.toLocaleString('zh-CN', {
    timeZone: 'Asia/Shanghai',
    month: 'numeric', day: 'numeric',
    hour: 'numeric', minute: 'numeric',
    hour12: false
  })
}

const SOURCE_MAP: Record<string, string> = {
  '布伦特原油期货': 'ICE Futures',
  '纽约原油期货': 'NYMEX',
  '美元指数': 'ICE',
  'RBOB汽油价格': 'NYMEX',
  '纽约黄金': 'COMEX',
  '标普500': 'NYSE',
  '纳斯达克指数': 'NASDAQ',
  '道琼斯指数': 'NYSE',
  '波动率指数VIX': 'CBOE',
  '布油-WTI地缘溢价': 'Yahoo Finance (Brent-WTI Spread)',
  '10年期国债收益率': 'U.S. Treasury',
  '2年期国债收益率': 'U.S. Treasury',
  '特朗普支持率': 'Wikipedia',
  'Polymarket弹劾概率': 'Polymarket',
  'CPI同比': 'U.S. BLS',
  '非农就业': 'U.S. BLS',
  '失业率': 'U.S. BLS',
}

const getSource = (item: RealTimeData) => item.source || SOURCE_MAP[item.name] || ''

// 按指标名分组，定义展示顺序
const METRIC_GROUPS = [
  { label: '股票市场', names: ['纳斯达克指数', '道琼斯指数', '波动率指数VIX'] },
  { label: '能源 & 地缘', names: ['布伦特原油期货', '纽约原油期货', '美元指数', 'RBOB汽油价格', '纽约黄金', '布油-WTI地缘溢价'] },
  { label: '政治 & 民调', names: ['特朗普支持率', 'Polymarket弹劾概率'] },
  { label: '宏观经济', names: ['2年期国债收益率', '10年期国债收益率', 'CPI同比'] },
]

const groupedMetrics = computed(() => {
  const map = Object.fromEntries(realTimeData.value.map(d => [d.name, d]))
  return METRIC_GROUPS.map(g => ({
    label: g.label,
    items: g.names.map(n => map[n]).filter((x): x is RealTimeData => !!x),
  })).filter(g => g.items.length > 0)
})

const formatValue = (item: RealTimeData) => {
  const v = item.value
  // 大数字（股指、黄金）加千分位
  if (['标普500', '纳斯达克指数', '道琼斯指数', '纽约黄金'].includes(item.name)) {
    return v.toLocaleString('en-US', { maximumFractionDigits: 0 })
  }
  // 非农就业：月度新增，保留1位小数，加正负号
  if (item.name === '非农就业') {
    const sign = v > 0 ? '+' : ''
    return sign + v.toFixed(1)
  }
  // Polymarket 概率保留1位
  if (item.name === 'Polymarket弹劾概率') return v.toFixed(1)
  // 美元指数保留2位
  if (item.name === '美元指数') return v.toFixed(2)
  // 其余保留2位
  return v.toFixed(2)
}

// 涨跌点数：大数字加千分位，小数字保留2位
const formatChange = (item: RealTimeData): string => {
  const c = item.change
  if (c == null) return ''
  const sign = c > 0 ? '+' : ''
  if (['标普500', '纳斯达克', '道琼斯', '黄金价格'].includes(item.name)) {
    return sign + c.toLocaleString('en-US', { maximumFractionDigits: 0 })
  }
  return sign + c.toFixed(2)
}

const formatChangePct = (item: RealTimeData): string => {
  const p = item.change_pct
  if (p == null) return ''
  const sign = p > 0 ? '+' : ''
  return `${sign}${p.toFixed(2)}%`
}

const formatPostTime = (iso: string) => {
  const d = toBeijing(iso)
  if (!d) return ''
  return d.toLocaleString('zh-CN', {
    timeZone: 'Asia/Shanghai',
    month: 'numeric', day: 'numeric',
    hour: 'numeric', minute: 'numeric',
    hour12: false
  })
}

let modalChart: ECharts | null = null

const fetchRealTimeData = async () => {
  try {
    const data = await getRealTimeData()
    realTimeData.value = data || []
  } catch (error) {
    console.error('获取实时数据失败:', error)
    realTimeData.value = [
      { name: '布伦特原油', value: 98.5, unit: '美元/桶', trend: 'up', updated_at: new Date().toISOString() },
      { name: '标普500', value: 4720.25, unit: '点', trend: 'down', updated_at: new Date().toISOString() },
      { name: '特朗普支持率', value: 42.3, unit: '%', trend: 'stable', updated_at: new Date().toISOString() },
      { name: 'VIX指数', value: 22.7, unit: '', trend: 'up', updated_at: new Date().toISOString() },
      { name: '地缘风险溢价', value: 4.2, unit: '美元/桶', trend: 'up', updated_at: new Date().toISOString() },
      { name: '非农就业', value: 177.0, unit: '千人', trend: 'up', updated_at: new Date().toISOString() }
    ]
  }
}

const fetchStatements = async () => {
  try {
    const res = await getTrumpStatements(undefined, undefined, undefined, 10, 0)
    statements.value = res?.statements || []
    if (statements.value.length) {
      tickerText.value = statements.value
        .map(s => `【${s.source} · ${formatPostTime(s.post_time)}】${s.translation || s.content}`)
        .join('　　　　')
      // 按字符数动态计算时长，约 8px/字符，目标速度 80px/s
      const charCount = tickerText.value.length
      const estimatedPx = charCount * 8 + window.innerWidth
      tickerDuration.value = Math.round(estimatedPx / 80) + 's'
    }
  } catch (e) {
    console.error('获取言论失败:', e)
  }
}

const CHART_DARK = {
  bg: 'transparent',
  textColor: '#7a90a8',
  titleColor: '#e2e8f0',
  splitLineColor: '#1e2d45',
  axisLineColor: '#2d3f55',
}

const modalVisible = ref(false)
const modalItem = ref<RealTimeData | null>(null)
const modalGranularity = ref<Granularity>('day')
const modalLoading = ref(false)

const GRANULARITY_OPTIONS: { label: string; value: Granularity }[] = [
  { label: '分钟', value: 'minute' },
  { label: '小时', value: 'hour' },
  { label: '天',   value: 'day'  },
  { label: '周',   value: 'week' },
]

const GRANULARITY_LIMIT: Record<Granularity, number> = {
  minute: 120,
  hour:   72,
  day:    60,
  week:   52,
}

// 各指标的粒度配置：{ options: 可用粒度, default: 默认粒度, note?: 说明 }
const METRIC_GRANULARITY: Record<string, { options: Granularity[]; default: Granularity; note?: string }> = {
  // 股票市场：每30秒采集，分钟粒度最清晰
  '标普500':         { options: ['minute','hour','day','week'], default: 'minute' },
  '纳斯达克指数':    { options: ['minute','hour','day','week'], default: 'minute' },
  '道琼斯指数':      { options: ['minute','hour','day','week'], default: 'minute' },
  '波动率指数VIX':   { options: ['minute','hour','day','week'], default: 'minute' },
  // 能源 & 汇率：每30秒采集
  '布伦特原油期货':  { options: ['minute','hour','day','week'], default: 'minute' },
  '纽约原油期货':    { options: ['minute','hour','day','week'], default: 'minute' },
  '美元指数':        { options: ['minute','hour','day','week'], default: 'minute' },
  'RBOB汽油价格':    { options: ['minute','hour','day','week'], default: 'minute' },
  '纽约黄金':        { options: ['minute','hour','day','week'], default: 'minute' },
  '10年期国债收益率': { options: ['minute','hour','day','week'], default: 'minute' },
  '2年期国债收益率': { options: ['minute','hour','day','week'], default: 'minute' },
  // 地缘风险溢价：Brent-WTI 价差，来自 Yahoo Finance，支持分钟级
  '布油-WTI地缘溢价': { options: ['minute','hour','day','week'], default: 'minute', note: '布伦特-纽约原油价差，反映中东地缘溢价' },
  // 政治民调：更新频率较低
  '特朗普支持率': { options: ['day','week'], default: 'week', note: 'Wikipedia 民调聚合，通常每周或每月更新' },
  'Polymarket弹劾概率': { options: ['hour','day','week'], default: 'day', note: 'Polymarket 预测市场，价格随交易实时变动' },
  // BLS 月度数据（每月第一个周五发布）
  'CPI同比':  { options: ['day','week'], default: 'day', note: 'BLS 月度发布，反映通胀水平' },
}

const getMetricGranularityConfig = (name: string) => {
  return METRIC_GRANULARITY[name] ?? { options: ['minute','hour','day','week'] as Granularity[], default: 'day' as Granularity }
}

const modalGranularityOptions = computed(() =>
  GRANULARITY_OPTIONS.filter(o => getMetricGranularityConfig(modalItem.value?.name ?? '').options.includes(o.value))
)

const modalNote = computed(() => getMetricGranularityConfig(modalItem.value?.name ?? '').note ?? '')

const openMetricModal = async (item: RealTimeData) => {
  modalItem.value = item
  modalGranularity.value = getMetricGranularityConfig(item.name).default
  modalVisible.value = true
  await nextTick()
  await loadModalChart()
}

const loadModalChart = async () => {
  if (!modalItem.value) return
  modalLoading.value = true
  try {
    const g = modalGranularity.value
    const history = await getRealTimeHistory(modalItem.value.name, g, GRANULARITY_LIMIT[g])
    const xData = history.map(d => {
      const dt = new Date(d.updated_at)
      if (isNaN(dt.getTime())) return ''
      // BLS 月度数据：CPI 同比，显示 YYYY-MM
      const monthlyMetrics = ['CPI同比']
      if (monthlyMetrics.includes(modalItem.value?.name ?? '')) {
        return dt.toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit' }).replace('/', '-')
      }
      if (g === 'week' || g === 'day') {
        return dt.toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', month: 'numeric', day: 'numeric', hour12: false })
      }
      return dt.toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', month: 'numeric', day: 'numeric', hour: 'numeric', minute: 'numeric', hour12: false })
    })
    const yData = history.map(d => d.value)
    renderModalChart(xData, yData)
  } catch (e) {
    console.error('加载趋势图失败:', e)
    renderModalChart([], [])
  } finally {
    modalLoading.value = false
  }
}

// 计算 yAxis 的合理 min/max：以数据范围为基础，向外扩展 20%，使波动更清晰
const calcYAxisRange = (yData: number[]): { min: number; max: number; decimals: number } => {
  const valid = yData.filter(v => v != null && !isNaN(v))
  if (valid.length === 0) return { min: 0, max: 100, decimals: 2 }

  const lo = Math.min(...valid)
  const hi = Math.max(...valid)
  const range = hi - lo

  // 数据完全相同时给一个默认范围
  if (range === 0) {
    const pad = Math.abs(lo) * 0.02 || 1
    return { min: lo - pad, max: hi + pad, decimals: 2 }
  }

  const pad = range * 0.2
  const rawMin = lo - pad
  const rawMax = hi + pad

  // 根据数值大小决定小数位数
  let decimals = 2
  if (range < 0.1)       decimals = 4
  else if (range < 1)    decimals = 3
  else if (range >= 100) decimals = 0

  // 对齐到合适的刻度步长
  const step = range / 4  // 约4个刻度
  const magnitude = Math.pow(10, Math.floor(Math.log10(step)))
  const niceStep = Math.ceil(step / magnitude) * magnitude
  const niceMin = Math.floor(rawMin / niceStep) * niceStep
  const niceMax = Math.ceil(rawMax / niceStep) * niceStep

  return { min: niceMin, max: niceMax, decimals }
}

const renderModalChart = (xData: string[], yData: number[]) => {
  const dom = document.getElementById('modal-chart')
  if (!dom) return
  if (!modalChart) {
    modalChart = echarts.init(dom, 'dark')
  } else {
    modalChart.resize()
  }
  const unit = modalItem.value?.unit || ''
  const { min, max, decimals } = calcYAxisRange(yData)

  // tooltip 格式：大数字加千分位
  const name = modalItem.value?.name || ''
  const BIG_NAMES = new Set(['标普500', '纳斯达克指数', '道琼斯指数', '纽约黄金'])
  const fmtVal = (v: number) => {
    if (BIG_NAMES.has(name)) return v.toLocaleString('en-US', { maximumFractionDigits: 0 }) + unit
    return v.toFixed(decimals) + unit
  }

  modalChart.setOption({
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#1a2235',
      borderColor: '#2d3f55',
      textStyle: { color: '#e2e8f0', fontSize: 20 }, /* 原 13 加大 50% */
      formatter: (params: any) => {
        const p = params[0]
        return `${p.axisValue}<br/><b>${fmtVal(p.value)}</b>`
      }
    },
    grid: { left: 72, right: 16, top: 16, bottom: 48 },
    xAxis: {
      type: 'category',
      data: xData,
      axisLabel: { color: CHART_DARK.textColor, fontSize: 17, rotate: xData.length > 30 ? 30 : 0 }, /* 原 11 → 17 */
      axisLine: { lineStyle: { color: CHART_DARK.axisLineColor } },
      splitLine: { show: false },
    },
    yAxis: {
      type: 'value',
      min,
      max,
      axisLabel: {
        color: CHART_DARK.textColor,
        fontSize: 17, /* 原 11 → 17 */
        formatter: (v: number) => {
          if (BIG_NAMES.has(name)) return v.toLocaleString('en-US', { maximumFractionDigits: 0 })
          return v.toFixed(decimals) + unit
        }
      },
      splitLine: { lineStyle: { color: CHART_DARK.splitLineColor, type: 'dashed' } },
    },
    series: [{
      type: 'line',
      data: yData,
      smooth: true,
      symbol: yData.length <= 30 ? 'circle' : 'none',
      symbolSize: 4,
      lineStyle: { color: '#3b82f6', width: 2 },
      areaStyle: {
        color: {
          type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [
            { offset: 0, color: 'rgba(59,130,246,0.25)' },
            { offset: 1, color: 'rgba(59,130,246,0.02)' }
          ]
        }
      },
    }],
  }, true)
}

const onModalClose = (done: () => void) => {
  modalChart?.dispose()
  modalChart = null
  done()
}

const onGranularityChange = () => loadModalChart()

const onResize = () => {
  modalChart?.resize()
}

let intervals: ReturnType<typeof setInterval>[] = []

onMounted(async () => {
  fetchRealTimeData()
  fetchStatements()
  intervals.push(setInterval(fetchRealTimeData, 30000))
  intervals.push(setInterval(fetchStatements, 60000))

  window.addEventListener('resize', onResize)
})

onUnmounted(() => {
  intervals.forEach(clearInterval)
  window.removeEventListener('resize', onResize)
})
</script>

<template>
  <div class="dashboard">
    <!-- 言论滚动条 -->
    <div class="ticker-bar" v-show="statements.length">
      <span class="ticker-label">最新言论</span>
      <div class="ticker-track">
        <span class="ticker-text" :style="{ animationDuration: tickerDuration }">{{ tickerText }}</span>
      </div>
    </div>

    <!-- 实时数据卡片（分组） -->
    <div class="section-title">实时关键指标</div>
    <div class="metrics-groups" style="margin-bottom: 20px;">
      <div class="metric-group" v-for="group in groupedMetrics" :key="group.label">
        <div class="metric-group-label">{{ group.label }}</div>
        <div class="metric-group-cards">
          <div class="metric-card" v-for="item in group.items" :key="item.name" @click="openMetricModal(item)">
            <div class="metric-name">{{ item.name }}</div>
            <div class="metric-value">
              {{ formatValue(item) }}<span class="metric-unit">{{ item.unit }}</span>
            </div>
            <!-- 非农就业：月度新增，正红负绿，不显示环比变化行 -->
            <template v-if="item.name === '非农就业'">
              <div class="metric-change-row" :class="item.value >= 0 ? 'up' : 'down'">
                <span class="change-arrow">{{ item.value >= 0 ? '▲' : '▼' }}</span>
                <span class="change-abs">月度新增</span>
              </div>
            </template>
            <template v-else>
              <div class="metric-change-row" :class="item.trend">
                <template v-if="item.change != null">
                  <span class="change-arrow">{{ item.trend === 'up' ? '▲' : item.trend === 'down' ? '▼' : '—' }}</span>
                  <span class="change-abs">{{ formatChange(item) }}</span>
                  <span class="change-pct">{{ formatChangePct(item) }}</span>
                </template>
                <span v-else class="change-na">— —</span>
              </div>
            </template>
            <div class="metric-source" v-if="getSource(item)">{{ getSource(item) }}</div>
            <div class="metric-updated">{{ formatShortTime(item.updated_at) }} CST</div>
          </div>
        </div>
      </div>
    </div>

    <!-- 指标趋势弹框 -->
    <el-dialog
      v-model="modalVisible"
      :title="modalItem ? modalItem.name + ' 历史趋势' : ''"
      width="760px"
      :before-close="onModalClose"
      destroy-on-close
    >
      <!-- BLS 月度数据：固定月度，无需粒度选择器 -->
      <div v-if="['CPI同比'].includes(modalItem?.name ?? '')" style="display:flex; align-items:center; gap:8px; margin-bottom:16px; flex-wrap:wrap;">
        <span style="font-size:18px; color:#7a90a8; padding:4px 10px; background:#1a2235; border-radius:4px; border:1px solid #1e2d45;">
          📅 月度数据（每月发布一次）
        </span>
        <span style="margin-left:auto; font-size:18px; color:#4a5a6e;">
          {{ modalItem?.source || '' }}
        </span>
      </div>
      <!-- 其他指标：显示粒度选择器 -->
      <div v-else style="display:flex; align-items:center; gap:8px; margin-bottom:16px; flex-wrap:wrap;">
        <span style="font-size:20px; color:#7a90a8;">粒度：</span>
        <el-radio-group v-model="modalGranularity" size="small" @change="onGranularityChange">
          <el-radio-button
            v-for="opt in modalGranularityOptions"
            :key="opt.value"
            :value="opt.value"
          >{{ opt.label }}</el-radio-button>
        </el-radio-group>
        <span v-if="modalNote" style="font-size:17px; color:#4a5a6e; padding:2px 8px; background:#1a2235; border-radius:4px; border:1px solid #1e2d45;">
          {{ modalNote }}
        </span>
        <span v-if="modalItem" style="margin-left:auto; font-size:18px; color:#4a5a6e;">
          {{ modalItem?.source || '' }}
        </span>
      </div>
      <div v-loading="modalLoading" style="height:320px;">
        <div id="modal-chart" style="width:100%; height:320px;"></div>
      </div>
    </el-dialog>
  </div>
</template>

<style scoped>
.dashboard {
  padding: 4px 0;
}

.section-title {
  font-size: 27px; /* 原 18px 加大 50% */
  font-weight: 700;
  color: var(--text-primary, #e2e8f0);
  margin: 0 0 12px 2px;
  letter-spacing: 0.5px;
}

.metrics-groups {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.metric-group-label {
  font-size: 18px; /* 原 12px 加大 50% */
  font-weight: 600;
  color: var(--text-muted, #4a5a6e);
  text-transform: uppercase;
  letter-spacing: 0.8px;
  margin-bottom: 8px;
}

.metric-group-cards {
  display: flex;
  gap: 12px;
  flex-wrap: nowrap;
}

.metric-card {
  flex: 1;
  min-width: 0;
  background: var(--bg-card, #111827);
  border: 1px solid var(--border, #1e2d45);
  border-radius: 8px;
  padding: 12px 10px;
  text-align: center;
  cursor: pointer;
  transition: border-color 0.2s;
}

.metric-card:hover {
  border-color: var(--accent, #3b82f6);
  transform: translateY(-1px);
  transition: transform 0.15s, border-color 0.15s;
}

.metric-name {
  font-size: 18px; /* 原 12px 加大 50% */
  color: var(--text-secondary, #7a90a8);
  margin-bottom: 6px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.metric-value {
  font-size: 30px; /* 原 20px 加大 50% */
  font-weight: 800;
  color: var(--text-primary, #e2e8f0);
  line-height: 1.2;
  margin-bottom: 4px;
  white-space: nowrap;
}

.metric-unit {
  font-size: 17px; /* 原 11px 加大 50% */
  font-weight: 400;
  color: var(--text-secondary, #7a90a8);
  margin-left: 2px;
}

.metric-change-row {
  display: flex;
  align-items: baseline;
  gap: 3px;
  margin-bottom: 4px;
  font-weight: 600;
  font-size: 18px; /* 原 12px 加大 50% */
}
.metric-change-row.up    { color: #ef4444; }
.metric-change-row.down  { color: #22c55e; }
.metric-change-row.stable,
.metric-change-row.unknown { color: #64748b; }

.change-arrow { font-size: 15px; } /* 原 10px 加大 50% */
.change-abs   { font-size: 18px; } /* 原 12px 加大 50% */
.change-pct   { font-size: 17px; opacity: 0.8; } /* 原 11px 加大 50% */
.change-na    { font-size: 18px; color: #64748b; } /* 原 12px 加大 50% */

.metric-source {
  font-size: 15px; /* 原 10px 加大 50% */
  color: var(--text-muted, #4a5a6e);
  margin-top: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.metric-updated {
  font-size: 15px; /* 原 10px 加大 50% */
  color: var(--text-muted, #4a5a6e);
  margin-top: 3px;
  white-space: nowrap;
}

.ticker-bar {
  display: flex;
  align-items: center;
  background: #0f1923;
  border: 1px solid #1e2d45;
  border-radius: 6px;
  margin-bottom: 20px;
  height: 44px;
  overflow: hidden;
}

.ticker-label {
  flex-shrink: 0;
  padding: 0 18px;
  font-size: 21px; /* 原 14px 加大 50% */
  font-weight: 700;
  color: #fff;
  background: #c0392b;
  height: 100%;
  display: flex;
  align-items: center;
  white-space: nowrap;
  letter-spacing: 1px;
}

.ticker-track {
  flex: 1;
  overflow: hidden;
  height: 100%;
}

.ticker-text {
  display: inline-block;
  white-space: nowrap;
  color: #a0b4c8;
  font-size: 21px; /* 原 14px 加大 50% */
  line-height: 44px;
  animation: ticker-scroll 100s linear infinite;
}

@keyframes ticker-scroll {
  0%   { transform: translateX(100vw); }
  100% { transform: translateX(-100%); }
}

:deep(.el-dialog) {
  background: var(--bg-card, #111827) !important;
  border: 1px solid var(--border, #1e2d45) !important;
  border-radius: 10px !important;
}

:deep(.el-dialog__header) {
  padding: 16px 20px 12px !important;
  border-bottom: 1px solid var(--border, #1e2d45) !important;
}

:deep(.el-dialog__title) {
  font-size: 24px !important; /* 原 16px 加大 50% */
  font-weight: 700 !important;
  color: var(--text-primary, #e2e8f0) !important;
}

:deep(.el-dialog__body) {
  padding: 16px 20px 20px !important;
}

:deep(.el-radio-button__inner) {
  background: transparent !important;
  border-color: var(--border, #1e2d45) !important;
  color: var(--text-secondary, #7a90a8) !important;
  font-size: 18px !important; /* 原 12px 加大 50% */
}

:deep(.el-radio-button__original-radio:checked + .el-radio-button__inner) {
  background: var(--accent, #3b82f6) !important;
  border-color: var(--accent, #3b82f6) !important;
  color: #fff !important;
  box-shadow: none !important;
}
</style>
