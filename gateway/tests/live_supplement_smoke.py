"""Opt-in: real one-lesson transport test with authored synthetic material only."""
import json
import os
import sys
import tempfile
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='trainer-supplement-smoke-') as folder:
        os.environ['TRAINER_DATA_DIR'] = folder
        import server
        from teaching_plan import PLAN_SCHEMA, validate_plan
        def probe(data, original, documents, generate, **kwargs):
            schema = deepcopy(PLAN_SCHEMA)
            schema['properties']['lessons'].update(minItems=1, maxItems=1)
            result = generate('仅生成一节简短中文 Go 加法函数教学课。代码 func add(a int, b int) int { return a + b }。解释参数与 return，并给 add(2,3) 预测练习。各说明字段使用短 Markdown。这是合成测试资料。', schema)
            validate_plan(result, min_lessons=1)
            assert len(result['lessons']) == 1
            return {'valid': True, 'lessonCount': 1, 'language': result['lessons'][0]['language']}
        with patch('plan_library.saved_plan', return_value={'planId': 'f' * 64}), patch('plan_library.maintain_plan', side_effect=probe), patch('version_store.resolve_teaching_id', return_value='synthetic'), patch.object(server, 'read_skill', return_value={'documents': {'SKILL.md': 'Synthetic Go addition'}}), patch.object(server, 'read_curriculum_context', return_value={'teaching_rules': '解释参数、返回值，并提供预测练习。', 'project_teaching': '仅教学，不执行代码。'}):
            print(json.dumps(server.generate_plan({'skillId': 'synthetic', 'mode': 'supplement'}), ensure_ascii=False))
