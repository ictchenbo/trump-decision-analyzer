@echo off
chcp 65001 >nul
echo ========================================
echo    特朗普决策分析系统 - 一键启动
echo ========================================
echo.

REM 检查当前目录是否正确（应该在项目根目录）
if not exist "backend\app\main.py" (
    echo 错误：当前目录不对，请从项目根目录运行此脚本！
    echo 当前目录: %cd%
    pause
    exit /b 1
)

REM 设置Python环境 - 在Windows cmd中需要调用conda.bat
echo 正在激活 conda 环境...
call %USERPROFILE%\anaconda3\Scripts\conda.bat activate base
if errorlevel 1 (
    echo.
    echo 错误：conda 激活失败！请检查路径：%USERPROFILE%\anaconda3\Scripts\conda.bat
    echo 如果你的 conda 安装在其他位置，请编辑此脚本修改路径。
    pause
    exit /b 1
)

echo conda 环境激活成功！
echo.

REM 启动后端API
echo 启动后端API服务...
start "后端API" cmd /k "cd backend && python -m app.main"
if errorlevel 1 (
    echo 警告：后端启动可能有问题
)

timeout /t 2 /nobreak >nul

REM 启动前端开发服务器
echo 启动前端开发服务器...
start "前端 - Vite Dev Server" cmd /k "cd src\frontend && npm run dev"
if errorlevel 1 (
    echo 警告：前端启动可能有问题
)

timeout /t 2 /nobreak >nul

REM 启动数据采集器
echo 启动定时数据采集器...
start "数据采集 - 定时任务" cmd /k "cd backend && python -m app.ingestion.run_ingestion"
if errorlevel 1 (
    echo 警告：数据采集启动可能有问题
)

echo.
echo ========================================
echo 三个服务已在独立窗口启动：
echo   1. 后端API: http://localhost:8000
echo   2. 前端: 看上面窗口输出的地址（通常是 http://localhost:5173）
echo   3. 数据采集: 自动定时运行
echo ========================================
echo 如果某个窗口一闪而过，请检查该窗口的错误信息！
echo.
pause
