"""In-process background jobs for slow model generation; replace with durable queue in production."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import RLock
from typing import Any, Callable
from uuid import uuid4
import json
import os
from pathlib import Path
from threading import local


EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="trainer-ai")
JOBS: dict[str, dict[str, Any]] = {}
LOCK = RLock()
RUNNING = set()
from storage import DATA
STORE = DATA / 'job-history'
CONTEXT = local()

class JobCancelled(RuntimeError):
    pass

def checkpoint():
    job_id = getattr(CONTEXT, 'job_id', None)
    if job_id:
        with LOCK:
            if JOBS.get(job_id, {}).get('status') == 'cancelled':
                raise JobCancelled('任务已取消，已生成内容保留。')

def current_id():
    return getattr(CONTEXT, 'job_id', None)

def active():
    with LOCK:
        return bool(RUNNING) or any(j['status'] in ('queued', 'running') for j in JOBS.values())

def active_plan_job(skill_id):
    list_jobs()
    with LOCK:
        for job in JOBS.values():
            recipe = job.get('recipe') or {}
            payload = recipe.get('payload') or {}
            if (recipe.get('kind') == 'plan' and payload.get('skillId') == skill_id
                    and (job.get('status') in ('queued', 'running') or job['id'] in RUNNING)):
                return {**job, 'inFlight': job['id'] in RUNNING}
    return None

def list_jobs(archived=None):
    if STORE.exists():
        for path in STORE.glob('*.json'):
            try:
                get(path.stem)
            except (KeyError, ValueError):
                continue
    with LOCK:
        return sorted([{k: job.get(k) for k in ('id', 'status', 'createdAt', 'completed', 'total', 'message', 'error')} |
                       {'kind': (job.get('recipe') or {}).get('kind', 'legacy'), 'resumable': bool(job.get('recipe')),
                        'inFlight': job['id'] in RUNNING} for job in JOBS.values() if archived is None or bool(job.get('archived')) == archived], key=lambda j: j['createdAt'] or '', reverse=True)

def archive_jobs(job_id=None, restore=False):
    list_jobs()  # Load persisted history; do not remove recipe/result/checkpoints.
    count = 0
    with LOCK:
        candidates = [JOBS[job_id]] if job_id in JOBS else ([] if job_id else list(JOBS.values()))
        if job_id and not candidates: raise ValueError('任务不存在')
        for job in candidates:
            if job['id'] in RUNNING or job['status'] not in ('completed', 'failed', 'cancelled', 'paused'):
                if job_id: raise ValueError('进行中的任务不能清理')
                continue
            if bool(job.get('archived')) == (not restore): continue
            updated = {**job, 'archived': not restore}
            persist(updated)
            JOBS[job['id']] = updated
            count += 1
    return {'count': count}

def delete_jobs(job_id=None):
    """Permanently remove archived terminal task records, never their outputs."""
    list_jobs()
    count = preserved = 0
    with LOCK:
        candidates = [JOBS[job_id]] if job_id in JOBS else ([] if job_id else list(JOBS.values()))
        if job_id and not candidates:
            raise ValueError('任务不存在')
        eligible = []
        for job in candidates:
            if (job['id'] in RUNNING or job.get('status') not in ('completed', 'failed', 'paused', 'cancelled')
                    or not job.get('archived')):
                if job_id:
                    raise ValueError('只能彻底删除已清理且已结束的任务')
                continue
            if not isinstance(job['id'], str) or not job['id'] or any(char in job['id'] for char in '/\\'):
                raise ValueError('任务标识无效')
            eligible.append(job)
        # Preflight every course reference before deleting any task record.
        for job in eligible:
            try:
                from plan_library import preserve_course_reference
                if preserve_course_reference(DATA, job):
                    preserved += 1
            except (OSError, ValueError, TypeError):
                if (job.get('recipe') or {}).get('kind') == 'plan' and job.get('status') == 'completed':
                    raise ValueError('课程索引保存失败，未删除任务')
        for job in eligible:
            path = STORE / (job['id'] + '.json')
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            JOBS.pop(job['id'], None)
            count += 1
    return {'count': count, 'preservedCourses': preserved}

def cancel(job_id):
    get(job_id)
    with LOCK:
        job = JOBS[job_id]
        if job['status'] in ('queued', 'running', 'paused'):
            job.update(status='cancelled', message='已停止后续步骤；正在返回的请求结束后释放资源。')
            persist(job)
        return {'id': job_id, 'status': job['status']}

def retry(job_id, handler):
    previous = get(job_id)
    with LOCK:
        if job_id in RUNNING:
            raise ValueError('当前请求仍在结束中，请稍后继续。')
        if not previous.get('recipe'):
            raise ValueError('此旧任务未保存参数，请从原入口重新发起。')
        if previous['status'] in ('queued', 'running', 'completed'):
            raise ValueError('只能继续失败、暂停或取消的任务。')
        recipe = previous['recipe']
        return submit(lambda: handler(recipe), recipe, job_id)

def persist(job):
    STORE.mkdir(parents=True, exist_ok=True)
    path = STORE / (job['id'] + '.json')
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(job, ensure_ascii=False), encoding='utf-8')
    os.replace(temporary, path)

def progress(completed, total, message):
    checkpoint()
    job_id = getattr(CONTEXT, 'job_id', None)
    if job_id:
        with LOCK:
            JOBS[job_id].update({'completed': completed, 'total': total, 'message': message})
            persist(JOBS[job_id])


def publish_partial(result):
    """Publish validated modules without marking the background job completed."""
    job_id = getattr(CONTEXT, 'job_id', None)
    checkpoint()
    if job_id:
        with LOCK:
            JOBS[job_id]['partialResult'] = result
            persist(JOBS[job_id])


def submit(work: Callable[[], dict[str, Any]], recipe=None, job_id=None) -> dict[str, str]:
    job_id = job_id or str(uuid4())
    with LOCK:
        if recipe:
            existing = next((job for job in JOBS.values() if job.get('recipe') == recipe and job['status'] in ('queued', 'running')), None)
            if existing:
                return {'id': existing['id'], 'status': existing['status']}
        JOBS[job_id] = {"id": job_id, "status": "queued", "createdAt": datetime.now(timezone.utc).isoformat(), 'recipe': recipe}
        persist(JOBS[job_id])

    def runner() -> None:
        CONTEXT.job_id = job_id
        with LOCK:
            if JOBS[job_id]['status'] == 'cancelled':
                return
            RUNNING.add(job_id)
            JOBS[job_id]["status"] = "running"
            persist(JOBS[job_id])
        try:
            result = work()
            with LOCK:
                if JOBS[job_id]['status'] != 'cancelled':
                    JOBS[job_id].update({"status": "completed", "result": result})
                persist(JOBS[job_id])
        except Exception as error:  # Returned as safe user-facing text by the API layer.
            with LOCK:
                if JOBS[job_id]['status'] != 'cancelled':
                    JOBS[job_id].update({"status": "failed", "error": str(error)})
                persist(JOBS[job_id])
        finally:
            with LOCK:
                RUNNING.discard(job_id)
            CONTEXT.job_id = None

    EXECUTOR.submit(runner)
    return {"id": job_id, "status": "queued"}


def recover(handler):
    if not STORE.exists():
        return
    for path in STORE.glob('*.json'):
        try:
            job = json.loads(path.read_text())
            recipe = job.get('recipe')
            if job['status'] in ('queued', 'running'):
                if recipe and recipe.get('kind') == 'plan':
                    submit(lambda recipe=recipe: handler(recipe), recipe=recipe, job_id=job['id'])
                else:
                    job.update(status='paused', message='重启后已保留参数，可在任务中心继续。')
                    with LOCK:
                        JOBS[job['id']] = job
                        persist(job)
        except (OSError, ValueError, KeyError):
            continue


def get(job_id: str) -> dict[str, Any]:
    with LOCK:
        if job_id not in JOBS:
            from uuid import UUID
            try:
                normalized = str(UUID(job_id))
                JOBS[job_id] = json.loads((STORE / (normalized + '.json')).read_text())
                if JOBS[job_id]['status'] in ('queued', 'running'):
                    JOBS[job_id].update({'status': 'paused', 'error': '进程重启中断了任务，可从任务中心继续。'})
            except (ValueError, OSError):
                raise KeyError('Job not found.')
        return dict(JOBS[job_id])
