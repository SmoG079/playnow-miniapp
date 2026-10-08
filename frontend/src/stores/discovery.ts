import { defineStore } from "pinia";
import { ref } from "vue";
import { request } from "../services/api";
export function regionCity(region: string[]): string {
  const [province = "", city = "", district = ""] = region;
  if (["市辖区", "县"].includes(city) && province.endsWith("市")) return province;
  if (["省直辖县级行政区划", "自治区直辖县级行政区划"].includes(city)) return district;
  return city;
}
export const useDiscovery = defineStore("discovery", () => {
  const city = ref("");
  const region = ref<string[]>([]);
  const latitude = ref<number | null>(null), longitude = ref<number | null>(null);
  const locating = ref(false), attempted = ref(false);
  let selection = 0;
  function selectRegion(value: string[]) {
    selection++;
    region.value = value;
    city.value = regionCity(value);
  }
  async function locate() {
    if (locating.value) return;
    attempted.value = true; locating.value = true;
    const version = ++selection;
    try {
      const loc: any = await new Promise((resolve, reject) => uni.getLocation({ type: "gcj02", success: resolve, fail: reject }));
      const result: any = await request(`/discovery/location-city?lat=${loc.latitude}&lng=${loc.longitude}`);
      if (version !== selection) return;
      latitude.value = loc.latitude; longitude.value = loc.longitude;
      region.value = [result.province, result.city, result.district];
      city.value = result.city;
    } finally { locating.value = false; }
  }
  async function coordinates() {
    if (latitude.value !== null && longitude.value !== null) return;
    const loc: any = await new Promise((resolve, reject) => uni.getLocation({ type: "gcj02", success: resolve, fail: reject }));
    latitude.value = loc.latitude; longitude.value = loc.longitude;
  }
  return { city, region, latitude, longitude, locating, attempted, selectRegion, locate, coordinates };
});
