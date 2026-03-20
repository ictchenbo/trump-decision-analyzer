<script setup lang="ts">
import { RouterView, useRoute } from 'vue-router'
import { Monitor, TrendCharts, Aim, ChatDotRound, DataAnalysis } from '@element-plus/icons-vue'

const route = useRoute()
</script>

<template>
  <div class="app-layout">
    <header class="app-header">
      <div class="header-brand">
        <span class="brand-dot"></span>
        <span class="brand-title">特朗普决策影响因子分析系统</span>
        <span class="brand-badge">LIVE</span>
      </div>
      <nav class="header-nav">
        <router-link to="/regression" class="nav-item" :class="{ active: route.path === '/regression' }">
          <el-icon><DataAnalysis /></el-icon><span>决策建模</span>
        </router-link>
        <router-link to="/statements" class="nav-item" :class="{ active: route.path === '/statements' }">
          <el-icon><ChatDotRound /></el-icon><span>言论监测</span>
        </router-link>
        <router-link to="/" class="nav-item" :class="{ active: route.path === '/' }">
          <el-icon><Monitor /></el-icon><span>指标看板</span>
        </router-link>
        <!-- <router-link to="/decision-pressure" class="nav-item" :class="{ active: route.path === '/decision-pressure' }">
          <el-icon><TrendCharts /></el-icon><span>决策压力分析</span>
        </router-link> -->
        <router-link to="/war-peace" class="nav-item" :class="{ active: route.path === '/war-peace' }">
          <el-icon><Aim /></el-icon><span>战争倾向分析</span>
        </router-link>
      </nav>
      <div class="header-time" id="header-clock"></div>
    </header>
    <main class="app-main">
      <RouterView />
    </main>
  </div>
</template>

<script lang="ts">
export default {
  mounted() {
    const el = document.getElementById('header-clock')
    const tick = () => {
      if (el) el.textContent = new Date().toLocaleString('zh-CN', { hour12: false })
    }
    tick()
    setInterval(tick, 1000)
  }
}
</script>

<style scoped>
.app-layout {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  background: var(--bg-base);
}

.app-header {
  display: flex;
  align-items: center;
  height: 72px;
  padding: 0 32px;
  background: var(--bg-card);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
  gap: 40px;
}

.header-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.brand-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--accent);
  box-shadow: 0 0 10px var(--accent);
  animation: pulse 2s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0.4; }
}

.brand-title {
  font-size: 24px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: 1px;
  white-space: nowrap;
}

.brand-badge {
  font-size: 12px;
  font-weight: 700;
  color: #ef4444;
  border: 1px solid #ef4444;
  border-radius: 3px;
  padding: 2px 6px;
  letter-spacing: 1px;
  animation: pulse 1.5s ease-in-out infinite;
}

.header-nav {
  display: flex;
  align-items: center;
  gap: 4px;
  flex: 1;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 18px;
  border-radius: 6px;
  font-size: 18px;
  color: var(--text-primary);
  text-decoration: none;
  transition: all 0.2s;
  border-bottom: 2px solid transparent;
}

.nav-item:hover {
  color: var(--text-primary);
  background: rgba(255,255,255,0.05);
}

.nav-item.active {
  color: var(--accent);
  background: var(--accent-glow);
  border-bottom-color: var(--accent);
}

.header-time {
  flex-shrink: 0;
  font-size: 16px;
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.5px;
}

.app-main {
  flex: 1;
  padding: 16px 20px;
  overflow-y: auto;
}
</style>
