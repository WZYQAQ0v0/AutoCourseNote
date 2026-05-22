# AutoCourseNote

一个面向本地课程资料的多智能体课程笔记生成系统。用户把课件、教材、作业、往年题、图片等资料放入 `materials/`，系统会自动完成资料分类、文本解析、初稿生成、审查补充、教材编写、章节精修，并最终输出书籍风格的 Markdown 与 PDF。

本项目不爬取教学网，不处理登录或验证码。资料获取由用户自行完成，系统只处理本地文件。

## 你需要做什么

按下面顺序操作即可：

1. 进入项目目录。

```powershell
cd course_note_agents
```

2. 安装项目命令。

```powershell
python -m pip install -e .
```

3. 把课程资料放入一个文件夹。

推荐每门课单独放一个目录，例如：

```text
materials/
  my_course/
    第1讲.pptx
    第2讲.pdf
    教材.pdf
    作业1.docx
    往年题与答案.pdf
```

4. 打开 [course_config.toml](course_config.toml)，修改课程信息。

至少修改这几项：

```toml
[course]
course_id = "my_course"
materials_dir = "materials/my_course"
run_prefix = "my_course"
language = "zh-CN"
```

含义：

- `course_id`：课程唯一标识，建议使用英文、数字和下划线。
- `materials_dir`：课程资料所在文件夹。
- `run_prefix`：输出目录名，例如 `my_course` 会把所有产物放到 `runs/my_course/` 下。
- `language`：中文课程保持 `zh-CN`。

5. 在 [course_config.toml](course_config.toml) 中确认模型配置。

示例：

```toml
[llm]
provider = "deepseek"
base_url = "https://api.deepseek.com/v1"
model = "deepseek-chat"
api_key_env = "COURSE_NOTE_LLM_API_KEY"
```

`api_key_env` 填的是环境变量名，不是真实 API key。不要把真实 key 写进配置文件。最后一行不要修改

6. 购买API额度并在 PowerShell 中设置 API key。

```powershell
$env:COURSE_NOTE_LLM_API_KEY = "你的真实 API key"
```

这只对当前终端窗口有效。关闭终端后，下次运行需要重新设置。

7. 如果没有安装 LaTeX，先关闭 PDF 编译。

打开 [course_config.toml](course_config.toml)，设置：

```toml
[layout]
compile_pdf = false
```

这样仍会生成 Markdown 和 TeX。若已经安装 TeX Live 或 MiKTeX，可以保持 `compile_pdf = true`,将直接生成整理好的PDF文件。

8. 预览运行流程，确认配置没有写错。

```powershell
course-note-run --config .\course_config.toml --dry-run
```

看到系统依次打印 `INGEST`、`PARSE`、`DRAFT`、`REVIEW`、`TEXTBOOK`、`POLISH`、`LAYOUT`，说明配置能正常展开。

9. 正式运行。

```powershell
course-note-run --config .\course_config.toml
```

10. 查看产物。

```text
runs/<你的课程前缀>/polished/polished_textbook.md
runs/<你的课程前缀>/book_pdf/book.pdf
```

如果关闭了 PDF 编译，优先查看 `polished_textbook.md`。

## 主要能力

- 自动识别资料类型：课件、教材、作业、往年题、答案、参考文献、笔记、图片等。
- 支持多格式输入：PDF、PPTX、DOCX、图片、TXT、Markdown、HTML、CSV。
- 使用 OpenAI-compatible LLM 接口，可接入 DeepSeek、OpenAI 或其他兼容服务。
- 面向中文课程优化，支持中英文混合术语、公式、题目和讲义文本。
- 学科自适应：理工课程强调推导和完整解题，文科课程强调知识点完整、背诵提纲和论述框架。
- 保留结构化溯源信息，避免无依据编造。
- 可生成结构化 Markdown、术语表、符号表、引用表、自检报告和书籍风格 PDF。

## 安装

进入项目目录：

```powershell
cd course_note_agents
```

安装为本地可执行命令：

```powershell
python -m pip install -e .
```

如果只想从源码直接运行：

```powershell
$env:PYTHONPATH = "src"
```

PDF 排版需要本机安装 XeLaTeX，例如 TeX Live 或 MiKTeX。没有 LaTeX 环境时仍可生成 Markdown，或在配置文件中设置：

```toml
[layout]
compile_pdf = false
```

## 准备课程资料

建议每门课单独建一个资料目录：

```text
materials/
  my_course/
    第1讲.pptx
    第2讲.pdf
    教材.pdf
    作业1.docx
    往年题与答案.pdf
```

图片资料也可以放进去。当前版本会识别图片并标记为需要 OCR；完整 OCR/视觉理解可作为后续增强接入。

## 配置模型

除资料扫描和基础解析外，初稿、审查、教材编写和精修需要 LLM。系统使用 OpenAI-compatible Chat Completions 接口。

在 [course_config.toml](course_config.toml) 中配置模型服务：

```toml
[llm]
provider = "deepseek"
base_url = "https://api.deepseek.com/v1"
model = "deepseek-chat"
api_key_env = "COURSE_NOTE_LLM_API_KEY"
```

API key 不建议写入配置文件。请在 PowerShell 中设置环境变量：

```powershell
$env:COURSE_NOTE_LLM_API_KEY = "你的 API key"
```

这只对当前终端窗口有效。以后重新打开终端，需要再次设置；也可以在系统环境变量中长期保存。

## 修改配置文件

大多数用户只需要修改 [course_config.toml](course_config.toml) 顶部几项：

```toml
[course]
course_id = "my_course"
materials_dir = "materials/my_course"
run_prefix = "my_course"
language = "zh-CN"
```

含义：

- `course_id`：课程唯一标识，建议使用英文、数字和下划线。
- `materials_dir`：课程资料所在文件夹。
- `run_prefix`：输出目录名，例如 `my_course` 会生成 `runs/my_course/ingest`、`runs/my_course/polished` 等目录。
- `language`：中文课程保持 `zh-CN`。

正式运行前，可以先预览将要执行的步骤：

```powershell
course-note-run --config .\course_config.toml --dry-run
```

## 一键运行

确认资料和配置无误后：

```powershell
course-note-run --config .\course_config.toml
```

系统会按顺序执行：

1. `ingest`：资料扫描与分类
2. `parse`：内容解析与文本清洗
3. `draft`：单份资料初稿生成
4. `review`：审查补充
5. `textbook`：全书教材编写
6. `polish`：章节精修
7. `layout`：生成 LaTeX/PDF

## 输出目录

假设 `run_prefix = "my_course"`，输出如下：

```text
runs/my_course/ingest/      # manifest.json
runs/my_course/parsed/      # parsed_index.json 和解析文本
runs/my_course/draft/       # 初稿
runs/my_course/review/      # 审查补充稿
runs/my_course/textbook/    # 教材初稿、术语表、引用表、自检报告
runs/my_course/polished/    # 精修后的 Markdown
runs/my_course/book_pdf/    # book.tex、book.pdf、compile.log
```

最常用产物：

```text
runs/my_course/polished/polished_textbook.md
runs/my_course/book_pdf/book.pdf
```

如果需要追踪问题或来源：

```text
runs/my_course/textbook/citations.json
runs/my_course/textbook/self_checks/*.json
runs/my_course/polished/polishing_reports/*.json
```

## 常用配置

只解析课件：

```toml
[parse]
include_roles = ["lecture_slides"]
exclude_roles = []
```

跳过往年题和答案：

```toml
[parse]
exclude_roles = ["past_exam", "solution"]
```

先小样本测试：

```toml
[parse]
limit_documents = 2
limit_pages = 5

[draft]
limit_documents = 2

[review]
limit_documents = 2

[textbook]
limit_chapters = 2

[polish]
limit_chapters = 2
```

从某个阶段开始重跑：

```toml
[workflow]
start_at = "polish"
stop_after = "layout"
skip_stages = []
```

关闭 PDF 编译，只生成 Markdown 和 TeX：

```toml
[layout]
compile_pdf = false
```

## 资料角色

系统会把文件分类为以下角色之一：

- `syllabus`：课程大纲
- `textbook`：教材或讲义
- `lecture_slides`：课件
- `assignment`：作业
- `past_exam`：往年题、真题、试卷
- `solution`：答案或解析
- `reference_paper`：参考论文
- `notes`：笔记
- `miscellaneous`：其他资料

往年题和答案经常在同一个文件里。系统会尽量识别为 `past_exam`，并把 `solution` 记录到辅助角色中，后续 Agent 会在同一资料内区分题目、答案和解析。

## 项目结构

```text
course_note_agents/
  course_config.toml          # 一键运行配置文件
  materials/                  # 放置课程资料
  schemas/                    # 中间产物 JSON 格式说明
  runs/                       # 运行产物
  src/course_note_agents/     # 源码
```

`schemas/` 目录中的 `.schema.json` 文件对代码正常运行没有作用，只用于说明和检查各阶段中间产物的 JSON 格式。

## 质量检查

检查最终 Markdown 是否虚构考试章节：

```powershell
Select-String -Path .\runs\my_course\polished\polished_textbook.md `
  -Pattern '历年题|往年题|真题|试卷|模拟卷'
```

如果输入资料本身没有往年题，上述检查不应出现无来源的考试章节。

检查 PDF：

```powershell
@'
from pathlib import Path
import fitz

pdf = Path("runs/my_course/book_pdf/book.pdf")
doc = fitz.open(pdf)
print(pdf.exists(), pdf.stat().st_size)
print("pages:", doc.page_count)
print(doc[0].get_text()[:200])
'@ | python -
```

## 高级命令

一键命令会自动调用以下底层命令。开发者也可以单独运行某个阶段：

```powershell
course-note-ingest --help
course-note-parse --help
course-note-draft --help
course-note-review --help
course-note-textbook --help
course-note-polish --help
course-note-layout --help
course-note-run --help
```
