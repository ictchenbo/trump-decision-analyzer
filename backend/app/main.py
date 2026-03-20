import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import uvicorn
import logging
import markdown
from app.api import data, analysis, alerts, trump_statements, images
from datetime import datetime
from app.core.config import settings
from app.core.database import db

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 创建FastAPI应用
app = FastAPI(
    title="特朗普决策影响因子分析系统API",
    description="基于FastAPI构建的实时决策分析系统后端接口",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(data.router, prefix=settings.API_PREFIX)
app.include_router(analysis.router, prefix=settings.API_PREFIX)
app.include_router(alerts.router, prefix=settings.API_PREFIX)
app.include_router(trump_statements.router, prefix=settings.API_PREFIX)
app.include_router(images.router, prefix=settings.API_PREFIX)

# 初始化数据库连接
@app.on_event("startup")
async def startup_db():
    db.connect()

@app.on_event("shutdown")
async def shutdown_db():
    db.disconnect()

# 根路由
@app.get("/", tags=["root"])
async def root():
    return {"message": "特朗普决策影响因子分析系统API", "docs": "/docs", "redoc": "/redoc"}

# 生成接口文档的Markdown和HTML
@app.get("/docs/markdown", tags=["docs"])
async def get_docs_markdown():
    """导出接口文档为Markdown格式"""
    from fastapi.openapi.utils import get_openapi
    
    openapi_schema = get_openapi(
        title=app.title,
        description=app.description,
        version=app.version,
        routes=app.routes,
    )
    
    # 转换为Markdown文档
    md_content = f"# 特朗普决策影响因子分析系统API文档\n\n"
    md_content += f"版本: {app.version}\n\n"
    md_content += f"生成时间: {datetime.utcnow().isoformat()}\n\n"
    md_content += "## 接口列表\n\n"
    
    for path, path_item in openapi_schema["paths"].items():
        for method, operation in path_item.items():
            md_content += f"### {method.upper()} {path}\n"
            md_content += f"{operation.get('summary', '')}\n\n"
            if "parameters" in operation:
                md_content += "**参数**:\n\n"
                for param in operation["parameters"]:
                    md_content += f"- `{param['name']}`: {param.get('description', '')} ({param['in']})\n"
            if "requestBody" in operation:
                md_content += "**请求体**:\n\n```json\n" + str(operation["requestBody"]["content"]["application/json"]["schema"])
                md_content += "\n```\n\n"
            md_content += "\n"
    
    # 保存Markdown文档
    import os
    os.makedirs("docs", exist_ok=True)
    md_path = os.path.join(os.path.dirname(__file__), "..", "docs", "api_docs.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)
    
    return FileResponse(md_path, media_type="text/markdown", filename="api_docs.md")

@app.get("/docs/html", tags=["docs"])
async def get_docs_html():
    """导出接口文档为HTML格式"""
    from fastapi.openapi.utils import get_openapi
    
    # 先获取Markdown内容
    markdown_response = await get_docs_markdown()
    
    # 读取Markdown文件
    import os
    md_path = os.path.join(os.path.dirname(__file__), "..", "docs", "api_docs.md")
    with open(md_path, "r", encoding="utf-8") as f:
        md_content = f.read()
    
    # 转换为HTML
    html_content = f"""
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <title>特朗普决策影响因子分析系统API文档</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; line-height: 1.6; }}
            h1 {{ color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; }}
            h2 {{ color: #34495e; margin-top: 30px; border-bottom: 1px solid #eee; padding-bottom: 5px; }}
            h3 {{ color: #3498db; margin-top: 20px; }}
            pre {{ background: #f8f9fa; padding: 12px; border-radius: 4px; overflow-x: auto; border: 1px solid #e6e6e6; }}
            code {{ background: #f8f9fa; padding: 2px 4px; border-radius: 4px; font-family: 'Consolas', 'Monaco', monospace; }}
            table {{ border-collapse: collapse; width: 100%; margin: 15px 0; }}
            th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
            th {{ background-color: #f2f2f2; }}
        </style>
    </head>
    <body>
        {markdown.markdown(md_content)}
    </body>
    </html>
    """
    
    html_path = os.path.join(os.path.dirname(__file__), "..", "docs", "api_docs.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    
    return FileResponse(html_path, media_type="text/html", filename="api_docs.html")

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.PORT, reload=True)
