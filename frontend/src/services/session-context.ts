import { API_BASE_URL } from "../config";
export const SESSION_CONTEXT_KEY = "session_context";
/** A token from an older AppID or an unscoped development build is not a current login. */
export function sessionContext(): string {
  let appId = "web";
  try { appId = uni.getAccountInfoSync?.().miniProgram.appId || appId; } catch {}
  return `account-v2:${appId}:${API_BASE_URL}`;
}
