export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api';

/**
 * Public base path the app is served under — Vite's `base` (see
 * `vite.config.js`), e.g. `/mapper-new-ui/`. Trailing slashes are dropped so it
 * can be concatenated; a deployment at an origin root normalises to `''`.
 *
 * Every in-app URL must be built from this. Hard-coding a root-relative path
 * such as `/login` escapes the SPA and lands on whatever the origin root
 * serves — on `https://api.imis.com.pk:9001` that is a *different* application.
 */
export const APP_BASE_PATH = (import.meta.env.BASE_URL || '/').replace(/\/+$/, '');

/** Root-relative login route that respects the deployment base path. */
export const LOGIN_PATH = `${APP_BASE_PATH}/login`;

export default API_BASE_URL;