"""Consistent local export. No API credentials or external symlink targets."""
import json
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from storage import DATA
import shutil
import stat
from contextlib import closing

RESTORE_ENTRIES = {'trainer-learning.sqlite3', 'skills', 'pending-approvals', 'learning-plans', 'lesson-tasks', 'job-history', 'avatars'}

def inspect_backup(path):
    source = Path(path).expanduser()
    if not source.is_file() or source.is_symlink() or source.suffix.lower() != '.zip':
        raise ValueError('请选择有效的 Trainer ZIP 备份。')
    with zipfile.ZipFile(source) as archive:
        infos = archive.infolist()
        if len(infos) > 20000 or sum(i.file_size for i in infos) > 1024 * 1024 * 1024:
            raise ValueError('备份超过恢复上限（20000 项 / 1 GB）。')
        seen = set()
        for item in infos:
            name = Path(item.filename)
            if name.is_absolute() or '..' in name.parts or '\\' in item.filename or not name.parts:
                raise ValueError('备份含非法路径。')
            normalized = name.as_posix()
            if name.parts[0] not in RESTORE_ENTRIES | {'backup-manifest.json'} or normalized in seen:
                raise ValueError('备份含未知或重复文件。')
            if stat.S_ISLNK(item.external_attr >> 16):
                raise ValueError('备份不能包含符号链接。')
            seen.add(normalized)
        manifest = json.loads(archive.read('backup-manifest.json'))
        if manifest.get('format') != 1:
            raise ValueError('不支持此备份版本。')
    return {'path': str(source), 'fileCount': len(infos), 'bytes': sum(i.file_size for i in infos), 'createdAt': manifest.get('createdAt', '')}

def restore_backup(path):
    info = inspect_backup(path)
    with tempfile.TemporaryDirectory(prefix='trainer-restore-', dir=DATA) as temporary:
        staging = Path(temporary)
        with zipfile.ZipFile(info['path']) as archive:
            archive.extractall(staging)
        db = staging / 'trainer-learning.sqlite3'
        if db.exists():
            with closing(sqlite3.connect(f'file:{db}?mode=ro', uri=True)) as connection:
                if connection.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                    raise ValueError('备份数据库校验失败。')
        # Restoring data must not silently restart old paid requests.
        for job_path in (staging / 'job-history').glob('*.json'):
            job = json.loads(job_path.read_text())
            if job.get('status') in ('queued', 'running'):
                job.update(status='paused', message='从备份恢复；请在任务中心手动继续。')
                job_path.write_text(json.dumps(job, ensure_ascii=False), encoding='utf-8')
        recovery = DATA / 'restore-history' / (datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid4().hex[:8])
        recovery.mkdir(parents=True)
        moved, installed = [], []
        try:
            for name in sorted(RESTORE_ENTRIES | {'trainer-learning.sqlite3-wal', 'trainer-learning.sqlite3-shm'}):
                target = DATA / name
                if target.is_symlink():
                    raise ValueError('当前数据路径包含符号链接，无法恢复。')
                if target.exists():
                    target.rename(recovery / name); moved.append(name)
                if (staging / name).exists():
                    (staging / name).rename(target); installed.append(name)
        except Exception:
            for name in reversed(installed):
                (DATA / name).rename(staging / name)
            for name in reversed(moved):
                (recovery / name).rename(DATA / name)
            raise
    return {'restored': True, 'previousDataPath': str(recovery), 'fileCount': info['fileCount']}


def create_backup():
    destination = DATA / 'backups'
    destination.mkdir(parents=True, exist_ok=True)
    name = 'Trainer-' + datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid4().hex[:8] + '.zip'
    archive = destination / name
    temporary = archive.with_suffix('.tmp')
    with tempfile.TemporaryDirectory(prefix='trainer-backup-') as directory:
        snapshot = Path(directory) / 'trainer-learning.sqlite3'
        database = DATA / 'trainer-learning.sqlite3'
        if database.exists():
            with closing(sqlite3.connect(f'file:{database}?mode=ro', uri=True)) as source, closing(sqlite3.connect(snapshot)) as target:
                source.backup(target)
        with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as output:
            if snapshot.exists():
                output.write(snapshot, snapshot.name)
            for folder in ['skills', 'pending-approvals', 'learning-plans', 'lesson-tasks', 'job-history', 'avatars']:
                root = DATA / folder
                if not root.exists():
                    continue
                for item in root.rglob('*'):
                    if item.is_file() and not item.is_symlink() and not any((root / parent).is_symlink() for parent in item.relative_to(root).parents):
                        if item.suffix != '.tmp':
                            output.write(item, str(item.relative_to(DATA)))
            output.writestr('backup-manifest.json', json.dumps({'format': 1, 'createdAt': datetime.now(timezone.utc).isoformat(), 'containsPrivateProjectContent': True, 'excludes': ['API keys', 'macOS UserDefaults'], 'restore': 'Quit Trainer and stop its Gateway. Preserve the current data folder before restoring this archive into Application Support/Trainer. Configure API keys separately.'}))
    temporary.replace(archive)
    return {'path': str(archive), 'name': name, 'bytes': archive.stat().st_size}
