import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useUiStore = defineStore('ui', () => {
  const isNavigationOpen = ref(false)

  const toggleNavigation = () => {
    isNavigationOpen.value = !isNavigationOpen.value
  }

  return { isNavigationOpen, toggleNavigation }
})
