import { reactive } from 'vue'

export const toast = reactive({ text: '', visible: false })
let timer: number | undefined

export function showToast(text: string) {
  toast.text = text
  toast.visible = true
  window.clearTimeout(timer)
  timer = window.setTimeout(() => { toast.visible = false }, 2200)
}
