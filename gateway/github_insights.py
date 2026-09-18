"""Aggregate authorized GitHub metadata without retaining source or commit messages."""
from collections import Counter
from datetime import datetime


def aggregate(events, languages=None):
    days, hours, repositories = Counter(), Counter(), set()
    for event in events:
        if not isinstance(event, dict) or not isinstance(event.get('committedAt'), str):
            continue
        try:
            timestamp = datetime.fromisoformat(event['committedAt'].replace('Z', '+00:00'))
        except ValueError:
            continue
        days[timestamp.date().isoformat()] += 1
        hours[str(timestamp.hour).zfill(2)] += 1
        if isinstance(event.get('repositoryId'), str): repositories.add(event['repositoryId'])
    safe_languages = []
    for name, count in (languages or {}).items():
        if isinstance(name, str) and isinstance(count, int) and count >= 0:
            safe_languages.append({'name': name[:60], 'bytes': count})
    return {'commitCount': sum(days.values()), 'repositoryCount': len(repositories),
            'activeDays': [{'day': day, 'count': days[day]} for day in sorted(days)],
            'hourHistogram': [{'hour': hour, 'count': hours.get(hour, 0)} for hour in [str(i).zfill(2) for i in range(24)]],
            'languages': sorted(safe_languages, key=lambda item: (-item['bytes'], item['name'])),
            'privacy': '仅聚合授权账户的提交元数据；不保存源码、diff 或提交消息。'}
