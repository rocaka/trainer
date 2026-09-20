import { invoke, isTauri } from '@tauri-apps/api/core';

export interface Language { name: string; score: number | null; evidenceCount: number; githubBytes: number; githubRepositoryCount: number }
export interface Activity { day: string; count: number }
export interface Achievement { title: string; unlocked: boolean; current?: number; target?: number; detail?: string; icon?: string }
export interface RecordItem { concept_id: string; evidence_type: string; note: string; created_at: string }
export interface Dashboard {
  profile: { id?: string; name: string; bio: string; avatar: string };
  xp?: number; level?: number; conceptCount?: number; evidenceCount: number; activeDays: number;
  currentStreak: number; longestStreak?: number; languages: Language[];
  dimensions?: { name: string; count: number }[]; activity?: Activity[];
  achievements?: Achievement[]; recent?: RecordItem[]; storagePath?: string;
  github?: { login: string; refreshedAt: string; repositoryCount: number; totalContributions: number; activity: Activity[] } | null;
}
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

export async function trainerAction<T = unknown>(action: string, payload: Record<string, unknown> = {}): Promise<T> {
  if (!isTauri()) throw new Error('此操作仅可在 Trainer 桌面客户端中执行。');
  return invoke<T>('trainer_action', { action, payload });
}
