<template>
  <el-container class="app-container">
    <el-header class="app-header">
      <div class="app-brand">
        <router-link to="/" class="brand-link">
          <span class="brand-logo">📦</span>
          <span class="brand-title">阿里国际站素材抓取</span>
        </router-link>
      </div>
    </el-header>
    <el-main class="app-main">
      <router-view />
    </el-main>
  </el-container>
</template>

<script setup>
</script>

<style>
* {
  box-sizing: border-box;
}

html,
body,
#app {
  height: 100%;
  margin: 0;
  padding: 0;
}

body {
  background: #f5f7fa;
  font-family: 'Helvetica Neue', Helvetica, 'PingFang SC', 'Hiragino Sans GB',
    'Microsoft YaHei', Arial, sans-serif;
  color: #303133;
  -webkit-font-smoothing: antialiased;
}
</style>

<style scoped>
.app-container {
  height: 100vh;
}

.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #fff;
  border-bottom: 1px solid #e4e7ed;
  box-shadow: 0 1px 4px rgba(0, 21, 41, 0.08);
}

.brand-link {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  text-decoration: none;
}

.brand-logo {
  font-size: 22px;
}

.brand-title {
  font-size: 18px;
  font-weight: 600;
  color: #303133;
}

.app-main {
  padding: 20px;
  overflow-y: auto;
}
</style>
