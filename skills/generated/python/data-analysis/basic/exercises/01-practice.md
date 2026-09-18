# 练习：清洗并计算平均值

## 预测题

给定如下 CSV（`scores.csv`）：

```csv
name,score
Alice,88
Bob,
Carol,72
David,not_sure
```

以下代码输出什么？你认为会出错吗？为什么？

```python
import csv

scores = []
with open("scores.csv") as f:
    reader = csv.reader(f)
    header = next(reader)
    for row in reader:
        scores.append(float(row[1]))

print(len(scores))
print(sum(scores) / len(scores))
```

请先写下你的预测，再运行验证。

## 可控练习

使用同一份 CSV，修改代码使其：
1. 跳过空值行（如 Bob 的行）。
2. 遇到无法转换的文本（如 "not_sure"）时，打印一行警告并继续。
3. 最后输出有效记录数和平均值。

提示骨架：

```python
valid = []
for row in reader:
    raw = row[1].strip()
    if raw == "":
        continue  # 跳过缺失
    try:
        valid.append(float(raw))
    except ValueError:
        print(f"跳过非法值: {raw}")
```

## 解释题

用你自己的话说明：为什么必须先处理缺失值才能计算平均值？如果直接转换会怎样？
