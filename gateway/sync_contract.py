"""Versioned cloud-sync envelope rules shared by future HTTP adapters."""
import json
import re

KINDS = {'profile', 'evidence', 'course-completion', 'course-progress', 'preference'}


def validate_change(change):
    if not isinstance(change, dict) or set(change) != {'id', 'kind', 'version', 'updatedAt', 'payload'}:
        raise ValueError('同步记录字段无效')
    if not re.fullmatch(r'[a-f0-9]{32,64}', str(change['id'])) or change['kind'] not in KINDS:
        raise ValueError('同步记录身份无效')
    if not isinstance(change['version'], int) or change['version'] < 1:
        raise ValueError('同步版本无效')
    if not isinstance(change['updatedAt'], str) or not change['updatedAt']:
        raise ValueError('同步时间无效')
    if not isinstance(change['payload'], dict) or len(json.dumps(change['payload'], ensure_ascii=False).encode()) > 256 * 1024:
        raise ValueError('同步负载无效或过大')
    return change


def merge(local, remote):
    """Append-only learning records never overwrite; mutable rows use version then timestamp."""
    local, remote = validate_change(local), validate_change(remote)
    if local['id'] != remote['id'] or local['kind'] != remote['kind']:
        raise ValueError('不能合并不同记录')
    if local['kind'] in ('evidence', 'course-completion'):
        if local != remote:
            raise ValueError('不可变学习记录发生冲突，必须保留两条独立身份')
        return local
    return max((local, remote), key=lambda item: (item['version'], item['updatedAt']))
