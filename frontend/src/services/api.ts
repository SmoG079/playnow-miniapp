import { API_BASE_URL } from "../config";

export interface PageResult<T> {
  items: T[];
  total?: number;
  page?: number;
  page_size?: number;
}
type Method = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
let refreshPromise: Promise<void> | null = null;

function detailMessage(data: any) {
  const detail = data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail))
    return detail.map((x) => x?.msg || "参数错误").join("；");
  return "请求失败";
}

export function clearTokens() {
  uni.removeStorageSync("access_token");
  uni.removeStorageSync("refresh_token");
}

async function refreshTokens() {
  const refreshToken = uni.getStorageSync("refresh_token");
  if (!refreshToken) throw new Error("登录已失效");
  const tokens = await rawRequest<any>(
    "/auth/refresh",
    "POST",
    { refresh_token: refreshToken },
    true,
  );
  uni.setStorageSync("access_token", tokens.access_token);
  uni.setStorageSync("refresh_token", tokens.refresh_token);
}

function rawRequest<T>(
  url: string,
  method: Method,
  data: any,
  skipAuth = false,
): Promise<T> {
  return new Promise((resolve, reject) => {
    const token = uni.getStorageSync("access_token");
    uni.request({
      url: API_BASE_URL + url,
      method: method as any,
      data,
      timeout: 30000,
      header: {
        "Content-Type": "application/json",
        ...(!skipAuth && token ? { Authorization: `Bearer ${token}` } : {}),
      },
      success: (response) => {
        if (response.statusCode >= 200 && response.statusCode < 300)
          resolve(response.data as T);
        else
          reject(
            Object.assign(new Error(detailMessage(response.data)), {
              statusCode: response.statusCode,
              response,
            }),
          );
      },
      fail: (error) =>
        reject(
          Object.assign(new Error("网络连接失败，请稍后重试"), {
            cause: error,
          }),
        ),
    });
  });
}

export async function request<T = any>(
  url: string,
  options: { method?: Method; data?: any; skipAuth?: boolean } = {},
): Promise<T> {
  const method = options.method || "GET";
  try {
    return await rawRequest<T>(
      url,
      method,
      options.data || {},
      !!options.skipAuth,
    );
  } catch (error: any) {
    if (error.statusCode === 401 && !options.skipAuth) {
      try {
        if (!refreshPromise)
          refreshPromise = refreshTokens().finally(() => {
            refreshPromise = null;
          });
        await refreshPromise;
        return await rawRequest<T>(url, method, options.data || {});
      } catch (refreshError: any) {
        if (
          refreshError.statusCode === 401 ||
          refreshError.message === "登录已失效"
        ) {
          clearTokens();
          uni.reLaunch({
            url: `/pages/common/login?redirect=${encodeURIComponent(currentRoute())}`,
          });
        }
        throw refreshError;
      }
    }
    throw error;
  }
}

export async function listAll<T = any>(url: string): Promise<T[]> {
  const result: T[] = [];
  for (let page = 1; ; page++) {
    const separator = url.includes("?") ? "&" : "?";
    const response = await request<PageResult<T>>(
      `${url}${separator}page=${page}&page_size=50`,
    );
    const batch = response.items || [];
    result.push(...batch);
    if (
      batch.length < 50 ||
      (typeof response.total === "number" && result.length >= response.total)
    )
      return result;
  }
}

export function currentRoute() {
  const pages = getCurrentPages();
  const page = pages[pages.length - 1] as any;
  return page ? `/${page.route}` : "/pages/home/index";
}

export function uploadFile(filePath: string): Promise<{ url: string }> {
  return new Promise((resolve, reject) => {
    uni.uploadFile({
      url: API_BASE_URL + "/upload",
      filePath,
      name: "file",
      header: { Authorization: `Bearer ${uni.getStorageSync("access_token")}` },
      success: (response) => {
        try {
          const body = JSON.parse(response.data);
          if (response.statusCode !== 200 || !body.url)
            throw new Error(body.detail || "上传失败");
          resolve(body);
        } catch (error) {
          reject(error);
        }
      },
      fail: reject,
    });
  });
}
