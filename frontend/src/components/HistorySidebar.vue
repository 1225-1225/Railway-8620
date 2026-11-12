<template>
  <div class="sidebar" :class="{ collapsed }">
    <!-- 折叠/展开按钮 -->
    <button class="toggle-btn" @click="$emit('toggle')" :title="collapsed ? '展开历史' : '收起历史'">
      <svg v-if="collapsed" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true">
        <path d="M4 7h16M4 12h16M4 17h16" />
      </svg>
      <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true">
        <path d="M6 6l12 12M18 6L6 18" />
      </svg>
    </button>

    <div class="sidebar-content" v-show="!collapsed">
      <div class="sidebar-header">
        <h3>历史对话</h3>
        <button class="new-chat-btn" @click="$emit('new-chat')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
            <path d="M12 5v14M5 12h14" />
          </svg>新对话
        </button>
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
            <!-- 行内重命名编辑态 -->
            <input
              v-if="renamingId === session.thread_id"
              v-model="renamingTitle"
              class="rename-input"
              maxlength="100"
              @click.stop
              @vue:mounted="focusRenameInput"
              @keyup.enter="confirmRename(session.thread_id)"
              @keyup.esc="cancelRename"
              @blur="confirmRename(session.thread_id)"
            />
            <template v-else>
              <div class="session-preview">{{ session.preview }}</div>
              <div class="session-meta">
                <span class="session-time">{{ session.time }}</span>
                <span class="session-actions">
                  <button
                    class="rename-btn"
                    title="重命名会话"
                    @click.stop="startRename(session)"
                  >
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                      <path d="M4 20h4l10-10a2.8 2.8 0 0 0-4-4L4 16z" />
                    </svg>
                  </button>
                  <button
                    class="delete-btn"
                    title="删除会话"
                    @click.stop="$emit('delete-session', session.thread_id)"
                  >
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                      <path d="M4 7h16M9 7V5h6v2M6 7l1 13h10l1-13" />
                    </svg>
                  </button>
                </span>
              </div>
            </template>
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

const emit = defineEmits<{
  toggle: []
  'new-chat': []
  'select-session': [threadId: string]
  'rename-session': [threadId: string, newTitle: string]
  'delete-session': [threadId: string]
}>()

// ── 行内重命名状态 ──
const renamingId = ref('')
const renamingTitle = ref('')

/** input 挂载后聚焦并全选（v-for 中 ref 会收集为数组，改用 mounted 钩子） */
function focusRenameInput(event: unknown) {
  const el = (event as { el?: HTMLInputElement }).el
  if (el) {
    el.focus()
    el.select()
  }
}

function startRename(session: { thread_id: string; preview: string }) {
  renamingId.value = session.thread_id
  renamingTitle.value = session.preview
}

function confirmRename(threadId: string) {
  if (renamingId.value !== threadId) return // 已由 blur/enter 处理过
  const title = renamingTitle.value.trim()
  renamingId.value = ''
  if (title) {
    emit('rename-session', threadId, title)
  }
}

function cancelRename() {
  renamingId.value = ''
}

function formatDateHeader(dateStr: string): string {
  const today = new Date()
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
    return weekDay[targetDate.getDay()] ?? dateStr
  }
  return dateStr
}
</script>

<style scoped>
.sidebar {
  position: relative;
  height: 100%;
  background: var(--ink-800);
  border-right: 1px solid var(--border);
  /* 折叠动画用 transform 平移，而非 transition width
     （width 会触发布局重排，且 sloplint 规则 10a 明确禁止） */
  transition: transform var(--dur-mid) var(--ease);
  overflow: hidden;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  will-change: transform;
}

.sidebar:not(.collapsed) {
  width: 280px;
  transform: translateX(0);
}

.sidebar.collapsed {
  width: 44px;
  transform: translateX(0);
}

.toggle-btn {
  position: absolute;
  top: var(--sp-3);
  right: var(--sp-2);
  z-index: 20;
  width: 28px;
  height: 28px;
  border: 1px solid transparent;
  border-radius: var(--r-sm);
  background: transparent;
  color: var(--text-300);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition:
    background var(--dur-fast) var(--ease),
    color var(--dur-fast) var(--ease),
    border-color var(--dur-fast) var(--ease);
}

.toggle-btn svg {
  width: 15px;
  height: 15px;
}

.toggle-btn:hover {
  background: var(--ink-700);
  color: var(--text-100);
  border-color: var(--border);
}

.toggle-btn:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

.toggle-btn:active {
  background: var(--ink-600);
}

.sidebar-content {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
  padding-top: 48px;
}

.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-2);
  padding: 0 var(--sp-4) var(--sp-3);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.sidebar-header h3 {
  color: var(--text-100);
  font-size: var(--fs-sm);
  font-weight: 600;
  margin: 0;
  letter-spacing: 0;
}

.new-chat-btn {
  display: inline-flex;
  align-items: center;
  gap: var(--sp-1);
  padding: var(--sp-1) var(--sp-3);
  border: 1px solid var(--border);
  border-radius: var(--r-sm);
  background: transparent;
  color: var(--text-200);
  font-size: var(--fs-xs);
  cursor: pointer;
  transition:
    background var(--dur-fast) var(--ease),
    border-color var(--dur-fast) var(--ease),
    color var(--dur-fast) var(--ease);
  white-space: nowrap;
}

.new-chat-btn svg {
  width: 12px;
  height: 12px;
}

.new-chat-btn:hover {
  background: var(--accent-wash);
  border-color: var(--accent-line);
  color: var(--accent);
}

.new-chat-btn:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

.new-chat-btn:active {
  background: var(--ink-600);
}

.loading-state,
.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--sp-10) var(--sp-4);
  color: var(--text-400);
  font-size: var(--fs-sm);
}

.session-list {
  flex: 1;
  overflow-y: auto;
  padding: var(--sp-2) var(--sp-2) var(--sp-4);
}

.date-group {
  margin-bottom: var(--sp-2);
}

.date-header {
  padding: var(--sp-2) var(--sp-3) var(--sp-1);
  font-size: var(--fs-xs);
  font-weight: 500;
  color: var(--text-400);
}

.session-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: var(--sp-2) var(--sp-3);
  border: 1px solid transparent;
  border-radius: var(--r-sm);
  cursor: pointer;
  transition:
    background var(--dur-fast) var(--ease),
    border-color var(--dur-fast) var(--ease);
  margin-bottom: 2px;
}

.session-item:hover {
  background: var(--ink-700);
}

.session-item:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: -2px;
}

.session-item.active {
  background: var(--accent-wash);
  border-color: var(--accent-line);
}

.session-item:active {
  background: var(--ink-600);
}

.session-preview {
  font-size: var(--fs-sm);
  color: var(--text-200);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  line-height: 1.4;
}

.session-item.active .session-preview {
  color: var(--text-100);
}

.session-time {
  font-size: var(--fs-xs);
  color: var(--text-400);
}

.session-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-1);
}

.session-actions {
  display: flex;
  align-items: center;
  gap: 2px;
  opacity: 0;
  transition: opacity var(--dur-fast) var(--ease);
}

.session-item:hover .session-actions,
.session-item:focus-within .session-actions {
  opacity: 1;
}

.rename-btn,
.delete-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border: none;
  background: transparent;
  color: var(--text-400);
  cursor: pointer;
  padding: 0;
  border-radius: 4px;
  transition:
    color var(--dur-fast) var(--ease),
    background var(--dur-fast) var(--ease);
}

.rename-btn svg,
.delete-btn svg {
  width: 13px;
  height: 13px;
}

.rename-btn:hover {
  color: var(--accent);
  background: var(--accent-wash);
}

.delete-btn:hover {
  color: var(--danger);
  background: var(--danger-wash);
}

.rename-btn:focus-visible,
.delete-btn:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 1px;
}

.rename-btn:disabled,
.delete-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.rename-input {
  width: 100%;
  padding: var(--sp-1) var(--sp-2);
  border: 1px solid var(--accent-line);
  border-radius: var(--r-sm);
  background: var(--ink-900);
  color: var(--text-100);
  font-size: var(--fs-sm);
  font-family: var(--font-body);
  outline: none;
}

.rename-input:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 1px;
}

.session-list::-webkit-scrollbar {
  width: 4px;
}

.session-list::-webkit-scrollbar-track {
  background: transparent;
}

.session-list::-webkit-scrollbar-thumb {
  background: var(--ink-600);
  border-radius: 4px;
}

@media (prefers-reduced-motion: reduce) {
  .sidebar,
  .toggle-btn,
  .session-item,
  .new-chat-btn,
  .session-actions,
  .rename-btn,
  .delete-btn {
    transition: none;
  }
}
</style>
