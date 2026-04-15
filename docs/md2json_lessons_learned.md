# md2json 接入经验

本文总结当前项目在 `Markdown -> JSON` 阶段接入 OpenRouter Structured Outputs 的实际经验，重点记录 Claude 模型与 provider 兼容性、fixture 维护和后处理边界。

## 1. schema 设计经验

### 1.1 不要假设 provider 支持完整 JSON Schema

在 `anthropic/claude-sonnet-4.6` 的当前 OpenRouter 路由下，provider 返回过以下兼容性错误：

- 递归定义不支持
  - 错误示例：`Circular reference detected in schema definitions: question -> question`
- 某些数值约束关键字不支持
  - 错误示例：`For 'integer' type, property 'minimum' is not supported`

因此项目中的 `schemas/question_schema.json` 采用以下策略：

- 不使用递归 `$ref`
- 将题目树展开为固定 5 层
- 不在模型侧 schema 中使用 `minimum` 一类细粒度约束
- 将更严格的业务规则下沉到程序校验

### 1.2 模型侧 schema 只保留最必要结构

当前实践表明，模型侧 schema 适合保留：

- 顶层对象形状
- 必填字段
- 基本类型
- 有限枚举
- 固定层数的子题结构

不稳定或 provider 兼容性差的规则，应放到程序侧：

- 非负数约束
- `fill_slots_count` 与 `[[slot]]` 数量匹配
- 题型与字段一致性
- 题号连续性
- LaTeX 完整性与自动修复

## 2. 模型输出经验

### 2.1 Claude 当前模型可以返回完整结果

在兼容后的 `question_schema.json` 下，`anthropic/claude-sonnet-4.6` 已经能够成功返回完整结构化结果，不再出现请求阶段的 `400 Bad Request`。

### 2.2 当前主要问题已经不是 schema，而是文本标准化

当前 Claude 输出整体覆盖率和题目切分已经基本符合预期。主要剩余问题集中在文本细节：

- 保留 Markdown 强调，如 `**不是**`
- 某些选择题题干去掉了 `（ ）`
- `[[slot]]` 前后的连接符样式不完全一致
- 中西文和公式附近空格风格不统一

这类问题应在 `md2json.py` 的后处理层解决，而不是继续收紧 schema。

## 3. fixture 经验

### 3.1 fixture 不一定永远正确

实际对比发现：

- `tests/fixtures/md2json/output/概率论7套真题.json` 为 103 题
- 原 `tests/fixtures/md2json/expected/概率论7套真题.json` 为 102 题

根因不是模型多拆题，而是旧 fixture 少了一道源 Markdown 中真实存在的题：

- 第四套 `### 三、计算题`
- `**5.** 各零件的重量（单位：千克）...求 400 个零件的总重量超过 202 的概率`

因此不能只拿 `expected` 当唯一真值，还必须对照源 Markdown 做编号与覆盖率校验。

### 3.2 当前基线

用户已确认：Claude 当前输出整体符合预期，只有 Markdown 标记等细节仍需后处理。

因此当前 `tests/fixtures/md2json/expected/概率论7套真题.json` 已更新为 Claude 最新输出，作为新的 fixture 基线。

## 4. 后续实现建议

### 4.1 validate.py

优先补充：

- 题号连续性检查
- 源 Markdown 覆盖率检查
- `expected_fixture_outdated` / `fixture_count_mismatch` 报告

### 4.2 md2json.py

优先补充：

- 去掉 `**...**`
- 统一 `[[slot]]` 前后的 `=`、`\sim`
- 统一空格风格
- 保持题干语义不变，仅做确定性文本规范化

### 4.3 prompt_md2json.md

Prompt 应继续强调：

- 不漏掉任何显式编号题
- 不输出 Markdown 强调标记
- 只输出题目结构，不输出解释
