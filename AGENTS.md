# 试卷转 JSON 转换工具

将试卷文件（PDF、Word、图片等）解析并结构化输出为 JSON 格式。

## 技术栈

| 职责 | 语言 |
|---|---|
| 全部模块（格式转换、LLM 调用、校验、流程编排） | Python |

## 项目结构

```
fictional-disco/
├── AGENTS.md
├── LICENSE
├── pyproject.toml
├── .env.example
├── .gitignore
│
├── src/exam_parser/          # 源码包
│   ├── __init__.py
│   ├── main.py               # CLI / 流水线入口
│   ├── config.py             # 读 .env、常量、资源路径
│   ├── step0_convert.py      # Step 0：文件 → PDF
│   ├── step1_pdf2md.py       # Step 1：PDF → Markdown（Doc2X）
│   ├── step2_md2json.py      # Step 2：Markdown → JSON（LLM）
│   ├── step3_validate.py     # Step 3/5：校验（通用 + 答案）
│   ├── step4_answers.py      # Step 4：生成答案（LLM）
│   └── step5_final.py        # Step 5：最终校验（调用 step3）
│
├── schemas/                  # JSON Schema
│   ├── question_schema.json
│   └── answer_schema.json
│
├── prompts/                  # LLM Prompt 模板
│   ├── prompt_step2.md
│   └── prompt_step4.md
│
├── docs/                     # 参考文档
│   ├── doc2x_api.md
│   └── openrouter_structured_output.md
│
├── tests/                    # 测试
│   ├── __init__.py
│   ├── conftest.py
│   └── fixtures/
│       ├── pdf2md/
│       │   ├── input/simple/
│       │   ├── input/hard/
│       │   └── output/
│       └── md2json/
│           ├── input/
│           ├── expected/
│           └── output/
│
└── output/                   # 运行时产物（已 gitignore）
```

---

## 关键设计文件

| 文件 | 用途 |
|---|---|
| `schemas/question_schema.json` | Step 2 使用的 Structured Outputs Schema（题目结构） |
| `schemas/answer_schema.json` | Step 4 使用的 Structured Outputs Schema（答案与解析） |
| `prompts/prompt_step2.md` | Step 2 的 System Prompt 与 User Prompt 模板 |
| `prompts/prompt_step4.md` | Step 4 的 System Prompt 与 User Prompt 模板 |

---

## 程序业务逻辑

### Step 0：将上传内容统一转换为 PDF

**源码：** `src/exam_parser/step0_convert.py`
**输入：** 用户上传的任意文件（`.docx`、`.pptx`、`.jpg`、`.png` 等）
**输出：** 标准 PDF 文件

**规则：**

1. Office 文档（Word、PowerPoint）使用 `LibreOffice` 转换为 PDF。
2. 图片（JPG、PNG、WEBP 等）使用 `img2pdf` 直接封装为 PDF。
3. 原始文件已经是 PDF 则跳过此步骤，直接进入 Step 1。

---

### Step 1：PDF 转换为 Markdown + 图片

**源码：** `src/exam_parser/step1_pdf2md.py`
**输入：** PDF 文件
**输出：** 压缩包，内含 Markdown 文件和 `images/` 文件夹

**规则：**

1. 调用 [Doc2X](https://doc2x.noedgeai.com/) API 将 PDF 转换为 Markdown，输出格式选择压缩包。
2. 压缩包内部结构为 Markdown 文件 + `images/` 文件夹。
3. Markdown 中的图片以相对路径引用（如 `![](images/xxx.png)`）。
4. 数学公式一律使用美元符号包裹：
   - 行内公式：`$...$`
   - 块级公式：`$$...$$`
5. 保留原始段落结构，不做任何内容增删。
6. 解压压缩包，将 Markdown 文件和 `images/` 文件夹提取到工作目录。

---

### Step 2：Markdown 转换为 JSON（使用 LLM）

**源码：** `src/exam_parser/step2_md2json.py`
**输入：** Doc2X 输出的原始 Markdown 文本
**输出：** 符合 `schemas/question_schema.json` 的结构化 JSON 文件

**规则：**

1. 调用 OpenRouter API，使用 Structured Outputs 功能（`response_format.type: "json_schema"`），将 Markdown 解析为 JSON。
2. Schema 使用 `schemas/question_schema.json`，设置 `strict: true`。
3. API 配置从项目根目录的 `.env` 文件读取：
   ```
   OPENROUTER_API_KEY=your_api_key_here
   OPENROUTER_MODEL_NAME=your_model_name_here
   ```
4. Prompt 参见 `prompts/prompt_step2.md`。
5. 此步骤只负责结构化题目内容，不生成答案与解析。
6. 不对 Doc2X 输出做预清洗——LLM 自行容忍文本噪音。

---

### Step 3：校验 JSON（不使用 LLM）

**源码：** `src/exam_parser/step3_validate.py`
**输入：** 结构化 JSON 文件
**输出：** 校验报告 + 修正后的 JSON 文件（如有自动修复）

此步骤为可复用模块，在 Step 2 之后和 Step 4 之后各调用一次，通过参数 `check_answers` 控制校验范围。

**通用校验规则（始终执行）：**

1. **必填字段完整性：** 递归遍历题目树，检查每个节点是否包含所有必填字段（`type`、`stem`、`stem_image`、`options`、`sub_questions`）。
2. **题型合法性：** 检查 `type` 值是否属于枚举 `["choices", "filling", "judging", "subjective"]`。
3. **题型与字段一致性：**
   - `choices` 类型的 `options` 不得为 `null`，且至少包含 2 个选项。
   - 非 `choices` 类型的 `options` 必须为 `null`。
   - 有 `sub_questions` 的节点，其 `options` 应为 `null`。
4. **子题结构递归校验：** 子题结构与父题一致，每个子题也是完整的 `question` 节点。
5. **LaTeX 格式校验：**
   - 检测未闭合的 `$` 或 `$$` 符号。
   - 检测公式内残留的全角符号。
6. **自动修复：** 仅修复可确定意图的格式问题（如多余空格、公式内全角括号替换为半角）。语义不明的问题只记录，不修改。

**答案校验规则（仅在 Step 4 之后执行，即 `check_answers=True`）：**

7. **答案字段完整性：** 确认每个叶子节点（无 `sub_questions` 的题目）均已填充 `answer` 与 `solution`。
8. **选择题答案合法性：** `choices` 类型的 `answer` 值必须由合法的选项标号组成（如 `"A"`、`"AC"`）。
9. **判断题答案合法性：** `judging` 类型的 `answer` 值必须为 `"正确"` 或 `"错误"`。

**输出报告：** 以结构化格式列出所有警告与错误，包含字段路径、问题类型及原始值。

---

### Step 4：生成答案与解析（使用 LLM）

**源码：** `src/exam_parser/step4_answers.py`
**输入：** 结构化 JSON 文件中的单道顶层题目（含完整子题树）
**输出：** 符合 `schemas/answer_schema.json` 的答案与解析 JSON

**规则：**

1. 调用 OpenRouter API，使用 Structured Outputs 功能，逐题推算正确答案并生成完整解析。
2. Schema 使用 `schemas/answer_schema.json`，设置 `strict: true`。
3. API 配置同 Step 2（读取根目录 `.env` 文件）。
4. Prompt 参见 `prompts/prompt_step4.md`。
5. **以顶层题目为单位调用：** 每道顶层题目单独发起一次 API 请求。父题的 `stem` 作为所有子题的上下文，整棵子题树在同一次请求中处理。
6. **答案 Schema 为镜像树结构：** `schemas/answer_schema.json` 的 `sub_answers` 数组与 `schemas/question_schema.json` 的 `sub_questions` 按位置一一对应。
7. **合并：** 代码按位置将 `answer_schema` 的输出合并回主 JSON 的对应题目节点，写入 `answer` 和 `solution` 字段。

---

### Step 5：最终校验（不使用 LLM）

**源码：** `src/exam_parser/step5_final.py`（内部调用 `step3_validate.validate_json(check_answers=True)`）
**输入：** 合并答案后的完整 JSON 文件
**输出：** 校验报告 + 最终 JSON 文件

**规则：**

1. 调用 Step 3 的校验模块，启用答案校验规则。
2. 对 `answer` 和 `solution` 字段执行 LaTeX 格式校验与自动修复（规则同 Step 3）。
3. 输出最终的结构化 JSON 文件（与 `images/` 文件夹一同作为交付产物）。

---

## 最终交付产物

```
output/
├── questions.json      # 包含题目结构、答案与解析的完整 JSON
└── images/             # 题目配图
    ├── q1_stem.png
    ├── q2_option_a.png
    └── ...
```
