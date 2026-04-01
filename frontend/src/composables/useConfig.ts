import { ref } from 'vue'

export function useConfig(name: string) {
  const data = ref<any>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)
  const saved = ref(false)

  async function load() {
    loading.value = true
    error.value = null
    try {
      const res = await fetch(`/api/config/${name}`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      data.value = await res.json()
    } catch (e: any) {
      error.value = e.message
    } finally {
      loading.value = false
    }
  }

  async function save(content: any) {
    error.value = null
    saved.value = false
    try {
      const res = await fetch(`/api/config/${name}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      saved.value = true
      setTimeout(() => { saved.value = false }, 3000)
    } catch (e: any) {
      error.value = e.message
    }
  }

  return { data, loading, error, saved, load, save }
}
