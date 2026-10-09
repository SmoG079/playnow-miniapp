import { defineStore } from "pinia";
import { ref } from "vue";
import { request } from "../services/api";

export interface CityWeather {
  city: string;
  temperature: number;
  observed_at: string;
  condition: string;
}
const TTL = 15 * 60 * 1000;
const RETRY_DELAY = 60 * 1000;
export const useWeather = defineStore("weather", () => {
  const current = ref<CityWeather | null>(null);
  const loading = ref(false);
  const cache = new Map<string, { data: CityWeather | null; until: number }>();
  const pending = new Map<string, Promise<void>>();
  let selected = "";
  async function refresh(city: string, province = "") {
    const key = JSON.stringify([province, city]);
    selected = key;
    if (!city) { current.value = null; loading.value = false; return; }
    const cached = cache.get(key);
    current.value = cached && cached.until > Date.now() ? cached.data : null;
    if (cached && cached.until > Date.now()) { loading.value = false; return; }
    loading.value = true;
    if (pending.has(key)) return pending.get(key);
    const operation = (async () => {
      try {
        const data = await request<CityWeather>(`/discovery/weather?city=${encodeURIComponent(city)}&province=${encodeURIComponent(province)}`, { skipAuth: true });
        if (data.city !== city || typeof data.temperature !== "number" || !Number.isFinite(data.temperature)) throw new Error("天气数据异常");
        cache.set(key, { data, until: Date.now() + TTL });
        if (selected === key) current.value = data;
      } catch {
        cache.set(key, { data: null, until: Date.now() + RETRY_DELAY });
        if (selected === key) current.value = null;
      } finally {
        pending.delete(key);
        if (selected === key) loading.value = false;
        if (cache.size > 20) cache.delete(cache.keys().next().value!);
      }
    })();
    pending.set(key, operation);
    return operation;
  }
  return { current, loading, refresh };
});
