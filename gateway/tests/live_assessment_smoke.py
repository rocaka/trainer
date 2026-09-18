"""Opt-in live check using only synthetic teaching data, never user's courses."""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='trainer-live-smoke-') as folder:
        os.environ['TRAINER_DATA_DIR'] = folder
        import server
        root = Path(folder) / 'learning-plans'
        root.mkdir(exist_ok=True)
        key = 'f' * 64
        (root / (key + '.json')).write_text(json.dumps({'lessons': [{
            'id': 'synthetic-add', 'title': '理解 Go 加法函数', 'language': 'Go',
            'objective': '解释参数、返回值和一次调用',
            'code': 'func add(a int, b int) int { return a + b }',
            'exercise': '解释 add(2, 3) 的结果并给另一个例子。'}]}), encoding='utf-8')
        result = server.assess_lesson({'planId': key, 'lessonId': 'synthetic-add', 'evidenceType': 'reading',
            'answer': 'a 和 b 是两个整数参数，return 把相加结果返回。add(2, 3) 返回 5；add(4, 6) 返回 10。'})
        print(json.dumps({'valid': True, 'score': result['score'], 'language': result['language'], 'method': result['method']}, ensure_ascii=False))
