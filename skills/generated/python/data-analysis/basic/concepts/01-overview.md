# 概念：读取 CSV 并计算平均值

## 文件是什么

CSV 是纯文本表格，每行用逗号分隔字段。Python 需要先把文件打开，再逐行读入。

## 读取流程（三步）

```python
import csv

with open("scores.csv") as f:
    reader = csv.reader(f)
    header = next(reader)   # 第一行通常是表头
    for row in reader:      # 之后每一行是一条数据
        print(row)          # row 是一个字符串列表
```

## 字符串与数字的区别

CSV 里的一切都是文本。`"95"` 是字符串，"95" 加 "5" 会得 "955"。必须用 `float()` 转换后才能做算术。

```python
value = float(row[1])   # 把第二个字段变成浮点数
```

## 缺失值问题

某些行可能缺数据，如空串 `""` 或非数字文本。直接 `float("")` 会报 `ValueError`。

清洗策略——先判断再转换：

```python
if row[1].strip() != "":
    numbers.append(float(row[1]))
```

## 计算平均值

收集到有效数字列表后：

```python
mean = sum(numbers) / len(numbers)
```

或用标准库：`statistics.mean(numbers)`。

## 语言 vs 通用概念

- 通用：数据清洗、缺失值决策、均值语义。
- Python 具体：`open`/`with` 语法、`csv` 模块、`float()` 行为。
