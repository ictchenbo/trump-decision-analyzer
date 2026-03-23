<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { ElTable, ElTableColumn, ElTag, ElButton, ElCard, ElPagination, ElSelect, ElOption, ElDatePicker, ElInput, ElMessage } from 'element-plus'
import { getTrumpStatements, deleteTrumpStatement, getHawkishDaily } from '../api/trump_statements'
import type { TrumpStatement, HawkishDailyData } from '../models/trump_statement'
import dayjs from 'dayjs'
import * as echarts from 'echarts'

const statementList = ref<TrumpStatement[]>([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(20)
const loading = ref(false)
let hawkishChart: echarts.ECharts | null = null

// 查询参数
const searchParams = ref({
  source: '',
  start_time: undefined as Date | undefined,
  end_time: undefined as Date | undefined,
  keyword: ''
})

const fetchStatements = async () => {
  loading.value = true
  try {
    const data = await getTrumpStatements(
      searchParams.value.source || undefined,
      searchParams.value.start_time,
      searchParams.value.end_time,
      pageSize.value,
      (currentPage.value - 1) * pageSize.value,
      searchParams.value.keyword || undefined
    )
    statementList.value = data.statements
    total.value = data.total
    // updateChart()
  } catch (error) {
    console.error('获取特朗普言行数据失败:', error)
    // 备用模拟数据
    statementList.value = generateMockData()
    total.value = statementList.value.length
    // updateChart()
  } finally {
    loading.value = false
  }
}

const handleSearch = () => {
  currentPage.value = 1
  fetchStatements()
}

const handleDelete = async (id: string) => {
  try {
    await deleteTrumpStatement(id)
    ElMessage.success('删除成功')
    fetchStatements()
    fetchChartData() // 删除后刷新图表数据
  } catch (error) {
    ElMessage.error('删除失败')
  }
}

const handlePageChange = (page: number) => {
  currentPage.value = page
  fetchStatements()
}

const handleSizeChange = (size: number) => {
  pageSize.value = size
  currentPage.value = 1
  fetchStatements()
}

// 生成模拟数据
const generateMockData = (): TrumpStatement[] => {
  const templates = [
    "我们将让美国再次强大！",
    "我们在阿富汗的撤退是彻底的灾难！",
    "油价太高了，我们需要能源独立！",
    "选举被操纵了，这是一场骗局！",
    "我刚刚在集会上发表了演讲，现场太棒了！",
    "美联储应该大幅降息！",
    "我们的边境是安全的，再也不会有非法移民！",
    "中国对我们的贸易不公平，必须改变！"
  ]
  const sources = ["Truth Social", "福克斯新闻", "路透社", "BBC", "美联社", "华盛顿邮报"]
  const sentimentOptions = ['positive', 'negative', 'neutral']
  
  return Array.from({ length: 25 }, (_, i) => ({
    _id: `stmt_${i}`,
    content: templates[Math.floor(Math.random() * templates.length)] as string,
    source: sources[Math.floor(Math.random() * sources.length)] as string,
    post_time: dayjs().subtract(Math.random() * 48, 'hour').toISOString(),
    url: `https://example.com/news/${Math.floor(Math.random() * 1000000)}`,
    likes: Math.floor(Math.random() * 1000000),
    shares: Math.floor(Math.random() * 500000),
    sentiment: sentimentOptions[Math.floor(Math.random() * sentimentOptions.length)] as any,
    sentiment_score: (Math.random() * 2 - 1).toFixed(2) as any,
    hawkish_score: Math.floor(Math.random() * 100)
  }))
}

const hawkishColor = (score: number) => {
  if (score >= 70) return '#f56c6c'
  if (score >= 40) return '#e6a23c'
  return '#67c23a'
}

const hawkishLabel = (score: number) => {
  if (score >= 70) return '鹰派'
  if (score >= 40) return '中性'
  return '鸽派'
}

const getSentimentColor = (sentiment?: string) => {
  switch (sentiment) {
    case 'positive': return 'success'
    case 'negative': return 'danger'
    default: return 'info'
  }
}

const getSentimentLabel = (sentiment?: string) => {
  switch (sentiment) {
    case 'positive': return '正面'
    case 'negative': return '负面'
    default: return '中性'
  }
}

const getSentimentDesc = (score?: number) => {
  if (score === undefined || score === null) return ''
  const s = Number(score)
  if (s >= 0.6)  return '强烈正面'
  if (s >= 0.2)  return '偏正面'
  if (s > -0.2)  return '中性'
  if (s > -0.6)  return '偏负面'
  return '强烈负面'
}

const isUrlOnly = (content: string) => {
  if (!content) return false
  const trimmed = content.trim()
  return /^https?:\/\/\S+$/.test(trimmed)
}

const formatTime = (time: string) => {
  if (!time) return '--'
  const d = dayjs(time)
  return d.isValid() ? new Date(d.valueOf()).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false }) : '--'
}

// 获取图表数据：从后端新接口获取聚合好的每日平均鹰派评分
const fetchChartData = async () => {
  try {
    const data = await getHawkishDaily()
    console.log('图表数据加载完成，后端返回', data.length, '天数据:')
    console.table(data)
    updateChart(data)
  } catch (error) {
    console.error('获取图表数据失败:', error)
    updateChart([])
  }
}

// 处理图表数据：X轴从2026-02-28开始完整显示每一天，填入后端返回的数据
const processChartData = (backendData: HawkishDailyData[]) => {
  // 转换为map方便查找
  const dailyMap: Record<string, number> = {}
  backendData.forEach(item => {
    dailyMap[item.date] = item.avg_score
  })

  // 生成从2026-02-28到今天的完整日期序列
  const startDate = dayjs('2026-02-28')
  const endDate = dayjs()
  const daysDiff = endDate.diff(startDate, 'day')

  const fullDates: string[] = []
  const fullAvgScores: (number | null)[] = []

  for (let i = 0; i <= daysDiff; i++) {
    const currentDate = startDate.add(i, 'day')
    const dateKey = currentDate.format('YYYY-MM-DD')
    fullDates.push(dateKey)
    if (dailyMap[dateKey] !== undefined) {
      fullAvgScores.push(dailyMap[dateKey])
    } else {
      fullAvgScores.push(NaN) // 没有数据的日期留空
    }
  }

  return { dates: fullDates, avgScores: fullAvgScores }
}

// 初始化图表
const initChart = () => {
  const chartDom = document.getElementById('hawkish-chart')
  if (!chartDom) return

  hawkishChart = echarts.init(chartDom)

  const option = {
    title: {
      text: '鹰派评分走势（按日平均）',
      left: 'center',
      textStyle: {
        fontSize: 16
      }
    },
    tooltip: {
      trigger: 'axis',
      formatter: '日期: {b}<br/>平均鹰派评分: {c}'
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '15%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: [],
      axisLabel: {
        rotate: 45,
        fontSize: 11
      }
    },
    yAxis: {
      type: 'value',
      min: 0,
      max: 100,
      name: '评分'
    },
    series: [
      {
        name: '平均鹰派评分',
        data: [],
        type: 'line',
        smooth: true,
        connectNulls: false,
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(245, 108, 108, 0.5)' },
            { offset: 1, color: 'rgba(245, 108, 108, 0.1)' }
          ])
        },
        lineStyle: {
          color: '#f56c6c',
          width: 2
        },
        itemStyle: {
          color: '#f56c6c'
        }
      }
    ]
  }

  hawkishChart.setOption(option)
}

// 更新图表数据
const updateChart = (backendData: HawkishDailyData[] = []) => {
  if (!hawkishChart) {
    initChart()
  }
  if (!hawkishChart) return

  const { dates, avgScores } = processChartData(backendData)

  const option = {
    xAxis: {
      data: dates
    },
    series: [
      {
        data: avgScores
      }
    ]
  }

  hawkishChart.setOption(option)
}

// 处理窗口大小变化
const resizeChart = () => {
  if (hawkishChart) {
    hawkishChart.resize()
  }
}

window.addEventListener('resize', resizeChart)

onMounted(() => {
  // 先初始化图表，再获取数据（确保DOM已经渲染完成）
  initChart()
  fetchStatements()
  fetchChartData()
})

onUnmounted(() => {
  window.removeEventListener('resize', resizeChart)
  if (hawkishChart) {
    hawkishChart.dispose()
    hawkishChart = null
  }
})
</script>

<template>
  <div>
    <el-card title="特朗普言行数据">      
      <!-- 鹰派评分曲线图 -->
      <div style="margin-bottom: 20px;">
        <div id="hawkish-chart" style="width: 100%; height: 300px;"></div>
      </div>

      <!-- 搜索栏 -->
      <div class="search-bar" style="margin-bottom: 20px;">
        <el-form :inline="true" class="demo-form-inline">
          <el-form-item label="数据源">
            <el-select v-model="searchParams.source" placeholder="请选择数据源" style="width: 180px;">
              <el-option label="全部" value="" />
              <el-option label="X (Twitter)" value="X (Twitter)" />
              <el-option label="Truth Social" value="Truth Social" />
              <el-option label="Fox News" value="Fox News" />
              <el-option label="BBC News" value="BBC News" />
              <el-option label="CNN" value="CNN" />
            </el-select>
          </el-form-item>
          <el-form-item label="开始时间">
            <el-date-picker
              v-model="searchParams.start_time"
              type="datetime"
              placeholder="选择开始时间"
              style="width: 200px;"
            />
          </el-form-item>
          <el-form-item label="结束时间">
            <el-date-picker
              v-model="searchParams.end_time"
              type="datetime"
              placeholder="选择结束时间"
              style="width: 200px;"
            />
          </el-form-item>
          <el-form-item label="关键词">
            <el-input v-model="searchParams.keyword" placeholder="请输入关键词" style="width: 200px;" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" @click="handleSearch">查询</el-button>
            <el-button @click="searchParams = { source: '', start_time: undefined, end_time: undefined, keyword: '' }">重置</el-button>
          </el-form-item>
        </el-form>
      </div>

      <!-- 数据表格 -->
      <el-table
        v-loading="loading"
        :data="statementList"
        border
        stripe
        style="width: 100%;"
      >
        <el-table-column prop="post_time" label="发布时间" width="180" align="center">
          <template #default="{ row }">
            {{ formatTime(row.post_time) }}
          </template>
        </el-table-column>
        <el-table-column prop="source" label="数据源" width="120" align="center" />
        <el-table-column label="情感倾向" width="160" align="center">
          <template #default="{ row }">
            <el-tag :type="getSentimentColor(row.sentiment)" style="margin-bottom:4px;">
              {{ getSentimentLabel(row.sentiment) }}
            </el-tag>
            <div style="font-size:18px; color:#7a90a8; margin-top:4px;">
              {{ getSentimentDesc(row.sentiment_score) }}
              <span style="margin-left:6px; color:#647a94;">({{ Number(row.sentiment_score).toFixed(2) }})</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="content" label="言行内容" min-width="300">
          <template #default="{ row }">
            <div class="content-cell">
              <template v-if="isUrlOnly(row.content)">
                <a :href="row.url || row.content" target="_blank" class="content-link">{{ row.url || row.content }}</a>
              </template>
              <template v-else>
                <div class="content-original">{{ row.content }}</div>
                <div v-if="row.translation" class="content-translation">{{ row.translation }}</div>
              </template>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="鹰派评分" width="110" align="center">
          <template #default="{ row }">
            <template v-if="row.hawkish_score != null">
              <div class="hawkish-score" :style="{ color: hawkishColor(row.hawkish_score) }">
                {{ row.hawkish_score }}
              </div>
              <div class="hawkish-label" :style="{ color: hawkishColor(row.hawkish_score) }">
                {{ hawkishLabel(row.hawkish_score) }}
              </div>
            </template>
            <span v-else style="color:#4a5a6e; font-size:12px;">—</span>
          </template>
        </el-table-column>
        <el-table-column label="互动数据" width="150" align="center">
          <template #default="{ row }">
            <div>👍 {{ row.likes || 0 }}</div>
            <div>🔄 {{ row.shares || 0 }}</div>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120" align="center">
          <template #default="{ row }">
            <el-button size="small" type="text" @click="handleDelete(row._id || '')">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <div style="margin-top: 20px; text-align: right;">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="handleSizeChange"
          @current-change="handlePageChange"
        />
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.search-bar {
  padding: 16px;
  background: var(--bg-card2, #1a2235);
  border-radius: 6px;
  border: 1px solid var(--border, #1e2d45);
}

.content-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.content-original {
  color: var(--text-primary, rgb(65, 66, 68));
  font-size: 20px; /* 原 13px 加大 50% */
  line-height: 1.6;
  font-weight: 500; /* 加粗提高可读性 */
}

.content-translation {
  color: var(--text-secondary, #90a8c3); /* 提高对比度 */
  font-size: 18px; /* 原 12px 加大 50% */
  line-height: 1.6;
  border-left: 3px solid #2d3f55;
  padding-left: 12px;
}

.hawkish-score {
  font-size: 30px; /* 原 20px 加大 50% */
  font-weight: 800;
  line-height: 1.2;
}

.hawkish-label {
  font-size: 17px; /* 原 11px 加大 50% */
  font-weight: 600;
  margin-top: 4px;
}

.content-link {
  color: #4a9eff;
  font-size: 18px; /* 原 12px 加大 50% */
  word-break: break-all;
  text-decoration: none;
}
.content-link:hover {
  text-decoration: underline;
}
</style>