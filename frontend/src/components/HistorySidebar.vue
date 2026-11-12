<template>
  <div
    class="sidebar"
    :class="{ collapsed }"
    :style="collapsed ? undefined : { width: width + 'px' }"
  >
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

    <!-- 底部账号区：头像 + 用户名 + 菜单 -->
    <div class="account-bar" ref="accountRef">
      <button
        class="account-trigger"
        type="button"
        :aria-expanded="menuOpen"
        aria-haspopup="menu"
        @click="toggleMenu"
      >
        <span class="avatar-badge" aria-hidden="true">{{ initial }}</span>
        <span class="account-name" :title="username">{{ username || '未登录' }}</span>
        <svg class="chevron" :class="{ open: menuOpen }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M6 9l6 6 6-6" />
        </svg>
      </button>

      <div v-if="menuOpen" class="account-menu" role="menu">
        <div class="account-menu-head">
          <span class="avatar-badge lg" aria-hidden="true">{{ initial }}</span>
          <div class="account-menu-id">
            <div class="account-menu-name">{{ username || '未登录' }}</div>
            <div class="account-menu-sub">已登录</div>
          </div>
        </div>
        <div class="account-menu-sep" role="separator"></div>
        <button class="account-menu-item danger" type="button" role="menuitem" @click="onLogout">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M15 17l5-5-5-5M20 12H9M12 20H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h6" />
          </svg>退出登录
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

export interface SessionGroup {
  date: string
  sessions: Array<{
    thread_id: string
    preview: string
    time: string
    created_at: string
  }>
}

const props = defineProps<{
  collapsed: boolean
  width: number
  loading: boolean
  groups: SessionGroup[]
  activeThreadId: string
  username: string
}>()

const emit = defineEmits<{
  toggle: []
  'new-chat': []
  'select-session': [threadId: string]
  'rename-session': [threadId: string, newTitle: string]
  'delete-session': [threadId: string]
  logout: []
}>()

// ── 底部账号区 ──────────────────────────────────
const menuOpen = ref(false)
const accountRef = ref<HTMLElement | null>(null)

/** 头像首字母：取用户名首字符，英文转大写 */
const initial = computed(() => {
  const n = (props.username || '').trim()
  return n ? n[0]!.toUpperCase() : '?'
})

function toggleMenu() {
  menuOpen.value = !menuOpen.value
}

function closeMenu() {
  menuOpen.value = false
}

function onLogout() {
  closeMenu()
  emit('logout')
}

/** 点击账号区之外关闭菜单 */
function onDocumentClick(e: MouseEvent) {
  if (!menuOpen.value) return
  if (accountRef.value && !accountRef.value.contains(e.target as Node)) {
    closeMenu()
  }
}

/** Esc 关闭菜单 */
function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && menuOpen.value) closeMenu()
}

onMounted(() => {
  document.addEventListener('click', onDocumentClick)
  document.addEventListener('keydown', onKeydown)
})

onBeforeUnmount(() => {
  document.removeEventListener('click', onDocumentClick)
  document.removeEventListener('keydown', onKeydown)
})

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
  border-right: none;
  /* 宽度由 JS 内联控制（可拖拽）；折叠态固定 44px。
     不在此处动画 width —— 拖拽时需要跟手，动画会拖沓；
     折叠/展开的宽度变化由 CSS 覆盖，无需过渡（瞬时更利落）。 */
  overflow: hidden;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}

.sidebar.collapsed {
  width: 44px !important;
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
  flex: 1;
  min-height: 0;
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
  flex: 1;
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

/* ── 底部账号区 ───────────────────────────────── */
.account-bar {
  position: relative;
  flex-shrink: 0;
  border-top: 1px solid var(--border);
  padding: var(--sp-2);
}

.account-trigger {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  width: 100%;
  padding: var(--sp-2);
  border: 1px solid transparent;
  border-radius: var(--r-sm);
  background: transparent;
  color: var(--text-200);
  font-family: var(--font-body);
  font-size: var(--fs-sm);
  cursor: pointer;
  text-align: left;
  transition:
    background var(--dur-fast) var(--ease),
    border-color var(--dur-fast) var(--ease);
}

.account-trigger:hover {
  background: var(--ink-700);
}

.account-trigger:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: -2px;
}

.account-trigger:active {
  background: var(--ink-600);
}

.avatar-badge {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  flex-shrink: 0;
  border-radius: var(--r-sm);
  background: var(--accent);
  color: var(--ink-900);
  font-size: var(--fs-xs);
  font-weight: 700;
  line-height: 1;
}

.avatar-badge.lg {
  width: 32px;
  height: 32px;
  font-size: var(--fs-base);
}

.account-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 500;
  color: var(--text-100);
}

.chevron {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
  color: var(--text-400);
  transition: transform var(--dur-fast) var(--ease);
}

.chevron.open {
  transform: rotate(180deg);
}

/* 弹出菜单：从下往上展开 */
.account-menu {
  position: absolute;
  left: var(--sp-2);
  right: var(--sp-2);
  bottom: calc(100% - var(--sp-1));
  z-index: 30;
  padding: var(--sp-2);
  background: var(--ink-700);
  border-radius: var(--r-md);
  box-shadow: 0 8px 24px var(--shadow-panel);
}

.account-menu-head {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  padding: var(--sp-1) var(--sp-1) var(--sp-2);
}

.account-menu-id {
  min-width: 0;
}

.account-menu-name {
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--text-100);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.account-menu-sub {
  font-size: var(--fs-xs);
  color: var(--text-400);
}

.account-menu-sep {
  height: 1px;
  background: var(--border);
  margin: 0 calc(-1 * var(--sp-2)) var(--sp-2);
}

.account-menu-item {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  width: 100%;
  padding: var(--sp-2);
  border: none;
  border-radius: var(--r-sm);
  background: transparent;
  color: var(--text-200);
  font-family: var(--font-body);
  font-size: var(--fs-sm);
  cursor: pointer;
  text-align: left;
  transition:
    background var(--dur-fast) var(--ease),
    color var(--dur-fast) var(--ease);
}

.account-menu-item svg {
  width: 15px;
  height: 15px;
  flex-shrink: 0;
}

.account-menu-item:hover {
  background: var(--ink-600);
  color: var(--text-100);
}

.account-menu-item:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: -2px;
}

.account-menu-item.danger:hover {
  background: var(--danger-wash);
  color: var(--danger);
}

.account-menu-item:active {
  background: var(--ink-500);
}

/* 折叠态：只留头像 */
.sidebar.collapsed .account-bar {
  padding: var(--sp-2) 0;
}

.sidebar.collapsed .account-trigger {
  justify-content: center;
  padding: var(--sp-1) 0;
}

.sidebar.collapsed .account-name,
.sidebar.collapsed .chevron {
  display: none;
}

@media (prefers-reduced-motion: reduce) {
  .sidebar,
  .toggle-btn,
  .session-item,
  .new-chat-btn,
  .session-actions,
  .rename-btn,
  .delete-btn,
  .account-trigger,
  .account-menu-item,
  .chevron {
    transition: none;
  }
}
</style>
