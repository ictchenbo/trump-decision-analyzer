# 特朗普决策影响因子分析系统 - 后端

## 技术栈
- **框架**: FastAPI
- **数据库**: MongoDB (异步驱动 motor)
- **语言**: Python 3.11+

## 快速开始

### 1. 安装依赖
```bash
pip install -r requirements.txt
```

### 2. 启动MongoDB
确保本地MongoDB服务已启动，或者修改`.env`文件中的MongoDB连接地址

### 3. 启动后端服务
```bash
cd app
python main.py
```

或者使用uvicorn直接启动：
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## 接口文档
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **Markdown格式文档**: http://localhost:8000/docs/markdown
- **HTML格式文档**: http://localhost:8000/docs/html

## 项目结构
```
backend/
├── app/
│   ├── api/              # 接口路由
│   │   ├── data.py       # 实时数据接口
│   │   ├── analysis.py   # 分析接口
│   │   └── alerts.py     # 预警接口
│   ├── models/           # 数据模型
│   ├── core/             # 核心配置
│   └── main.py           # 应用入口
├── docs/                 # 文档目录
├── .env                  # 环境配置
└── requirements.txt      # 依赖列表
```

## 可用接口

### 数据接口
- `GET /api/v1/data/real-time` - 获取实时数据
- `POST /api/v1/data/real-time` - 添加实时数据
- `GET /api/v1/data/history` - 获取历史事件数据

### 分析接口
- `POST /api/v1/analysis/composite-index` - 计算综合影响指数
- `GET /api/v1/analysis/timeline/{event_id}` - 获取事件时间轴
- `POST /api/v1/analysis/simulate` - 运行反事实模拟

### 预警接口
- `GET /api/v1/alerts/` - 获取预警列表
- `POST /api/v1/alerts/` - 创建预警
- `PUT /api/v1/alerts/{alert_id}/status` - 更新预警状态
- `DELETE /api/v1/alerts/{alert_id}` - 删除预警
