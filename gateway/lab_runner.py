"""A deliberately small Python experiment interpreter for beginner lessons.

It interprets a safe subset rather than running arbitrary learner/project code.
"""

from __future__ import annotations

import ast
import operator
from typing import Any


BINOPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}


def _value(node: ast.AST, environment: dict[str, Any]) -> Any:
    if isinstance(node, ast.Constant) and isinstance(node.value, (str, int, float, bool, type(None))):
        return node.value
    if isinstance(node, ast.Name):
        if node.id not in environment:
            raise ValueError(f"Unknown label: {node.id}")
        return environment[node.id]
    if isinstance(node, ast.List):
        return [_value(item, environment) for item in node.elts]
    if isinstance(node, ast.Tuple):
        return tuple(_value(item, environment) for item in node.elts)
    if isinstance(node, ast.BinOp) and type(node.op) in BINOPS:
        return BINOPS[type(node.op)](_value(node.left, environment), _value(node.right, environment))
    raise ValueError("This experiment supports only values, labels, lists, and basic arithmetic.")


def run_python_experiment(code: str) -> dict[str, Any]:
    if len(code) > 2_000:
        raise ValueError("Experiment is too large.")
    tree = ast.parse(code, mode="exec")
    environment: dict[str, Any] = {}
    output: list[str] = []
    trace: list[dict[str, Any]] = []
    for statement in tree.body:
        if isinstance(statement, ast.Assign) and len(statement.targets) == 1 and isinstance(statement.targets[0], ast.Name):
            value = _value(statement.value, environment)
            environment[statement.targets[0].id] = value
            trace.append({"action": "assign", "label": statement.targets[0].id, "value": repr(value)})
        elif isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call) and isinstance(statement.value.func, ast.Name) and statement.value.func.id == "print" and len(statement.value.args) == 1:
            value = _value(statement.value.args[0], environment)
            output.append(str(value))
            trace.append({"action": "print", "value": repr(value)})
        else:
            raise ValueError("This experiment only allows simple assignment and print statements.")
    return {"output": output, "trace": trace, "environment": {key: repr(value) for key, value in environment.items()}}
