# any2pdf fixtures

用于测试阶段 0 的任意文件转 PDF 能力，覆盖以下输入类型：

- `input/Image/`: 图片样本，例如 `.jpg`、`.png`、`.webp`
- `input/Office/`: Office 文档样本，例如 `.docx`、`.pptx`、`.xlsx`
- `input/PDF/`: 原始 PDF 样本，用于验证直传 PDF 的复制逻辑
- `output/`: 运行 `run_any2pdf_fixture.py` 后生成的 PDF 输出目录

约定：

- 每个输入样本按文件名 stem 在 `output/<case_name>/` 下生成对应 PDF。
- 此目录以手工 fixture 回归为主，不依赖 pytest。
