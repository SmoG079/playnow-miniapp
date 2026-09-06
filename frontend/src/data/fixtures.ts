export interface Activity {
  id: number; title: string; club: string; day: number; time: string; level: number;
  distance: number; price: number; capacity: number; joined: number; kind: 'match' | 'tournament'; image: string
}
export const activities: Activity[] = [
  { id: 1, title: '下班不散场，来一局双打', club: '青禾网球俱乐部 · 示例', day: 0, time: '19:00–21:00', level: 3.0, distance: 2.4, price: 68, capacity: 4, joined: 3, kind: 'match', image: '/static/court.jpg' },
  { id: 2, title: '周末早场，把快乐打回来', club: '湖畔网球公园 · 示例', day: 1, time: '09:00–11:00', level: 2.5, distance: 4.1, price: 48, capacity: 4, joined: 2, kind: 'match', image: '/static/tennis.jpg' },
  { id: 3, title: '高手过招 · 单打训练局', club: '青禾网球俱乐部 · 示例', day: 1, time: '16:00–18:00', level: 4.0, distance: 2.4, price: 80, capacity: 2, joined: 2, kind: 'match', image: '/static/court.jpg' },
  { id: 4, title: 'PlayNow 周末积分赛', club: '湖畔网球公园 · 示例', day: 1, time: '13:00–17:00', level: 3.0, distance: 4.1, price: 128, capacity: 16, joined: 12, kind: 'tournament', image: '/static/tennis.jpg' }
]
export const clubs = [
  { id: 1, name: '青禾网球俱乐部', area: '滨江区 · 江南大道', distance: 2.4, price: 80, image: '/static/court.jpg', courts: 3, labels: ['室外硬地', '夜间灯光'] },
  { id: 2, name: '湖畔网球公园', area: '西湖区 · 湖滨路', distance: 4.1, price: 60, image: '/static/tennis.jpg', courts: 4, labels: ['公园球场', '免费停车'] }
]
export function dayLabel(offset: number) { return offset === 0 ? '今天' : offset === 1 ? '明天' : '后天' }
export function dateLabel(offset: number) { const d = new Date(); d.setDate(d.getDate() + offset); return `${d.getMonth() + 1}月${d.getDate()}日` }
export const routes = { home: '/pages/home/index', clubs: '/pages/booking/club-list', venue: '/pages/booking/venue-detail', activity: '/pages/common/post-detail', publish: '/pages/publish/post-create', profile: '/pages/profile/index', chat: '/pages/chat/index' }
export function go(page: keyof typeof routes, query = '') { uni.navigateTo({ url: routes[page] + query }) }
export function tab(page: keyof typeof routes) { uni.reLaunch({ url: routes[page] }) }
