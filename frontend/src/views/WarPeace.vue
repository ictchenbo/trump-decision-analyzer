<script setup lang="ts">
import { ref, computed, nextTick, onMounted, onUnmounted } from 'vue'
import * as echarts from 'echarts'
import type { ECharts } from 'echarts'
import { getLatestWarPeaceScores, getWarPeaceHistory } from '../api/analysis'
import type { FactorDetail } from '../api/analysis'
import request from '../utils/request'

interface TrumpImage {
  url: string
  title: string
  source_url: string
  crawled_at: string
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

let warPeaceRadarChart: ECharts | null = null
let warPeaceLineChart: ECharts | null = null

const CHART_DARK = {
  bg: 'transparent',
  textColor: '#7a90a8',
  titleColor: '#e2e8f0',
  splitLineColor: '#1e2d45',
  axisLineColor: '#2d3f55',
}

const onResize = () => {
  warPeaceRadarChart?.resize()
  warPeaceLineChart?.resize()
}

const warPeaceDetail = ref<FactorDetail[]>([])
const warPeaceIndex = ref<number | null>(null)
const warPeaceUpdatedAt = ref('')
const warPeaceHistory = ref<{ x: string; y: number }[]>([])

const WAR_PEACE_DESCRIPTIONS: Record<string, string> = {
  rhetoric:           '言辞强硬度：言论中军事威胁、制裁、极限施压等鹰派词汇的密度',
  military_signal:    '军事信号：油价走势与 Polymarket 军事行动预测市场的综合信号',
  economic_pressure:  '经济施压：VIX 恐慌指数与关税/制裁言论词频反映的经济战倾向',
  diplomatic_stance:  '外交姿态：支持率低迷与弹劾风险驱动的对外强硬转移动机',
  domestic_motivation:'国内政治动机：失业率与通胀压力形成的对外强硬内部驱动力',
}

const wpCustomWeights = ref<Record<string, number> | null>(null)
const wpWeightEditMode = ref(false)
const wpEditingWeights = ref<{ key: string; label: string; weight: number }[]>([])

const wpCustomCompositeIndex = computed(() => {
  if (!wpCustomWeights.value || !warPeaceDetail.value.length) return null
  const total = Object.values(wpCustomWeights.value).reduce((s, v) => s + v, 0)
  if (total === 0) return null
  return warPeaceDetail.value.reduce((sum, d) => {
    const w = (wpCustomWeights.value![d.key] ?? 0) / total
    return sum + d.score * w
  }, 0)
})

const wpDisplayIndex = computed(() =>
  wpCustomCompositeIndex.value !== null ? wpCustomCompositeIndex.value : warPeaceIndex.value
)

const wpWeightSum = computed(() =>
  wpEditingWeights.value.reduce((s, w) => s + w.weight, 0)
)

const wpOpenWeightEditor = () => {
  const base = wpCustomWeights.value
  wpEditingWeights.value = warPeaceDetail.value.map(d => ({
    key: d.key,
    label: d.label,
    weight: base ? (base[d.key] ?? d.weight) : d.weight,
  }))
  wpWeightEditMode.value = true
}

const wpApplyWeights = () => {
  if (Math.abs(wpWeightSum.value - 100) > 0.01) return
  wpCustomWeights.value = Object.fromEntries(wpEditingWeights.value.map(w => [w.key, w.weight]))
  wpWeightEditMode.value = false
  const merged = warPeaceDetail.value.map(d => ({ ...d, weight: wpCustomWeights.value![d.key] ?? d.weight }))
  updateWarPeaceRadarChart(merged)
}

const wpResetWeights = () => {
  wpCustomWeights.value = null
  wpWeightEditMode.value = false
  updateWarPeaceRadarChart(warPeaceDetail.value)
}

// 鹰鸽颜色：<40 绿（鸽），40-70 橙（中），>=70 红（鹰）
const hawkColor = (score: number) => {
  if (score >= 70) return '#f56c6c'
  if (score >= 40) return '#e6a23c'
  return '#67c23a'
}

const fetchAndUpdateWarPeaceChart = async () => {
  try {
    const res = await getLatestWarPeaceScores()
    if (res) {
      warPeaceDetail.value = res.detail
      warPeaceIndex.value = res.composite_index
      warPeaceUpdatedAt.value = res.computed_at
      const merged = wpCustomWeights.value
        ? res.detail.map(d => ({ ...d, weight: wpCustomWeights.value![d.key] ?? d.weight }))
        : res.detail
      updateWarPeaceRadarChart(merged)
      return
    }
  } catch (e) {
    console.error('获取战争与和平指数失败:', e)
  }
  updateWarPeaceRadarChart([])
}

const fetchWarPeaceHistory = async () => {
  try {
    const history = await getWarPeaceHistory(120)
    warPeaceHistory.value = history.map(h => ({
      x: new Date(h.computed_at).toLocaleString('zh-CN', {
        timeZone: 'Asia/Shanghai',
        month: 'numeric', day: 'numeric',
        hour: 'numeric', minute: 'numeric',
        hour12: false
      }),
      y: h.composite_index
    }))
    renderWarPeaceLineChart()
  } catch (e) {
    console.error('获取战争与和平指数历史失败:', e)
  }
}

const renderWarPeaceLineChart = () => {
  const dom = document.getElementById('war-peace-line-chart')
  if (!dom) return
  if (!warPeaceLineChart) {
    warPeaceLineChart = echarts.init(dom, 'dark')
  }
  const xData = warPeaceHistory.value.map(h => h.x)
  const yData = warPeaceHistory.value.map(h => h.y)
  const lo = yData.length ? Math.min(...yData) : 0
  const hi = yData.length ? Math.max(...yData) : 10
  const pad = (hi - lo) * 0.25 || 1
  warPeaceLineChart.setOption({
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
      lineStyle: { color: '#f59e0b', width: 2 },
      areaStyle: {
        color: {
          type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [
            { offset: 0, color: 'rgba(245,158,11,0.3)' },
            { offset: 1, color: 'rgba(245,158,11,0.02)' }
          ]
        }
      },
    }],
  }, true)
}

const updateWarPeaceRadarChart = (detail: FactorDetail[]) => {
  if (!warPeaceRadarChart) return
  const indicator = detail.length
    ? detail.map(d => ({ name: `${d.label}(${d.weight}%)`, max: 100 }))
    : ['言辞强硬度','军事信号','经济施压','外交姿态','国内政治动机'].map(n => ({ name: n, max: 100 }))
  const values = detail.length ? detail.map(d => d.score) : [0, 0, 0, 0, 0]

  warPeaceRadarChart.setOption({
    backgroundColor: 'transparent',
    title: { text: '各维度得分', textStyle: { color: CHART_DARK.titleColor, fontSize: 24, fontWeight: 700 } }, /* 原 16 → 24 */
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
      axisName: { fontSize: 18, color: CHART_DARK.textColor }, /* 原 12 → 18 */
      splitLine: { lineStyle: { color: CHART_DARK.splitLineColor } },
      splitArea: { areaStyle: { color: ['rgba(30,45,69,0.3)', 'rgba(30,45,69,0.1)'] } },
      axisLine: { lineStyle: { color: CHART_DARK.axisLineColor } },
    },
    series: [{
      type: 'radar',
      data: [{
        value: values,
        name: '鹰派倾向',
        itemStyle: { color: '#f59e0b' },
        lineStyle: { color: '#f59e0b', width: 2 },
        areaStyle: { color: 'rgba(245,158,11,0.2)' },
        label: { show: true, formatter: (p: any) => p.value.toFixed(1), fontSize: 18, fontWeight: 700, color: '#fbbf24' }, /* 原 12 → 18 */
      }]
    }]
  })
}

// ── 图片滚动 ──────────────────────────────────────────────────
const images = ref<TrumpImage[]>([])
const scrollTrack = ref<HTMLElement | null>(null)
let scrollAnim: number | null = null
let scrollPos = 0

const fetchImages = async () => {
  try {
    const res = await request.get<{ total: number; images: TrumpImage[] }>('/images', { params: { limit: 40 } })
    images.value = res.images
    // 重置滚动
    scrollPos = 0
    if (scrollTrack.value) scrollTrack.value.style.transform = 'translateX(0)'
  } catch (e) {
    console.error('获取图片失败:', e)
  }
}

const startScroll = () => {
  if (scrollAnim) cancelAnimationFrame(scrollAnim)
  const step = () => {
    const track = scrollTrack.value
    if (!track) { scrollAnim = requestAnimationFrame(step); return }
    const totalWidth = track.scrollWidth / 2  // 复制了一份，所以除以2
    scrollPos += 0.5
    if (scrollPos >= totalWidth) scrollPos = 0
    track.style.transform = `translateX(-${scrollPos}px)`
    scrollAnim = requestAnimationFrame(step)
  }
  scrollAnim = requestAnimationFrame(step)
}

const stopScroll = () => {
  if (scrollAnim) { cancelAnimationFrame(scrollAnim); scrollAnim = null }
}

let intervals: ReturnType<typeof setInterval>[] = []

onMounted(async () => {
  await nextTick()

  const wpRadarDom = document.getElementById('war-peace-radar-chart') as HTMLElement
  if (wpRadarDom) {
    warPeaceRadarChart = echarts.init(wpRadarDom, 'dark')
  }
  fetchAndUpdateWarPeaceChart()
  fetchWarPeaceHistory()
  fetchImages()
  intervals.push(setInterval(fetchAndUpdateWarPeaceChart, 30000))
  intervals.push(setInterval(fetchWarPeaceHistory, 60000))
  intervals.push(setInterval(fetchImages, 300000))  // 5分钟刷新图片

  window.addEventListener('resize', onResize)

  // 等待图片加载后启动滚动
  setTimeout(() => {
    startScroll()
  }, 500)
})

onUnmounted(() => {
  intervals.forEach(clearInterval)
  stopScroll()
  window.removeEventListener('resize', onResize)
})
</script>

<template>
  <div class="dashboard">
    <!-- <div class="section-title">战争与和平指数</div> -->
    <el-card class="factor-card-wrap" style="margin-bottom:20px;">
      <el-row :gutter="16">

        <!-- 左：综合指数趋势 + 鹰鸽对比条 -->
        <el-col :span="10">
          <div class="composite-trend-header">
            <div class="composite-trend-title">
              鹰派倾向综合指数
              <span v-if="wpDisplayIndex !== null"
                class="composite-badge"
                :style="{ background: hawkColor(wpDisplayIndex) + '22', color: hawkColor(wpDisplayIndex), borderColor: hawkColor(wpDisplayIndex) + '55' }">
                {{ wpDisplayIndex.toFixed(1) }}
              </span>
              <span v-if="wpCustomWeights" class="custom-weight-tag">自定义权重</span>
            </div>
            <div class="composite-trend-desc">
              综合 5 个维度分析特朗普对外采取强硬手段的倾向（0–100）。
              <b style="color:#ef4444;">≥70</b> 极度鹰派，
              <b style="color:#e6a23c;">40–70</b> 中性偏强硬，
              <b style="color:#67c23a;">&lt;40</b> 鸽派倾向。
            </div>
          </div>
          <div id="war-peace-line-chart" style="width:100%; height:180px;"></div>
          <!-- 鹰鸽对比条 -->
          <div class="hawk-dove-bar-wrap">
            <span class="hawk-dove-label dove">🕊 鸽派</span>
            <div class="hawk-dove-track">
              <div class="hawk-dove-fill"
                :style="{
                  width: (wpDisplayIndex ?? 50) + '%',
                  background: `linear-gradient(90deg, #67c23a, ${hawkColor(wpDisplayIndex ?? 50)})`
                }">
              </div>
              <div class="hawk-dove-pointer"
                :style="{ left: (wpDisplayIndex ?? 50) + '%' }">
                <div class="hawk-dove-pointer-line"></div>
                <div class="hawk-dove-pointer-val" :style="{ color: hawkColor(wpDisplayIndex ?? 50) }">
                  {{ wpDisplayIndex !== null ? wpDisplayIndex.toFixed(1) : '--' }}
                </div>
              </div>
            </div>
            <span class="hawk-dove-label hawk">🦅 鹰派</span>
          </div>
          <div class="composite-trend-footer">
            更新于 {{ formatTime(warPeaceUpdatedAt) }}
          </div>
        </el-col>

        <!-- 中：雷达图 + 维度说明 -->
        <el-col :span="8">
          <div id="war-peace-radar-chart" style="width:100%; height:300px;"></div>
          <div class="factor-desc-list">
            <div v-for="item in warPeaceDetail" :key="item.key" class="factor-desc-item">
              <span class="factor-desc-dot" :style="{ background: hawkColor(item.score) }"></span>
              <span class="factor-desc-text">{{ WAR_PEACE_DESCRIPTIONS[item.key] || item.label }}</span>
            </div>
          </div>
        </el-col>

        <!-- 右：各维度得分 + 权重调整 -->
        <el-col :span="6" style="display:flex; flex-direction:column; justify-content:center;">
          <div v-if="warPeaceDetail.length" class="factor-inline-col">
            <div v-if="wpWeightEditMode" class="weight-editor">
              <div class="weight-editor-title">
                调整权重
                <span :class="['weight-sum-badge', Math.abs(wpWeightSum - 100) < 0.01 ? 'ok' : 'err']">
                  合计 {{ wpWeightSum }}%
                </span>
              </div>
              <div v-for="w in wpEditingWeights" :key="w.key" class="weight-row">
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
                <el-button size="small" type="primary" :disabled="Math.abs(wpWeightSum - 100) > 0.01" @click="wpApplyWeights">应用</el-button>
                <el-button size="small" @click="wpWeightEditMode = false">取消</el-button>
              </div>
            </div>

            <template v-else>
              <div class="factor-card-inline" v-for="item in warPeaceDetail" :key="item.key">
                <div class="factor-label-row">
                  <span class="factor-label">{{ item.label }}</span>
                  <span class="factor-weight">{{ wpCustomWeights ? wpCustomWeights[item.key] : item.weight }}%</span>
                </div>
                <div class="factor-score-inline" :style="{ color: hawkColor(item.score) }">{{ item.score.toFixed(1) }}</div>
                <el-progress :percentage="item.score" :color="hawkColor(item.score)" :show-text="false" style="margin:4px 0 0;" />
              </div>
              <div class="weight-btn-row">
                <el-button size="small" plain @click="wpOpenWeightEditor">调整权重</el-button>
                <el-button v-if="wpCustomWeights" size="small" plain @click="wpResetWeights">重置</el-button>
              </div>
            </template>
          </div>
        </el-col>

      </el-row>
    </el-card>

  <!-- 图片滚动展示 -->
  <el-card class="img-scroll-card" style="margin-top:16px;">
    <div class="img-scroll-header">
      <span class="img-scroll-title">📸 特朗普最新动态图片</span>
      <span class="img-scroll-source">来源：新浪图片</span>
    </div>
    <div
      class="img-scroll-viewport"
      @mouseenter="stopScroll"
      @mouseleave="startScroll"
    >
      <div ref="scrollTrack" class="img-scroll-track">
        <!-- 渲染两份实现无缝循环 -->
        <template v-for="pass in 2" :key="pass">
          <a
            v-for="(img, i) in images"
            :key="`${pass}-${i}`"
            :href="img.source_url"
            target="_blank"
            class="img-scroll-item"
          >
            <img
              :src="img.url"
              :alt="img.title"
              class="img-scroll-img"
              loading="lazy"
              @error="($event.target as HTMLImageElement).style.display='none'"
            />
            <div class="img-scroll-caption">{{ img.title || '特朗普' }}</div>
          </a>
        </template>
      </div>
    </div>
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

.factor-weight { font-size: 15px; color: var(--text-muted, #4a5a6e); } /* 原 10px → 15 */

.composite-trend-header { padding: 0 0 8px 0; }

.composite-trend-title {
  font-size: 21px; /* 原 14px → 21 (+50%) */
  font-weight: 700;
  color: var(--text-primary, #e2e8f0);
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.composite-badge {
  font-size: 27px; /* 原 18px → 27 (+50%) */
  font-weight: 800;
  padding: 1px 10px;
  border-radius: 6px;
  border: 1px solid;
  line-height: 1.4;
}

.composite-trend-desc {
  font-size: 17px; /* 原 11px → 17 (+50%) */
  color: var(--text-muted, #4a5a6e);
  line-height: 1.6;
}

.composite-trend-footer {
  font-size: 15px; /* 原 10px → 15 (+50%) */
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
  font-size: 17px; /* 原 11px → 17 (+50%) */
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
  font-size: 15px; /* 原 10px → 15 (+50%) */
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
  font-size: 18px; /* 原 12px → 18 (+50%) */
  font-weight: 700;
  color: var(--text-secondary, #7a90a8);
  margin-bottom: 10px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.weight-sum-badge {
  font-size: 17px; /* 原 11px → 17 (+50%) */
  font-weight: 600;
  padding: 1px 7px;
  border-radius: 4px;
}
.weight-sum-badge.ok { color: #67c23a; background: rgba(103,194,58,0.12); border: 1px solid rgba(103,194,58,0.3); }
.weight-sum-badge.err { color: #f56c6c; background: rgba(245,108,108,0.12); border: 1px solid rgba(245,108,108,0.3); }

.weight-row { display: flex; align-items: center; gap: 6px; margin-bottom: 7px; }

.weight-row-label {
  flex: 1;
  font-size: 17px; /* 原 11px → 17 (+50%) */
  color: var(--text-secondary, #7a90a8);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.weight-row-pct { font-size: 17px; /* 原 11px → 17 (+50%) */ color: var(--text-muted, #4a5a6e); }

.weight-editor-actions { display: flex; gap: 6px; margin-top: 10px; justify-content: flex-end; }

.weight-btn-row { display: flex; gap: 6px; margin-top: 6px; justify-content: flex-end; }

.factor-card-wrap :deep(.el-card__body) { padding: 16px; }

.hawk-dove-bar-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 10px 0 6px;
}

.hawk-dove-label { font-size: 17px; /* 原 11px → 17 (+50%) */ white-space: nowrap; flex-shrink: 0; }
.hawk-dove-label.dove { color: #67c23a; }
.hawk-dove-label.hawk { color: #f56c6c; }

.hawk-dove-track {
  flex: 1;
  height: 8px;
  background: #1e2d45;
  border-radius: 4px;
  position: relative;
  overflow: visible;
}

.hawk-dove-fill {
  height: 100%;
  border-radius: 4px;
  transition: width 0.6s ease;
}

.hawk-dove-pointer {
  position: absolute;
  top: 50%;
  transform: translate(-50%, -50%);
  display: flex;
  flex-direction: column;
  align-items: center;
  transition: left 0.6s ease;
}

.hawk-dove-pointer-line {
  width: 2px;
  height: 14px;
  background: #e2e8f0;
  border-radius: 1px;
}

.hawk-dove-pointer-val {
  font-size: 15px; /* 原 10px → 15 (+50%) */
  font-weight: 700;
  margin-top: 2px;
  white-space: nowrap;
}

/* 图片滚动样式 */
.img-scroll-card :deep(.el-card__body) { padding: 12px; }

.img-scroll-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.img-scroll-title {
  font-size: 20px; /* 原 13px → 20 (+50%) */
  font-weight: 700;
  color: var(--text-primary, #e2e8f0);
}

.img-scroll-source {
  font-size: 15px; /* 原 10px → 15 (+50%) */
  color: var(--text-muted, #4a5a6e);
}

.img-scroll-viewport {
  width: 100%;
  overflow: hidden;
  position: relative;
  height: 140px;
  background: var(--bg-card, #111827);
  border-radius: 6px;
  border: 1px solid var(--border, #1e2d45);
}

.img-scroll-track {
  display: flex;
  gap: 10px;
  position: absolute;
  left: 0;
  top: 0;
  height: 100%;
  align-items: center;
  padding: 0 10px;
  will-change: transform;
}

.img-scroll-item {
  flex-shrink: 0;
  width: 180px;
  height: 120px;
  position: relative;
  border-radius: 6px;
  overflow: hidden;
  border: 1px solid var(--border, #1e2d45);
  transition: transform 0.2s ease, box-shadow 0.2s ease;
  text-decoration: none;
}

.img-scroll-item:hover {
  transform: scale(1.05);
  box-shadow: 0 4px 12px rgba(0,0,0,0.4);
  border-color: #4a9eff;
}

.img-scroll-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.img-scroll-caption {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  background: linear-gradient(to top, rgba(0,0,0,0.8), transparent);
  color: #fff;
  font-size: 17px; /* 原 11px → 17 (+50%) */
  padding: 16px 8px 6px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  pointer-events: none;
}

</style>
