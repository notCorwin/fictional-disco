# 程序校验设计

## 目标

- 模型侧 schema 只负责约束基本结构：对象形状、字段存在、字段基本类型、5 层子题深度限制。
- 业务正确性与细粒度约束全部下沉到程序校验，避免被特定 provider 的 JSON Schema 子集限制住。
- 校验模块应同时服务于：
  - `md2json` 之后的题目结构校验
  - `answers` 合并后的最终校验

## 模型侧 schema 保留内容

- 顶层必须是 `{ "questions": [...] }`
- 每道题必须包含字段：
  - `type`
  - `stem`
  - `stem_images`
  - `fill_slots_count`
  - `options`
  - `sub_questions`
- `type` 仍限制为：
  - `choices`
  - `filling`
  - `judging`
  - `subjective`
- `options` 仍为 `array | null`
- `sub_questions` 仍为 `array | null`
- 最多允许 5 层子题

## 下沉到程序校验的规则

### 1. 数值与计数规则

- `fill_slots_count >= 0`
- `fill_slots_count == stem 中 [[slot]] 的数量`
- 非填空题的 `fill_slots_count` 必须为 `0`

### 2. 题型与字段一致性

- `choices` 题必须有 `options`
- `choices` 题的 `options` 数量至少为 2
- 非 `choices` 题的 `options` 必须为 `null`
- 有 `sub_questions` 的节点，其 `options` 应为 `null`
- `judging` 题不应出现多选样式选项

### 3. 文本规范化

- 去掉题号前缀，如 `1.`、`（1）`、`第一题`
- 填空下划线统一替换为 `[[slot]]`
- 清理明显 OCR/Doc2X 噪音：
  - 多余空格
  - 非预期断行
  - 数学符号附近的异常空白
- 统一图片路径为相对路径

### 4. 结构完整性

- 每个节点都必须是完整 question 对象
- `sub_questions` 内部节点递归校验
- 深度超过 5 层时直接报错
- 叶子节点不得再包含非空 `sub_questions`
- 检查题号连续性，避免漏题或重复拆题：
  - 例如同一大题下 `1,2,3,4,6` 应报告缺失 `5`
  - 例如同一大题下出现两个 `5` 应报告疑似重复拆题
- 对照源 Markdown 的显式编号做顶层题目数量核对，优先发现“模型少解析/多拆题”与“expected 样本过期”两类问题
- 若源 Markdown 中存在明确题号，而结构化结果缺失对应题目，报告 `question_missing_from_output`
- 若结构化结果多出一题，但该题在源 Markdown 中确有对应编号，报告 `expected_fixture_outdated` 或 `fixture_count_mismatch`

### 5. LaTeX 校验

- `$` / `$$` 是否成对闭合
- 公式内全角括号、全角标点规范化
- 常见 OCR 误差修正：
  - `∼` -> `\sim`
  - 异常反斜杠数量

### 6. 答案阶段附加校验

- 每个叶子题都必须有 `answer` 与 `solution`
- `choices.answer` 必须只包含合法选项标号
- `judging.answer` 只能是 `正确` 或 `错误`
- `filling.answer` 必须是数组，长度等于 `fill_slots_count`

## 校验模块输出格式

- 统一输出结构化报告，包含：
  - `path`
  - `severity`
  - `code`
  - `message`
  - `raw_value`
  - `fixed_value`
- `severity` 分为：
  - `error`
  - `warning`
- 可确定意图的问题直接自动修复，并记录 `fixed_value`
- 语义不明确的问题只报错，不自动修复

## 当前 fixture 对比结论

- `tests/fixtures/md2json/output/概率论7套真题.json` 共 103 题
- `tests/fixtures/md2json/expected/概率论7套真题.json` 共 102 题
- Claude 当前模型已经能够在现有 schema 下成功返回完整结构化结果，说明 schema 兼容问题已解决
- 差异原因不是 Claude 多拆题，而是 `expected` 少了一道源文中真实存在的题：
  - 第四套 `### 三、计算题` 下的 `**5.** 各零件的重量（单位：千克）...求 400 个零件的总重量超过 202 的概率`
- 这说明后续校验不能只依赖 `expected` 对比，还需要做“源 Markdown 编号连续性/题目覆盖率”检查
- 当前剩余的主要问题已经转为“文本标准化规则没有完全对齐 expected”，而不是 schema/provider 兼容性问题

## 待补充的文本后处理规则

- 去掉 Markdown 强调标记，如 `**...**`
- 去掉选择题题干末尾无语义价值的作答占位，如 `（ ）`、`( )`
- 规范 `[[slot]]` 前后的连接符样式：
  - `= [[slot]]`
  - `\sim [[slot]]`
  - 避免生成 `=$ [[slot]]`、`\sim$ [[slot]]` 一类不统一写法
- 统一中西文之间、数学符号前后的空格样式
- 尽量保留题干语义，不在标准化阶段改写题目内容本身
- 这些规则优先在 `md2json.py` 的后处理层实现，而不是继续修改 schema

## 实现建议

- 在 `validate.py` 中拆成两层：
  - `normalize_question_tree()`：只做确定性修复
  - `validate_question_tree()`：只产出问题列表
- `md2json.py` 在模型返回后先调用规范化，再调用校验
- `final.py` 在答案合并后复用同一套规则，并增加答案校验
