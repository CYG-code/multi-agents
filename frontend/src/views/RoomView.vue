<template>
  <div class="flex h-screen overflow-hidden bg-gray-50">
    <!-- 左栏 35% -->
    <div class="w-[35%] flex flex-col gap-2 p-2 border-r border-gray-200">
      <DiscussionArea class="flex-1" />
      <WritingArea class="flex-1" />
    </div>

    <!-- 中栏 35% -->
    <div class="w-[35%] flex flex-col border-r border-gray-200">
      <ChatPanel class="flex-1" />
    </div>

    <!-- 右栏 30% -->
    <div class="w-[30%] flex flex-col gap-2 p-2">
      <TaskRequirements class="flex-1" />
      <TaskScript class="flex-1" />
    </div>
  </div>
</template>

<script setup>
import DiscussionArea from '../components/layout/DiscussionArea.vue'
import WritingArea from '../components/layout/WritingArea.vue'
import ChatPanel from '../components/chat/ChatPanel.vue'
import TaskRequirements from '../components/task/TaskRequirements.vue'
import TaskScript from '../components/task/TaskScript.vue'
</script>
