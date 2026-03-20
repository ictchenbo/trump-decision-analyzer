# 🇺🇸 特朗普决策分析系统 / Trump Decision Analyzer

> 量化分析市场因子与特朗普鹰派言论之间的因果关系 / Quantitative analysis of the causal relationship between market factors and Trump's hawkish rhetoric

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688.svg)](https://fastapi.tiangolo.com/)
[![Vue](https://img.shields.io/badge/Vue-3.x-4FC08D.svg)](https://vuejs.org/)
[![MongoDB](https://img.shields.io/badge/MongoDB-4.x-green.svg)](https://www.mongodb.com/)

## 📋 项目简介

这是一个**实证研究项目**，旨在通过数据科学方法回答一个核心问题：

> **市场状况 / 政治指标 (X) 是否会影响特朗普对伊朗/石油问题的鹰派言论强度 (Y)？**

项目支持双向分析：

- 🔹 **方向A（原假设）**：市场变化 → 特朗普言论调整。油价上涨/股市下跌是否会导致特朗普发表更多鹰派言论转移国内矛盾？
- 🔹 **方向B（反向因果）**：特朗普言论 → 市场反应。鹰派言论是否会领先市场变化？
- 🔹 **滞后效应分析**：支持对鹰派评分做滞后1天处理，研究昨日言论对今日市场的前瞻性影响。

### 🎯 研究问题背后的两种机制

| 机制 | 逻辑路径 |
|------|---------|
| **政治反应机制** | 市场/油价/支持率变化 → 特朗普调整对外强硬程度 → 发表更鹰派或缓和言论 |
| **共同原因机制** | 中东冲突/地缘事件 → 同时推高油价 + 引发特朗普鹰派发言 → 虚假相关性 |

## ✨ 功能特性

### 数据分析能力
- ✅ **双向相关性分析**：支持 `市场→鹰派` 和 `鹰派→市场` 两种分析模式
- ✅ **滞后效应分析**：支持对自变量做 1/3/7 天滞后处理，支持鹰派评分滞后1天分析
- ✅ **多元因变量支持**：鹰派评分均值/最大值/鹰派帖子比例/发帖数量/鹰派词汇均值五种统计量
- ✅ **一元线性回归**：每个指标独立回归，输出相关系数 r 和决定系数 R²
- ✅ **时间趋势可视化**：归一化后展示 X 和 Y 的时间走势对比

### 数据采集
- ✅ 自动从 Truth Social 抓取特朗普最新言论
- ✅ 使用 LLM (GPT) 对言论进行鹰派评分（0-100）
- ✅ 自动采集每日市场数据（原油、黄金、股指、国债收益率等）
- ✅ 支持定时自动更新数据

### 技术架构
- 🚀 后端：**FastAPI** + **MongoDB** + **NumPy** 统计计算
- 🎨 前端：**Vue 3 + TypeScript + Vite** + **Element Plus** + **ECharts**
- 📊 完整的前后端分离架构，支持实时交互分析

## 📊 分析模式

项目支持三种分析模式：

| 模式 | X | Y | 研究问题 |
|------|---|---|----------|
| **市场→鹰派** | 市场指标 | 鹰派评分 | 市场状况是否影响特朗普言论倾向？ |
| **鹰派→市场** | 鹰派评分 | 市场指标 | 特朗普言论是否影响当日市场？ |
| **鹰派滞后1天→市场** | 昨日鹰派评分 | 今日市场指标 | 特朗普言论是否对次日市场有前瞻性影响？ |

## 🖼️ 界面预览

<p align="center">
  <img src="docs/images/dashboard.png" alt="仪表盘" width="800">
  <br>
  <em>📊 数据分析仪表盘 - 实时展示鹰派评分走势和市场指标</em>
</p>

<p align="center">
  <img src="docs/images/regression.png" alt="回归分析" width="800">
  <br>
  <em>📈 回归分析界面 - 双向因果分析，支持滞后效应检验</em>
</p>

## 🗺️ 项目结构

```
trump-decision-analyzer/
├── backend/                      # 后端代码
│   ├── app/
│   │   ├── api/                 # API 路由
│   │   │   ├── analysis.py     # 相关性分析接口
│   │   │   ├── data.py          # 数据查询接口
│   │   │   ├── alerts.py        # 预警接口
│   │   │   └── trump_statements.py  # 言论查询
│   │   ├── core/                # 核心配置
│   │   │   ├── config.py        # 环境配置
│   │   │   └── database.py      # MongoDB 连接
│   │   ├── ingestion/           # 数据采集模块
│   │   │   ├── trump_statement_ingestor.py  # Truth Social 采集
│   │   │   ├── factor_score_ingestor.py     # 市场因子采集
│   │   │   ├── llm_enricher.py              # LLM 鹰派评分
│   │   │   └── run_ingestion.py            # 定时采集任务
│   │   ├── models/              # 数据模型
│   │   ├── ingestion/prompts/  # LLM 提示词
│   │   └── main.py              # FastAPI 入口
│   ├── .env.example             # 环境变量示例
│   └── requirements.txt
├── frontend/                     # 前端代码
│   ├── src/
│   │   ├── views/
│   │   │   ├── Dashboard.vue     # 仪表盘
│   │   │   ├── Regression.vue    # 回归分析页面
│   │   │   ├── DecisionPressure.vue  # 决策压力指数
│   │   │   ├── TrumpStatements.vue   # 言论列表
│   │   │   └── WarPeace.vue     # 战争和平指数
│   │   ├── api/                 # API 调用
│   │   ├── components/          # 公共组件
│   │   ├── models/             # 类型定义
│   │   ├── router/             # 路由配置
│   │   └── App.vue             # 主应用
│   ├── package.json
│   ├── vite.config.ts
│   └── tsconfig.json
├── vibe-design/                 # 产品设计文档
├── start-all.bat               # Windows 一键启动脚本
└── README.md
```

## 🚀 快速开始

### 环境要求

- Python 3.10+
- Node.js 18+
- MongoDB
- Conda (推荐)

### 安装步骤

1. **克隆项目**
```bash
git clone https://github.com/ictchenbo/trump-decision-analyzer.git
cd trump-decision-analyzer
```

2. **安装后端依赖**
```bash
cd backend
pip install -r requirements.txt
```

3. **安装前端依赖**
```bash
cd ../frontend
npm install
```

4. **配置环境变量**

创建 `backend/.env` 文件：
```env
MONGODB_URL=mongodb://localhost:27017
MONGODB_DB_NAME=trump_analyzer
OPENAI_API_KEY=your-openai-api-key-here
API_PREFIX=/api
PORT=8000
```

5. **插入测试数据**
```bash
python insert_test_data.py
```

6. **启动服务**

Windows 一键启动：
```bash
start-all.bat
```

手动启动：
```bash
# 终端1: 启动后端
cd backend
python -m app.main

# 终端2: 启动前端
cd ../frontend
npm run dev

# 终端3: 启动定时数据采集 (可选)
cd ../backend
python -m app.ingestion.run_ingestion
```

7. **访问应用**

- 前端地址：http://localhost:8080
- 后端API文档：http://localhost:8000/docs

## 📈 使用示例

### 1. 分析市场对鹰派言论的影响

选择分析模式 **市场→鹰派**，选择因变量 `鹰派评分均值`，查看相关性排行：

- 油价上涨是否导致特朗普更鹰派？
- VIX 恐慌指数升高是否增加鹰派言论概率？
- 支持率下降是否让特朗普更强硬？

### 2. 分析鹰派言论对市场的影响

选择分析模式 **鹰派→市场**，选择因变量 `布伦特原油期货`，查看：

- 今日鹰派言论是否与今日油价相关？
- 相关性是正还是负？

### 3. 分析滞后效应

选择分析模式 **鹰派滞后1天→市场**，研究昨日鹰派言论对今日市场的影响，检验是否存在前瞻性预测能力。

## 📝 研究背景

这个项目源自一个有趣的政治学/经济学实证问题：**政治领导人的言论是否受市场状况驱动？**

传统观点认为：
- 油价上涨 → 民生痛苦指数上升 → 特朗普倾向对伊朗出手转移视线
- 支持率下滑 → 特朗普需要通过对外强硬巩固基本盘

本项目通过收集真实数据进行量化检验，验证这些假设是否成立。

## 🔬 方法论

项目当前采用 **单变量回归 + 滞后分析** 方法：

1. **数据频率**：日度数据，从 2026-02-28 开始
2. **变量定义**：
   - X：15+ 市场/政治指标，支持滞后 1/3/7 天
   - Y：五种鹰派言论统计量
3. **分析方法**：对每个 X 做一元线性回归 Y ~ X，报告相关系数 r 和 R²
4. **双向分析**：支持 X 和 Y 互换，检验反向因果

## 🛠️ 更新日志

### 2026-03-21
- ✅ 完善 `.gitignore`，忽略不适合提交的本地文件
- ✅ 整理项目结构，准备开源发布

### 2026-03-20
- ✅ 移除了原横轴为X的散点图，只保留时间趋势图，界面更简洁
- ✅ **新增 XY 互换分析模式**：支持鹰派评分作为X，市场指标作为Y
- ✅ **新增鹰派滞后1天分析**：研究昨日鹰派言论对今日市场的影响
- ✅ 前端新增分析模式切换器，根据模式动态更新说明
- ✅ 时间趋势图对任意X/Y都做归一化处理，支持可视化对比

## 📄 许可证

MIT License - 详见 [LICENSE](LICENSE)

## ⭐ 致谢

感谢以下开源项目：
- [FastAPI](https://fastapi.tiangolo.com/) - 高效后端框架
- [Vue.js](https://vuejs.org/) - 渐进式前端框架
- [ECharts](https://echarts.apache.org/) - 强大的可视化库
- [Element Plus](https://element-plus.org/) - 优秀的Vue组件库

---

**发现问题欢迎提 Issue，欢迎交流讨论研究发现！**
