import { invoke, isTauri } from '@tauri-apps/api/core';

export interface Language { name: string; score: number | null; evidenceCount: number; githubBytes: number; githubRepositoryCount: number }
export interface Dashboard { profile: { name: string; bio: string; avatar: string }; evidenceCount: number; activeDays: number; currentStreak: number; languages: Language[] }
export interface ServiceHealth { ok: boolean; configured: boolean; provider: string; model: string; secureSubmissionSupported?: boolean; submissionReady?: boolean }
export async function loadServiceHealth(): Promise<ServiceHealth> {
  if (!isTauri()) throw new Error('浏览器预览不能检查本地服务，请使用桌面客户端。');
  const value = await invoke<ServiceHealth>('service_health');
  if (typeof value?.ok !== 'boolean' || typeof value.configured !== 'boolean' || typeof value.model !== 'string') {
    throw new Error('服务状态格式不兼容，请更新 Gateway。');
  }
  return value;
}
export async function runtimeStatus(): Promise<string> {
  return isTauri() ? invoke<string>('preview_status') : '浏览器预览 · 不启动本地服务';
}
export async function restartPreview(): Promise<void> {
  if (!isTauri()) throw new Error('请在桌面开发客户端中启动后端。');
  await invoke('start_preview');
}
export async function loadDashboard(): Promise<Dashboard> {
  if (!isTauri()) throw new Error('当前是浏览器界面预览。请启动桌面客户端读取本机学习档案。');
  const data: Dashboard = await invoke('dashboard');
  if (!data?.profile || !Array.isArray(data.languages) || typeof data.evidenceCount !== 'number') throw new Error('档案格式不兼容，请更新本地 Gateway。');
  return data;
}
