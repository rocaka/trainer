"""Deterministic course-language and exercise coherence audit.

This is intentionally static: it catches contract mismatches but never claims that
generated code compiled or ran successfully.
"""
import re

LANGUAGES = {
    'python': ({'.py'}, (r'\bdef\s+\w+\s*\(', r'\bimport\s+\w+')),
    'go': ({'.go'}, (r'\bpackage\s+\w+', r'\bfunc\s+\w+\s*\(')),
    'javascript': ({'.js', '.jsx', '.mjs', '.cjs'}, (r'\b(const|let|var)\s+\w+', r'=>')),
    'typescript': ({'.ts', '.tsx'}, (r'\b(interface|type)\s+\w+', r':\s*(string|number|boolean)\b')),
    'swift': ({'.swift'}, (r'\b(func|let|var)\s+\w+',)),
    'rust': ({'.rs'}, (r'\bfn\s+\w+\s*\(', r'\blet\s+mut\b')),
    'java': ({'.java'}, (r'\b(class|interface)\s+\w+', r'\b(public|private|protected)\s+')),
    'kotlin': ({'.kt', '.kts'}, (r'\b(fun|val|var)\s+\w+',)),
    'ruby': ({'.rb'}, (r'\bdef\s+\w+', r'\brequire\s+')),
    'php': ({'.php'}, (r'<\?php', r'\bfunction\s+\w+')),
    'solidity': ({'.sol'}, (r'\b(contract|library|interface)\s+\w+', r'\bfunction\s+\w+')),
    'c': ({'.c', '.h'}, (r'#include\s*[<"]', r'\b(int|void)\s+\w+\s*\(')),
    'c++': ({'.cc', '.cpp', '.cxx', '.hpp', '.h'}, (r'#include\s*[<"]', r'\bstd::')),
    'c#': ({'.cs'}, (r'\b(namespace|class|record)\s+\w+', r'\busing\s+System')),
}
CONFIG_EXTENSIONS = {'.json', '.yaml', '.yml', '.toml', '.xml', '.md', '.txt', '.sql', '.sh'}


def _key(value):
    text = str(value).strip().lower().replace('golang', 'go').replace('python3', 'python')
    if text in ('js', 'node.js'): return 'javascript'
    if text == 'ts': return 'typescript'
    return text


def audit_course_quality(lessons, submission_policy=None):
    findings = []
    policy = submission_policy or {}
    for lesson in lessons:
        lesson_id = str(lesson.get('id', ''))
        language = _key(lesson.get('language', ''))
        code = str(lesson.get('code', '')).strip()
        spec = LANGUAGES.get(language)
        if spec is None:
            findings.append({'lessonId': lesson_id, 'kind': 'language', 'status': 'uncertain',
                             'detail': f'语言“{lesson.get("language", "")}”没有内置静态规则，需人工或编译器复核。'})
        else:
            signatures = spec[1]
            if len(code) < 8 or not any(re.search(pattern, code, re.I) for pattern in signatures):
                findings.append({'lessonId': lesson_id, 'kind': 'language', 'status': 'needs-work',
                                 'detail': f'代码示例缺少可识别的 {lesson.get("language")} 语法特征。'})
            else:
                findings.append({'lessonId': lesson_id, 'kind': 'language', 'status': 'passed',
                                 'detail': '语言标签与代码示例的静态特征一致。'})
        exercise = str(lesson.get('exercise', ''))
        actionable = re.search(r'读|运行|执行|修改|实现|编写|创建|调试|测试|迁移|解释|预测|比较', exercise)
        observable = re.search(r'输出|返回|结果|错误|函数|文件|命令|测试|断言|代码|字段|调用', exercise)
        findings.append({'lessonId': lesson_id, 'kind': 'exercise',
                         'status': 'passed' if actionable and observable else 'needs-work',
                         'detail': ('练习包含动作与可观察结果。' if actionable and observable
                                    else '练习需同时说明学习者动作和可观察的结果/产物。')})
        task = lesson.get('practiceTask')
        if policy.get('primaryRole') == 'course-task' and policy.get('mode') == 'project-practice':
            files = task.get('requiredFiles', []) if isinstance(task, dict) else []
            suffixes = {('.' + path.rsplit('.', 1)[-1].lower()) for path in files if '.' in path.rsplit('/', 1)[-1]}
            matches = bool(spec and suffixes.intersection(spec[0]))
            compatible = bool(suffixes) and all(ext in (spec[0] if spec else set()) or ext in CONFIG_EXTENSIONS for ext in suffixes)
            findings.append({'lessonId': lesson_id, 'kind': 'submission',
                             'status': 'passed' if task and matches and compatible else 'needs-work',
                             'detail': ('提交文件类型与本课语言一致。' if task and matches and compatible
                                        else '实践任务必须包含至少一个与本课语言一致的源文件，且不得混入不相容扩展名。')})
    failed = sum(item['status'] == 'needs-work' for item in findings)
    uncertain = sum(item['status'] == 'uncertain' for item in findings)
    return {'version': 1, 'status': 'passed' if failed == 0 and uncertain == 0 else 'needs-review',
            'passed': sum(item['status'] == 'passed' for item in findings), 'total': len(findings),
            'limitations': ['静态检查不执行、编译或测试代码；通过只代表标签、示例、练习和提交合同相互一致。'],
            'findings': findings}
