export const API_BASE_URL = (import.meta.env.VITE_DASHBOARD_API_BASE_URL ?? '').trim();

const envApiToken = (import.meta.env.VITE_DASHBOARD_API_TOKEN ?? '').trim();
const legacyTokenPrefix = ['autobot', 'token'].join('_');
const isUnsafePlaceholderToken = new RegExp(`^${legacyTokenPrefix}_`, 'i').test(envApiToken);

export const API_TOKEN = isUnsafePlaceholderToken ? '' : envApiToken;
