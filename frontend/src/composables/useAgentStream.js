import { ref } from 'vue'
import { useAgentStore } from '../stores/agent.js'
import { useChatStore } from '../stores/chat.js'

export function useAgentStream() {
  const chatStore = useChatStore()
  const agentStore = useAgentStore()
  const streamBuffers = ref(new Map())

  function handleTyping({ agent_role, is_typing }) {
    agentStore.setTyping(agent_role, is_typing)
  }

  function handleStream({ agent_role, message_id, token, source_message_id }) {
    if (!streamBuffers.value.has(message_id)) {
      streamBuffers.value.set(message_id, '')
      chatStore.addMessage({
        id: message_id,
        sender_type: 'agent',
        agent_role,
        source_message_id,
        content: '',
        status: 'streaming',
        created_at: new Date().toISOString(),
      })
    }

    const current = (streamBuffers.value.get(message_id) || '') + (token || '')
    streamBuffers.value.set(message_id, current)
    chatStore.updateMessageContent(message_id, current)
  }

  function handleStreamEnd({ message_id, status, content, created_at, agent_role, error, source_message_id }) {
    streamBuffers.value.delete(message_id)
    const normalizedContent = (content || '').trim()

    if (!chatStore.messages.find((m) => m.id === message_id)) {
      chatStore.addMessage({
        id: message_id,
        sender_type: 'agent',
        agent_role,
        source_message_id,
        content:
          status === 'failed'
            ? `Agent call failed${error ? `: ${error}` : ''}`
            : normalizedContent,
        status: status || 'failed',
        created_at: created_at || new Date().toISOString(),
      })
      return
    }

    chatStore.finalizeMessage(message_id, {
      status,
      content:
        status === 'failed' && !normalizedContent
          ? `Agent call failed${error ? `: ${error}` : ''}`
          : content,
      created_at,
      source_message_id: source_message_id || undefined,
    })
  }

  return { handleTyping, handleStream, handleStreamEnd }
}
