<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import * as echarts from 'echarts'
import dayjs from 'dayjs'
import request from '../utils/request'

interface RegressionPoint {
  date: string
  x: number
  y: number
}

interface IndicatorResult {
  label: string
  a: number
  b: number
  r2: number
  corr: number
  n: number
  x_min: number
  x_max: number
  y_at_xmin: number
  y_at_xmax: number
  points: RegressionPoint[]
}

interface YOption {
  key: string
  label: string
}

interface RegressionData {
  since: string
  days: number
  y_type: string
  y_label: string
  y_options: YOption[]
  indicators: Record<string, IndicatorResult>
}

const loading = ref(false)
const data = ref<RegressionData | null>(null)
const selectedKey = ref('')
const selectedY = ref('hawkish_mean')
const lagFilter = ref('all')
const analysisMode = ref('original') // original | swap | hawkish_lag1
let timeChart: echarts.ECharts | null = null

const indicatorList = computed(() => {
  if (!data.value) return []
  return Object.entries(data.value.indicators).map(([key, v]) => ({
    key,
    label: v.label,
    corr: v.corr,
    r2: v.r2,
    n: v.n,
  }))
})

const selected = computed(() =>
  selectedKey.value && data.value ? data.value.indicators[selectedKey.value] : null
)

const corrColor = (corr: number) => {
  const abs = Math.abs(corr)
  if (abs >= 0.7) return corr > 0 ? '#f56c6c' : '#67c23a'
  if (abs >= 0.4) return corr > 0 ? '#e6a23c' : '#4a9eff'
  return '#7a90a8'
}

const corrLabel = (corr: number) => {
  const abs = Math.abs(corr)
  const dir = corr > 0 ? '正' : '负'
  if (abs >= 0.7) return `强${dir}相关`
  if (abs >= 0.4) return `中${dir}相关`
  if (abs >= 0.2) return `弱${dir}相关`
  return '无显著相关'
}

const fetchData = async () => {
  loading.value = true
  try {
    data.value = await request.get<RegressionData>('/analysis/regression', {
      params: {
        y_type: selectedY.value,
        lag_filter: lagFilter.value,
        analysis_mode: analysisMode.value
      }
    })
    if (data.value.y_type) {
      selectedY.value = data.value.y_type
    }
    const keys = Object.keys(data.value.indicators)
    if (keys.length) {
      selectedKey.value = keys[0] as string
      await renderChart()
    }
  } catch (e) {
    console.error('获取回归数据失败:', e)
  } finally {
    loading.value = false
  }
}

const changeY = async () => {
  await fetchData()
}

const changeLagFilter = async () => {
  await fetchData()
}

const changeAnalysisMode = async () => {
  // 切换模式时重置selectedY默认值
  if (analysisMode.value === 'original') {
    selectedY.value = 'hawkish_mean'
  } else {
    // swap/hawkish_lag1模式，默认选中第一个市场指标
    selectedY.value = '标普500'
  }
  await fetchData()
}

const renderChart = async () => {
  const ind = selected.value
  if (!ind) return

  // 只渲染时间趋势图
  await renderTimeChart()
}

const renderTimeChart = async () => {
  const ind = selected.value
  if (!ind) return

  await new Promise(r => setTimeout(r, 50))
  const dom = document.getElementById('time-trend-chart')
  if (!dom) return

  if (!timeChart) timeChart = echarts.init(dom, 'dark')

  // 整理已有数据 - 保存完整日期和实际值
  const pointMap: Record<string, {x: number; y: number; fullDate: string}> = {}
  ind.points.forEach(p => {
    pointMap[p.date] = {x: p.x, y: p.y, fullDate: p.date}
  })

  // 生成从2026-02-28到今天的完整日期序列
  const startDateStr = '2026-02-28'
  const endDate = dayjs().startOf('day')
  const startDate = dayjs(startDateStr).startOf('day')
  const daysDiff = endDate.diff(startDate, 'day')

  const fullDates: string[] = []
  const fullDatesFull: string[] = []
  const fullX: (number | null)[] = []
  const fullY: (number | null)[] = []

  for (let i = 0; i <= daysDiff; i++) {
    const currentDate = dayjs(startDateStr).add(i, 'day')
    const dateKey = currentDate.format('YYYY-MM-DD')
    fullDates.push(dateKey.slice(5)) // 只显示 MM-DD
    fullDatesFull.push(dateKey)
    if (pointMap[dateKey]) {
      fullX.push(pointMap[dateKey].x)
      fullY.push(pointMap[dateKey].y)
    } else {
      fullX.push(null)
      fullY.push(null)
    }
  }

  // 对X和Y数据都做归一化到 0-100 方便同图展示（跳过null）
  const validX = fullX.filter(v => v != null) as number[]
  const validY = fullY.filter(v => v != null) as number[]
  const xMin = Math.min(...validX)
  const xMax = Math.max(...validX)
  const xNorm = fullX.map(v => v == null ? null : (v - xMin) / (xMax - xMin) * 100)

  const yMin = Math.min(...validY)
  const yMax = Math.max(...validY)
  const yNorm = fullY.map(v => v == null ? null : (v - yMin) / (yMax - yMin) * 100)

  // 根据分析模式确定图例名称
  const xName = ind.label
  const yName = data.value?.y_label || 'Y'

  const option = {
    backgroundColor: 'transparent',
    title: {
      text: '时间趋势对比 (归一化到0-100)',
      left: 'center',
      textStyle: { color: '#7a90a8', fontSize: 21 },
    },
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#1a2235',
      borderColor: '#2d3f55',
      textStyle: { color: '#e2e8f0', fontSize: 18 },
      formatter: (params: any) => {
        if (!params || params.length === 0) return ''
        const idx = params[0].dataIndex
        const fullDate = fullDatesFull[idx]
        const actualX = fullX[idx]
        const actualY = fullY[idx]
        
        let result = `<div style="font-weight: bold; margin-bottom: 8px;">日期: ${fullDate}</div>`
        
        params.forEach((param: any) => {
          const color = param.color
          const name = param.seriesName
          const normValue = param.value != null ? param.value.toFixed(2) : '-'
          
          if (name === xName) {
            const actualVal = actualX != null ? actualX.toFixed(4) : '-'
            result += `<div style="margin-bottom: 4px;">
              <span style="display:inline-block;margin-right:4px;border-radius:10px;width:10px;height:10px;background-color:${color};"></span>
              ${name}: ${normValue} (归一化) / ${actualVal} (实际)
            </div>`
          } else if (name === yName) {
            const actualVal = actualY != null ? actualY.toFixed(4) : '-'
            result += `<div style="margin-bottom: 4px;">
              <span style="display:inline-block;margin-right:4px;border-radius:10px;width:10px;height:10px;background-color:${color};"></span>
              ${name}: ${normValue} (归一化) / ${actualVal} (实际)
            </div>`
          }
        })
        
        return result
      }
    },
    legend: {
      data: [xName, yName],
      top: 30,
      textStyle: { color: '#e2e8f0' },
    },
    grid: { left: 50, right: 20, top: 60, bottom: 80 },
    xAxis: {
      type: 'category',
      data: fullDates,
      axisLabel: { color: '#7a90a8', fontSize: 13, rotate: 45 },
      axisLine: { lineStyle: { color: '#2d3f55' } },
    },
    yAxis: {
      type: 'value',
      min: 0,
      max: 100,
      name: '标准化数值 (0-100)',
      nameLocation: 'middle',
      nameGap: 30,
      nameTextStyle: { color: '#7a90a8', fontSize: 18 },
      axisLabel: { color: '#7a90a8', fontSize: 17 },
      splitLine: { lineStyle: { color: '#1e2d45', type: 'dashed' } },
      axisLine: { lineStyle: { color: '#2d3f55' } },
    },
    series: [
      {
        name: xName,
        type: 'line',
        data: xNorm,
        connectNulls: true,
        lineStyle: { width: 2, color: '#3b82f6' },
        symbol: 'circle',
        symbolSize: 6,
        itemStyle: { color: '#3b82f6' },
      },
      {
        name: yName,
        type: 'line',
        data: yNorm,
        connectNulls: true,
        lineStyle: { width: 2, color: '#ef4444' },
        symbol: 'circle',
        symbolSize: 6,
        itemStyle: { color: '#ef4444' },
      },
    ],
  }

  timeChart.setOption(option, true)
}

const selectIndicator = async (key: string) => {
  selectedKey.value = key
  await renderChart()
}

// 指标提示信息：含义与政策影响分析
const indicatorHints: Record<string, { meaning: string; impact: string }> = {
  '地缘风险溢价': {
    meaning: '布伦特原油与WTI原油的价差，反映霍尔木兹海峡地缘风险溢价',
    impact: '价差扩大→地缘紧张升高→特朗普更可能对伊朗采取强硬态度以维持石油航道安全'
  },
  '地缘溢价': {
    meaning: '布伦特原油与WTI原油的价差，反映霍尔木兹海峡地缘风险溢价',
    impact: '价差扩大→地缘紧张升高→特朗普更可能对伊朗采取强硬态度以维持石油航道安全'
  },
  '布伦特原油': {
    meaning: '布伦特原油现货/期货价格，反映全球石油供需与地缘风险',
    impact: '油价升高→刺激通胀、影响国内经济→特朗普可能倾向对伊朗出手压低油价巩固选情'
  },
  'WTI原油': {
    meaning: '西德克萨斯中质原油价格，反映美国本土油价水平',
    impact: 'WTI油价升高→美国消费者汽油负担加重→特朗普面临政治压力可能采取强硬行动'
  },
  '黄金价格': {
    meaning: '黄金期货价格，反映全球避险情绪与通胀预期',
    impact: '金价上涨→市场避险情绪升温→地缘不确定性升高→鹰派政策概率增加'
  },
  'VIX指数': {
    meaning: '标普500波动率指数，反映市场恐慌程度',
    impact: 'VIX升高→市场恐慌→风险升级→特朗普可能通过对外强硬转移国内注意力'
  },
  '标普500': {
    meaning: '标普500指数，反映美国股市整体表现',
    impact: '股市下跌→选民财富缩水→支持率承压→特朗普更可能对外秀强硬提振支持率'
  },
  '纳斯达克': {
    meaning: '纳斯达克综合指数，反映科技股表现',
    impact: '纳指下跌→ tech板块承压→资本市场不满→特朗普可能通过对外强硬转移视线'
  },
  '道琼斯': {
    meaning: '道琼斯工业平均指数，反映传统工业板块表现',
    impact: '道指下跌→经济信心下滑→政治压力上升→更倾向采取鹰派政策提振国内情绪'
  },
  '美国10年期国债': {
    meaning: '美国10年期国债收益率，反映市场利率与通胀预期',
    impact: '收益率走高→通胀压力大→美联储被迫加息→经济承压→特朗普可能对外转移矛盾'
  },
  '10年期国债': {
    meaning: '美国10年期国债收益率，反映市场利率与通胀预期',
    impact: '收益率走高→通胀压力大→美联储被迫加息→经济承压→特朗普可能对外转移矛盾'
  },
  '美国2年期国债': {
    meaning: '美国2年期国债收益率，反映短期利率预期',
    impact: '收益率走高→紧缩预期强→经济前景偏空→更可能通过对外强硬分散国内压力'
  },
  '2年期国债': {
    meaning: '美国2年期国债收益率，反映短期利率预期',
    impact: '收益率走高→紧缩预期强→经济前景偏空→更可能通过对外强硬分散国内压力'
  },
  '特朗普支持率': {
    meaning: '全国民意调查中特朗普的平均支持率',
    impact: '支持率偏低→选情吃紧→特朗普更需要通过鹰派外交政策巩固基本盘'
  },
  '支持率': {
    meaning: '全国民意调查中特朗普的平均支持率',
    impact: '支持率偏低→选情吃紧→特朗普更需要通过鹰派外交政策巩固基本盘'
  },
  '失业率': {
    meaning: '美国月度失业率，反映劳动市场状况',
    impact: '失业率上升→经济不景气→国内不满增加→特朗普倾向对外强硬转移焦点'
  },
  'CPI同比': {
    meaning: '美国消费者物价指数同比涨幅，反映通货膨胀水平',
    impact: 'CPI高企→通胀严重→民生痛苦指数上升→特朗普可能对伊朗出手试图压低油价'
  },
  'Polymarket弹劾概率': {
    meaning: 'Polymarket预测市场上特朗普被弹劾的概率定价',
    impact: '弹劾概率升高→国内政治危机→特朗普更可能通过对外强硬制造团结气氛'
  },
  '弹劾概率': {
    meaning: 'Polymarket预测市场上特朗普被弹劾的概率定价',
    impact: '弹劾概率升高→国内政治危机→特朗普更可能通过对外强硬制造团结气氛'
  },
  '非农就业': {
    meaning: '月度非农就业新增人数，反映就业市场韧性',
    impact: '非农强劲→劳动力市场火热→特朗普团队底气更足→更有底气采取冒险鹰派政策'
  },
  '黄金收益率': {
    meaning: '黄金价格日对数收益率，反映避险情绪变化',
    impact: '收益率大增→避险情绪爆发→地缘危机预期→鹰派言论概率上升'
  },
  '标普500收益率': {
    meaning: '标普500日对数收益率，反映股市单日涨跌幅',
    impact: '收益率大跌→市场恐慌→政治压力上升→更可能发表鹰派言论转移注意力'
  },
  '布伦特收益率': {
    meaning: '布伦特原油日对数收益率，反映油价单日涨跌幅',
    impact: '油价大涨→通胀压力升级→特朗普更可能对伊朗采取行动打开供应缺口'
  },
  'WTI收益率': {
    meaning: 'WTI原油日对数收益率，反映油价单日涨跌幅',
    impact: '油价大涨→国内通胀压力→特朗普倾向采取强硬政策打压油价'
  },
  'hawkish_avg_hawkish': {
    meaning: '特朗普言论政策评分均值',
    impact: '政策评分越高→特朗普对伊朗态度越强硬→预期影响市场风险偏好'
  },
  'hawkish_max_hawkish': {
    meaning: '特朗普言论政策评分最大值',
    impact: '单日最高政策评分越高→特朗普当日最强硬表态→对市场的冲击可能更大'
  },
  'hawkish_ratio_hawkish': {
    meaning: '当日鹰派帖子占比',
    impact: '鹰派帖子比例越高→当日整体言论偏强硬越高→一致性鹰派信号影响市场预期'
  },
  'post_count_hawkish': {
    meaning: '当日发帖数量',
    impact: '发帖数量增加→话题关注度提升→可能预示重大政策动作即将来临'
  },
  'hawkish_word_avg_hawkish': {
    meaning: '当日鹰派词汇平均计数',
    impact: '鹰派词汇使用越多→言论强硬程度越高→对市场风险情绪影响越大'
  },
  'hawkish_avg_hawkish_lag1': {
    meaning: '特朗普言论政策评分均值(滞后1天)',
    impact: '昨日政策评分→分析对今日市场的影响，检验鹰派言论是否领先市场变化'
  },
  'hawkish_max_hawkish_lag1': {
    meaning: '特朗普言论政策评分最大值(滞后1天)',
    impact: '昨日最高政策评分→分析对今日市场的滞后影响'
  },
  'hawkish_ratio_hawkish_lag1': {
    meaning: '当日鹰派帖子占比(滞后1天)',
    impact: '昨日鹰派帖子比例→分析对今日市场的滞后影响'
  },
  'post_count_hawkish_lag1': {
    meaning: '当日发帖数量(滞后1天)',
    impact: '昨日发帖数量→分析活跃度对今日市场的前瞻性'
  },
  'hawkish_word_avg_hawkish_lag1': {
    meaning: '当日鹰派词汇平均计数(滞后1天)',
    impact: '昨日鹰派词汇使用→分析言论强度对今日市场的影响'
  },
}

// 获取当前选中指标的提示
const currentHint = computed(() => {
  if (!selected.value) return null
  // 原始指标名（去掉滞后后缀）
  const baseKey = selectedKey.value.replace(/_lag\d+$/, '')
  const hint = indicatorHints[baseKey] || indicatorHints[selected.value.label]
  return hint
})

onMounted(fetchData)
</script>

<template>
  <div class="regression-page" v-loading="loading">
    <el-card v-if="data">
      <!-- 标题 -->
      <div class="page-header">
        <div class="page-title">指标–言论相关性分析</div>
        <div class="page-desc">
          <template v-if="analysisMode === 'original'">
            基于 {{ data.since }} 以来 {{ data.days }} 个交易日数据，分析关键市场指标（X）与
            Truth Social 涉伊朗/石油言论政策评分（Y）的线性回归关系。研究市场状况如何影响特朗普言论倾向。
          </template>
          <template v-else-if="analysisMode === 'swap'">
            基于 {{ data.since }} 以来 {{ data.days }} 个交易日数据，分析政策评分（X）与
            关键市场指标（Y）的线性回归关系。研究当日特朗普鹰派言论对当日市场的影响。
          </template>
          <template v-else-if="analysisMode === 'hawkish_lag1'">
            基于 {{ data.since }} 以来 {{ data.days }} 个交易日数据，分析滞后1天政策评分（X）与
            关键市场指标（Y）的线性回归关系。研究昨日特朗普鹰派言论对今日市场的影响。
          </template>
          点击指标查看指标含义与政策影响分析。
        </div>

        <div class="filter-row">
          <!-- 分析模式 -->
          <div class="mode-selector">
            <span class="mode-label">分析模式：</span>
            <el-radio-group v-model="analysisMode" @change="changeAnalysisMode" size="small">
              <el-radio-button label="original">市场→政策</el-radio-button>
              <el-radio-button label="swap">政策→市场</el-radio-button>
              <el-radio-button label="hawkish_lag1">政策→滞后1天市场</el-radio-button>
            </el-radio-group>
          </div>

          <!-- 滞后筛选 (仅在original模式显示) -->
          <div class="lag-selector" v-if="analysisMode === 'original'">
            <span class="lag-label">滞后筛选：</span>
            <el-radio-group v-model="lagFilter" @change="changeLagFilter" size="small">
              <el-radio-button label="all">全部</el-radio-button>
              <el-radio-button label="none">无滞后</el-radio-button>
              <el-radio-button label="lag1">滞后1天</el-radio-button>
              <el-radio-button label="lag3">滞后3天</el-radio-button>
              <!-- <el-radio-button label="lag7">滞后7天</el-radio-button> -->
            </el-radio-group>
          </div>

          <!-- Y 变量选择 -->
          <div class="y-selector">
            <span class="y-label">因变量 Y：</span>
            <el-radio-group v-model="selectedY" @change="changeY" size="small">
              <el-radio-button v-for="opt in data.y_options" :key="opt.key" :label="opt.key">
                {{ opt.label }}
              </el-radio-button>
            </el-radio-group>
          </div>

        </div>
      </div>

      <el-row :gutter="16" style="margin-top:16px;">
        <!-- 左：指标排行 -->
        <el-col :span="8">
          <div class="rank-title">相关性排行（按 |r| 降序）</div>
          <div class="rank-list">
            <div
              v-for="item in indicatorList"
              :key="item.key"
              :class="['rank-item', selectedKey === item.key ? 'active' : '']"
              @click="selectIndicator(item.key)"
            >
              <div class="rank-item-top">
                <span class="rank-label">{{ item.label }}</span>
                <span class="rank-corr" :style="{ color: corrColor(item.corr) }">
                  r = {{ item.corr > 0 ? '+' : '' }}{{ item.corr.toFixed(3) }}
                </span>
              </div>
              <div class="rank-item-bottom">
                <span class="rank-tag" :style="{ color: corrColor(item.corr), borderColor: corrColor(item.corr) + '55', background: corrColor(item.corr) + '15' }">
                  {{ corrLabel(item.corr) }}
                </span>
                <span class="rank-r2">R² = {{ item.r2.toFixed(3) }}</span>
                <span class="rank-n">n={{ item.n }}</span>
              </div>
              <!-- 相关性条 -->
              <div class="corr-bar-wrap">
                <div class="corr-bar-center"></div>
                <div
                  class="corr-bar-fill"
                  :style="{
                    width: Math.abs(item.corr) * 50 + '%',
                    left: item.corr >= 0 ? '50%' : (50 - Math.abs(item.corr) * 50) + '%',
                    background: corrColor(item.corr),
                  }"
                ></div>
              </div>
            </div>
          </div>
        </el-col>

        <!-- 右：散点图 + 回归线 + 统计摘要 -->
        <el-col :span="16">
          <template v-if="selected">
            <!-- 指标提示信息 -->
            <div v-if="currentHint" class="hint-card">
              <div class="hint-title">
                <span class="hint-icon">ℹ️</span>
                <span class="hint-title-text">{{ selected.label }} - 指标说明</span>
              </div>
              <div class="hint-row">
                <span class="hint-label">指标含义：</span>
                <span class="hint-text">{{ currentHint.meaning }}</span>
              </div>
              <div class="hint-row">
                <span class="hint-label">政策影响：</span>
                <span class="hint-text">{{ currentHint.impact }}</span>
              </div>
            </div>

            <!-- 统计摘要 -->
            <div class="stat-row">
              <div class="stat-card">
                <div class="stat-val" :style="{ color: corrColor(selected.corr) }">
                  {{ selected.corr > 0 ? '+' : '' }}{{ selected.corr.toFixed(3) }}
                </div>
                <div class="stat-label">相关系数 r</div>
              </div>
              <div class="stat-card">
                <div class="stat-val" :style="{ color: selected.r2 >= 0.5 ? '#f59e0b' : '#7a90a8' }">
                  {{ selected.r2.toFixed(3) }}
                </div>
                <div class="stat-label">决定系数 R²</div>
              </div>
              <div class="stat-card">
                <div class="stat-val" style="color:#e2e8f0;">
                  {{ selected.a > 0 ? '+' : '' }}{{ selected.a.toFixed(4) }}
                </div>
                <div class="stat-label">斜率 a</div>
              </div>
              <div class="stat-card">
                <div class="stat-val" style="color:#e2e8f0;">{{ selected.b.toFixed(2) }}</div>
                <div class="stat-label">截距 b</div>
              </div>
              <div class="stat-card">
                <div class="stat-val" style="color:#e2e8f0;">{{ selected.n }}</div>
                <div class="stat-label">样本量</div>
              </div>
            </div>

            <!-- 回归方程 -->
            <div class="equation-bar">
              <span class="equation-label">回归方程：</span>
              <span class="equation-text">
                <template v-if="analysisMode === 'original'">
                  政策评分 = {{ selected.a > 0 ? '+' : '' }}{{ selected.a.toFixed(4) }} × {{ selected.label }}
                  {{ selected.b >= 0 ? '+' : '' }}{{ selected.b.toFixed(2) }}
                </template>
                <template v-else>
                  {{ data?.y_label }} = {{ selected.a > 0 ? '+' : '' }}{{ selected.a.toFixed(4) }} × {{ selected.label }}
                  {{ selected.b >= 0 ? '+' : '' }}{{ selected.b.toFixed(2) }}
                </template>
              </span>
              <span class="equation-interp" :style="{ color: corrColor(selected.corr) }">
                {{ corrLabel(selected.corr) }}
              </span>
            </div>

            <!-- 时间趋势图 -->
            <div id="time-trend-chart" style="width:100%; height:500px; margin-top: 12px;"></div>

          </template>
        </el-col>
      </el-row>
    </el-card>

    <el-empty v-else-if="!loading" description="暂无回归数据" />
  </div>
</template>

<style scoped>
.regression-page { padding: 4px 0; }

.page-header { margin-bottom: 4px; }
.page-title {
  font-size: 20px; /* 原 16px 加大 50% */
  font-weight: 700;
  color: var(--text-primary, #e2e8f0);
  margin-bottom: 6px;
}
.page-desc {
  font-size: 18px; /* 原 12px 加大 50% */
  color: var(--text-muted, #4a5a6e);
  line-height: 1.6;
}

.rank-title {
  font-size: 18px; /* 原 12px 加大 50% */
  font-weight: 600;
  color: var(--text-secondary, #7a90a8);
  margin-bottom: 8px;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--border, #1e2d45);
}

.rank-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 480px;
  overflow-y: auto;
}

.rank-item {
  padding: 8px 10px;
  border-radius: 6px;
  background: var(--bg-card, #111827);
  border: 1px solid var(--border, #1e2d45);
  cursor: pointer;
  transition: border-color 0.2s, background 0.2s;
}
.rank-item:hover { border-color: #2d3f55; background: #131f30; }
.rank-item.active { border-color: rgba(145, 159, 12, 0.272); background: rgba(232, 155, 23, 0.135); }

.rank-item-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}
.rank-label { font-size: 20px; /* 原 13px 加大 50% */ font-weight: 600; color: var(--text-primary, #e2e8f0); }
.rank-corr { font-size: 20px; /* 原 13px 加大 50% */ font-weight: 700; font-family: monospace; }

.rank-item-bottom {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}
.rank-tag {
  font-size: 15px; /* 原 10px 加大 50% */
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 3px;
  border: 1px solid;
}
.rank-r2 { font-size: 17px; /* 原 11px 加大 50% */ color: var(--text-muted, #4a5a6e); }
.rank-n  { font-size: 17px; /* 原 11px 加大 50% */ color: var(--text-muted, #4a5a6e); margin-left: auto; }

.corr-bar-wrap {
  position: relative;
  height: 4px;
  background: var(--border, #1e2d45);
  border-radius: 2px;
  overflow: hidden;
}
.corr-bar-center {
  position: absolute;
  left: 50%;
  top: 0;
  width: 1px;
  height: 100%;
  background: #2d3f55;
}
.corr-bar-fill {
  position: absolute;
  top: 0;
  height: 100%;
  border-radius: 2px;
  transition: width 0.4s ease;
}

.stat-row {
  display: flex;
  gap: 8px;
  margin-bottom: 10px;
}
.stat-card {
  flex: 1;
  text-align: center;
  padding: 8px 4px;
  background: var(--bg-card, #111827);
  border: 1px solid var(--border, #1e2d45);
  border-radius: 6px;
}
.stat-val { font-size: 27px; /* 原 18px 加大 50% */ font-weight: 800; line-height: 1.2; font-family: monospace; }
.stat-label { font-size: 15px; /* 原 10px 加大 50% */ color: var(--text-muted, #4a5a6e); margin-top: 2px; }

.equation-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: var(--bg-card, #111827);
  border: 1px solid var(--border, #1e2d45);
  border-radius: 6px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}
.equation-label { font-size: 17px; /* 原 11px 加大 50% */ color: var(--text-muted, #4a5a6e); flex-shrink: 0; }
.equation-text { font-size: 20px; /* 原 13px 加大 50% */ font-weight: 600; color: #e2e8f0; font-family: monospace; flex: 1; }
.equation-interp { font-size: 17px; /* 原 11px 加大 50% */ font-weight: 600; flex-shrink: 0; }

.filter-row {
  display: flex;
  gap: 20px;
  align-items: center;
  flex-wrap: wrap;
  margin-top: 8px;
}
.y-selector {
  display: flex;
  align-items: center;
  gap: 10px;
}
.y-label {
  font-size: 18px; /* 原 12px 加大 50% */
  color: var(--text-secondary, #7a90a8);
  font-weight: 600;
}
.lag-selector {
  display: flex;
  align-items: center;
  gap: 10px;
}
.lag-label {
  font-size: 18px; /* 原 12px 加大 50% */
  color: var(--text-secondary, #7a90a8);
  font-weight: 600;
}

.mode-selector {
  display: flex;
  align-items: center;
  gap: 10px;
}

.mode-label {
  font-size: 18px;
  color: var(--text-secondary, #7a90a8);
  font-weight: 600;
}

.hint-card {
  padding: 12px 16px;
  margin-bottom: 10px;
  background: var(--bg-card, #111827);
  border: 1px solid var(--border, #1e2d45);
  border-radius: 6px;
}

.hint-title {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
}

.hint-icon {
  font-size: 18px;
}

.hint-title-text {
  font-size: 18px;
  font-weight: 700;
  color: #60a5fa;
}

.hint-row {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  margin-top: 6px;
  flex-wrap: wrap;
}

.hint-label {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-secondary, #7a90a8);
  flex-shrink: 0;
  min-width: 80px;
}

.hint-text {
  font-size: 16px;
  color: #4a5a6e;
  flex: 1;
  line-height: 1.5;
}
</style>
