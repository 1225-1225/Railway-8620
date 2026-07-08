<template>
  <div class="sidebar" :class="{ collapsed }">
    <!-- 折叠/展开按钮 -->
    <button class="toggle-btn" @click="$emit('toggle')" :title="collapsed ? '展开历史' : '收起历史'">
      <span v-if="collapsed">☰</span>
      <span v-else>✕</span>
    </button>

    <div class="sidebar-content" v-show="!collapsed">
      <div class="sidebar-header">
        <h3>历史对话</h3>
        <button class="new-chat-btn" @click="$emit('new-chat')">＋ 新对话</button>
      </div>

      <!-- 加载中 -->
      <div v-if="loading" class="loading-state">
        <span class="loading-dots">加载中</span>
      </div>

      <!-- 空状态 -->
      <div v-else-if="!groups || groups.length === 0" class="empty-state">
        <p>暂无历史记录</p>
      </div>

      <!-- 会话列表 -->
      <div v-else class="session-list" ref="listRef">
        <div v-for="group in groups" :key="group.date" class="date-group">
          <div class="date-header">{{ formatDateHeader(group.date) }}</div>
          <div
            v-for="session in group.sessions"
            :key="session.thread_id"
            class="session-item"
            :class="{ active: session.thread_id === activeThreadId }"
            @click="$emit('select-session', session.thread_id)"
          >
            <div class="session-preview">{{ session.preview }}</div>
            <div class="session-time">{{ session.time }}</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

export interface SessionGroup {
  date: string
  sessions: Array<{
    thread_id: string
    preview: string
    time: string
    created_at: string
  }>
}

defineProps<{
  collapsed: boolean
  loading: boolean
  groups: SessionGroup[]
  activeThreadId: string
}>()

defineEmits<{
  toggle: []
  'new-chat': []
  'select-session': [threadId: string]
}>()

function formatDateHeader(dateStr: string): string {
  const today = new Date()
  const target = new Date(dateStr)
  const todayStr = today.toISOString().slice(0, 10)
  const yesterday = new Date(today)
  yesterday.setDate(yesterday.getDate() - 1)
  const yesterdayStr = yesterday.toISOString().slice(0, 10)

  if (dateStr === todayStr) return '今天'
  if (dateStr === yesterdayStr) return '昨天'
  // 检查是否为本周
  const targetDate = new Date(dateStr)
  const weekDay = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']
  const diffDays = Math.floor((today.getTime() - targetDate.getTime()) / (1000 * 60 * 60 * 24))
  if (diffDays <= 7 && targetDate.getDay() <= today.getDay()) {
    return weekDay[targetDate.getDay()]
  }
  return dateStr
}
</script>

<style scoped>
.sidebar {
  position: relative;
  height: 100%;
  background: rgba(255, 255, 255, 0.03);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border-right: 1px solid rgba(255, 255, 255, 0.08);
  transition: width 0.3s ease;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}

.sidebar:not(.collapsed) {
  width: 280px;
}

.sidebar.collapsed {
  width: 40px;
}

.toggle-btn {
  position: absolute;
  top: 12px;
  right: 8px;
  z-index: 20;
  width: 28px;
  height: 28px;
  border: none;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.06);
  color: rgba(255, 255, 255, 0.6);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  transition: all 0.2s;
}

.toggle-btn:hover {
  background: rgba(255, 255, 255, 0.12);
  color: white;
}

.sidebar-content {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
  padding-top: 50px;
}

.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px 12px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  flex-shrink: 0;
}

.sidebar-header h3 {
  color: white;
  font-size: 14px;
  font-weight: 600;
  margin: 0;
}

.new-chat-btn {
  padding: 4px 10px;
  border: none;
  border-radius: 8px;
  background: linear-gradient(135deg, rgba(90, 103, 216, 0.4), rgba(139, 92, 246, 0.4));
  color: white;
  font-size: 11px;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
}

.new-chat-btn:hover {
  background: linear-gradient(135deg, rgba(90, 103, 216, 0.7), rgba(139, 92, 246, 0.7));
  transform: translateY(-1px);
}

.loading-state,
.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px 16px;
  color: rgba(255, 255, 255, 0.4);
  font-size: 13px;
}

.session-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px 8px 16px;
}

.date-group {
  margin-bottom: 8px;
}

.date-header {
  padding: 8px 12px 4px;
  font-size: 11px;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.35);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.session-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 10px 12px;
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.2s;
  margin-bottom: 2px;
}

.session-item:hover {
  background: rgba(255, 255, 255, 0.06);
}

.session-item.active {
  background: rgba(90, 103, 216, 0.15);
  border: 1px solid rgba(90, 103, 216, 0.2);
}

.session-preview {
  font-size: 13px;
  color: rgba(255, 255, 255, 0.8);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  line-height: 1.3;
}

.session-time {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.3);
}

.session-list::-webkit-scrollbar {
  width: 4px;
}

.session-list::-webkit-scrollbar-track {
  background: transparent;
}

.session-list::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.1);
  border-radius: 4px;
}
</style>
