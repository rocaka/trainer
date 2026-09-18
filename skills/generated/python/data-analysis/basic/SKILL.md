---
id: python.data-analysis.basic
title: Python 数据分析入门：从 CSV 到平均值
version: 0.1.0
status: provisional
contexts:
  languages: [Python]
  runtimes: [local]
  frameworks: [标准库 csv]
prerequisites: [programming.functions, programming.conditions, programming.collections]
---

# Skill 说明

教学习者用 Python 读取 CSV 并计算均值，假设其理解函数与列表概念，但尚未接触文件 IO 与缺失值。

## 核心教学目标

1. 用 `csv.reader` 读取文件并按行迭代。
2. 区分表头与数据行。
3. 用 `float()` 将字符串转换为数字。
4. 识别缺失值（空串或非法文本）并决定跳过或替换。
5. 用列表收集有效值，然后用 `sum()`/`len()` 或 `statistics.mean()` 计算均值。

## 教学原则

- 每个概念先给一个可预测的小例子。
- 缺失值是数据问题而非语法问题，需单独讲解。
- 使用公开示例数据，不涉及敏感信息。
- 先让学习者预测输出，再运行验证。
