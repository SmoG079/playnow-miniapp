export interface WeatherLocation {
  city: string;
  province: string;
  adcode?: string;
  latitude?: number;
  longitude?: number;
}

export function validAdcode(value: unknown): string | undefined {
  const code = String(value ?? "");
  return /^[1-9]\d{5}$/.test(code) ? code : undefined;
}

export function regionWeatherAdcode(region: string[], codes?: string[]): string | undefined {
  if (!Array.isArray(codes)) return undefined;
  if (["市辖区", "县"].includes(region[1]) && region[0]?.endsWith("市")) return validAdcode(codes[0]);
  if (["省直辖县级行政区划", "自治区直辖县级行政区划"].includes(region[1])) return validAdcode(codes[2]);
  return validAdcode(codes[1]) || validAdcode(codes[2]);
}

export function weatherPosition(location?: WeatherLocation | null): string {
  if (!location) return "";
  const { latitude, longitude } = location;
  if (typeof latitude === "number" && typeof longitude === "number" && Number.isFinite(latitude) && Number.isFinite(longitude)
    && latitude >= -90 && latitude <= 90 && longitude >= -180 && longitude <= 180)
    return `lat=${latitude}&lng=${longitude}`;
  const code = validAdcode(location.adcode);
  return code ? `adcode=${code}` : "";
}
