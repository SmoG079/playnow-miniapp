import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { Activity } from '../data/fixtures'
export const usePrototype = defineStore('prototype', () => {
  const joinedIds = ref<number[]>([])
  const bookings = ref<{ id: number; club: string; time: string; price: number }[]>([])
  const published = ref<Activity[]>([])
  function join(activity: Activity) {
    if (joinedIds.value.includes(activity.id)) return '你已报名这场活动'
    if (activity.joined >= activity.capacity) return '本场活动已满员'
    joinedIds.value.push(activity.id)
    return '报名成功，球场见！'
  }
  return { joinedIds, bookings, published, join }
})
