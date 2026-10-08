import { API_BASE_URL } from "../config";
import { SESSION_CONTEXT_KEY } from "./session-context";

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
  uni.removeStorageSync(SESSION_CONTEXT_KEY);
  uni.removeStorageSync("access_token");
  uni.removeStorageSync("refresh_token");
  uni.removeStorageSync("registered_post_ids");
  uni.removeStorageSync("booking_return");
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
  if (uni.getStorageSync("refresh_token") !== refreshToken)
    throw new Error("登录会话已变化，请重新加载");
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

async function authenticated<T>(operation: () => Promise<T>, skipAuth = false): Promise<T> {
  try { return await operation(); }
  catch (error: any) {
    if (error.statusCode !== 401 || skipAuth) throw error;
    try {
      if (!refreshPromise)
        refreshPromise = refreshTokens().finally(() => { refreshPromise = null; });
      await refreshPromise;
      return await operation();
    } catch (refreshError: any) {
      if (refreshError.statusCode === 401 || refreshError.message === "登录已失效") {
        clearTokens();
        uni.reLaunch({ url: `/pages/common/login?redirect=${encodeURIComponent(currentRoute())}` });
      }
      throw refreshError;
    }
  }
}

export async function request<T = any>(
  url: string,
  options: { method?: Method; data?: any; skipAuth?: boolean } = {},
): Promise<T> {
  return authenticated(() => rawRequest<T>(url, options.method || "GET", options.data || {}, !!options.skipAuth), !!options.skipAuth);
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

export function uploadFile(filePath: string, fileType = "upload"): Promise<{ url: string }> {
  return authenticated(() => new Promise((resolve, reject) => {
    uni.uploadFile({
      url: API_BASE_URL + "/upload",
      filePath,
      name: "file",
      formData: { file_type: fileType },
      timeout: 60000,
      header: { Authorization: `Bearer ${uni.getStorageSync("access_token") || ""}` },
      success: (response) => {
        let body: any;
        try { body = JSON.parse(response.data); } catch { body = null; }
        if (response.statusCode >= 200 && response.statusCode < 300 && body?.url)
          return resolve(body);
        reject(Object.assign(new Error(body ? detailMessage(body) : "图片上传服务返回异常，请稍后重试"), { statusCode: response.statusCode }));
      },
      fail: (error) => {
        const detail = error.errMsg || "";
        const message = /domain|url not in|合法域名/i.test(detail)
          ? "上传域名未配置，请联系管理员"
          : /timeout/i.test(detail) ? "图片上传超时，请重试" : "图片上传连接失败，请重试";
        reject(Object.assign(new Error(message), { cause: error }));
      },
    });
  }));
}
