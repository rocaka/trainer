import { invoke, isTauri } from '@tauri-apps/api/core';

export interface CourseSummary { id: string; title: string; lessonCount: number }
export interface Lesson {
  id: string; title: string; objective: string; language: string; code: string;
  explanation: string; syntax: string; rationale: string; exercise: string; reflection: string;
  contentType: 'project-brief' | 'concept' | 'implementation' | 'verification';
  practiceTask?: { prompt: string; requiredFiles: string[]; acceptance: string[] };
}
export interface Course { id: string; title: string; lessons: Lesson[] }
type RecordValue = Record<string, unknown>;
function record(value: unknown): value is RecordValue {
  return !!value && typeof value === 'object' && !Array.isArray(value);
}
function nonempty(value: unknown): value is string { return typeof value === 'string' && value.trim().length > 0; }
function planID(value: unknown): value is string { return typeof value === 'string' && /^[a-f0-9]{64}$/.test(value); }
function incompatible(): never { throw new Error('课程格式不兼容，请更新本地服务后重试。'); }
function requireDesktop() {
  if (!isTauri()) throw new Error('浏览器仅提供界面预览。请在桌面客户端打开本机已保存课程。');
}
export async function loadCourses(): Promise<CourseSummary[]> {
  requireDesktop();
  const value: unknown = await invoke('courses');
  if (!record(value) || !Array.isArray(value.courses) || value.courses.length > 1000) incompatible();
  const seen = new Set<string>();
  return value.courses.map((item: unknown) => {
    if (!record(item) || !planID(item.id) || !nonempty(item.title)
      || typeof item.lessonCount !== 'number' || !Number.isSafeInteger(item.lessonCount)
      || item.lessonCount < 1 || seen.has(item.id)) incompatible();
    seen.add(item.id);
    return { id: item.id, title: item.title, lessonCount: item.lessonCount };
  });
}
export async function loadCourse(planId: string): Promise<Course> {
  requireDesktop();
  if (!planID(planId)) throw new Error('课程编号无效，请重新选择课程。');
  const value: unknown = await invoke('course', { planId });
  if (!record(value) || value.id !== planId || !nonempty(value.title)
    || !Array.isArray(value.lessons) || !value.lessons.length) incompatible();
  const fields = ['id', 'title', 'objective', 'language', 'code', 'explanation', 'syntax', 'rationale', 'exercise', 'reflection'] as const;
  const seen = new Set<string>();
  for (const item of value.lessons) {
    if (!record(item) || fields.some(field => !nonempty(item[field]))
      || !['project-brief', 'concept', 'implementation', 'verification'].includes(String(item.contentType))
      || seen.has(String(item.id))) incompatible();
    seen.add(String(item.id));
    if (item.practiceTask !== undefined) {
      const task = item.practiceTask;
      if (!record(task) || !nonempty(task.prompt) || !Array.isArray(task.requiredFiles)
        || !task.requiredFiles.length || !task.requiredFiles.every(nonempty)
        || !Array.isArray(task.acceptance) || !task.acceptance.length || !task.acceptance.every(nonempty)) incompatible();
    }
  }
  return value as unknown as Course;
}
