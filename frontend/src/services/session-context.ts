import { API_BASE_URL } from "../config";
export const SESSION_CONTEXT_KEY = "session_context";
// Both production ports serve the same accounts. Keep the storage namespace for existing drafts and logins.
const apiNamespace = API_BASE_URL === "https://www.tennisplaynow.site/api/v1"
  ? "https://www.tennisplaynow.site:8443/api/v1"
  : API_BASE_URL;
/** A token from an older AppID or an unscoped development build is not a current login. */
export function sessionContext(): string {
  let appId = "web";
  try { appId = uni.getAccountInfoSync?.().miniProgram.appId || appId; } catch {}
  return `account-v2:${appId}:${apiNamespace}`;
}
