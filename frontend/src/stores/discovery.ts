import { defineStore } from "pinia";
import { ref } from "vue";
import { request } from "../services/api";
import { validAdcode, regionWeatherAdcode, type WeatherLocation } from "../domain/weather";
export function regionCity(region: string[]): string {
  const [province = "", city = "", district = ""] = region;
  if (["市辖区", "县"].includes(city) && province.endsWith("市")) return province;
  if (["省直辖县级行政区划", "自治区直辖县级行政区划"].includes(city)) return district;
  return city;
}
const CITY_CACHE = "discovery_city_v1";
export const useDiscovery = defineStore("discovery", () => {
  const cached = uni.getStorageSync(CITY_CACHE);
  const city = ref(typeof cached?.city === "string" ? cached.city : "");
  const region = ref<string[]>(Array.isArray(cached?.region) ? cached.region : []);
  // Precise coordinates are session-only; the city preference survives reopening.
  const latitude = ref<number | null>(null), longitude = ref<number | null>(null);
  const cachedCode = validAdcode(cached?.weather?.adcode);
  const weatherLocation = ref<WeatherLocation | null>(cachedCode && cached?.weather?.city === city.value
    && cached?.weather?.province === (region.value[0] || "")
    ? { city: city.value, province: region.value[0] || "", adcode: cachedCode } : null);
  const locating = ref(false), attempted = ref(false);
  let selection = 0;
  let locationPromise: Promise<void> | null = null;
  function persist() {
    const bound = weatherLocation.value;
    // Persist only administrative metadata, never precise GPS coordinates.
    const weather = bound?.adcode ? { city: bound.city, province: bound.province, adcode: bound.adcode } : null;
    uni.setStorageSync(CITY_CACHE, { city: city.value, region: region.value, weather });
  }
  function selectRegion(value: string[], codes?: string[]) {
    selection++;
    region.value = value;
    city.value = regionCity(value);
    const province = value[0] || "";
    const adcode = regionWeatherAdcode(value, codes);
    if (adcode) weatherLocation.value = { city: city.value, province, adcode };
    else if (weatherLocation.value?.city !== city.value || weatherLocation.value?.province !== province) weatherLocation.value = null;
    persist();
  }
  async function selectPoint(point: { latitude: number; longitude: number }) {
    const version = ++selection;
    const result: any = await request(`/discovery/location-city?lat=${point.latitude}&lng=${point.longitude}`);
    if (!result.city) throw new Error("未能识别地点所在城市，请重新选点");
    if (version !== selection) throw new Error("城市已变更，请重新选点");
    latitude.value = point.latitude; longitude.value = point.longitude;
    region.value = [result.province || "", result.city, result.district || ""];
    city.value = result.city;
    weatherLocation.value = { city: result.city, province: result.province || "", adcode: validAdcode(result.adcode),
      latitude: point.latitude, longitude: point.longitude };
    persist();
    return city.value;
  }
  function locate(): Promise<void> {
    if (locationPromise) return locationPromise;
    attempted.value = true; locating.value = true;
    const version = ++selection;
    locationPromise = (async () => {
      try {
        const loc: any = await new Promise((resolve, reject) => uni.getLocation({ type: "gcj02", success: resolve, fail: reject }));
        if (version !== selection) return;
        await selectPoint(loc);
      } finally { locating.value = false; locationPromise = null; }
    })();
    return locationPromise;
  }
  async function ensureCity() {
    if (city.value) return;
    if (locationPromise) return locationPromise;
    if (!attempted.value) await locate();
  }
  async function coordinates() {
    if (latitude.value !== null && longitude.value !== null) return;
    const loc: any = await new Promise((resolve, reject) => uni.getLocation({ type: "gcj02", success: resolve, fail: reject }));
    latitude.value = loc.latitude; longitude.value = loc.longitude;
  }
  return { city, region, latitude, longitude, weatherLocation, locating, attempted, selectRegion, selectPoint, locate, ensureCity, coordinates };
});
