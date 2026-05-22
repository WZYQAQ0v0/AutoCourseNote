"""Small Markdown-to-LaTeX renderer tuned for generated course textbooks."""

from __future__ import annotations

import re
from dataclasses import dataclass


SPECIALS = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}


@dataclass(slots=True)
class RenderStats:
    chapters: int = 0
    sections: int = 0
    tables: int = 0
    code_blocks: int = 0


class MarkdownLatexRenderer:
    def __init__(self, cjk_main_font: str = "NotoSerifSC-VF.ttf", cjk_sans_font: str = "NotoSansSC-VF.ttf") -> None:
        self.cjk_main_font = cjk_main_font
        self.cjk_sans_font = cjk_sans_font
        self.stats = RenderStats()

    def render_document(self, markdown: str, title: str | None = None) -> str:
        title = title or self._title_from_markdown(markdown) or "课程复习教材"
        body_markdown = self._drop_first_title(markdown)
        body_markdown = self._drop_duplicate_chapter_stubs(body_markdown)
        body = self.render_body(body_markdown)
        return self._preamble(title) + "\n" + body + "\n\\backmatter\n\\end{document}\n"

    def render_body(self, markdown: str) -> str:
        self.stats = RenderStats()
        lines = markdown.splitlines()
        output: list[str] = []
        list_type: str | None = None
        in_code = False
        code_lines: list[str] = []
        in_raw_math = False
        raw_end = ""
        index = 0
        previous_chapter_title = ""

        def close_list() -> None:
            nonlocal list_type
            if list_type == "itemize":
                output.append("\\end{itemize}")
            elif list_type == "enumerate":
                output.append("\\end{enumerate}")
            list_type = None

        while index < len(lines):
            line = lines[index].rstrip()
            stripped = line.strip()

            if in_code:
                if stripped.startswith("```"):
                    output.append(self._render_code_block(code_lines))
                    self.stats.code_blocks += 1
                    code_lines = []
                    in_code = False
                else:
                    code_lines.append(line)
                index += 1
                continue

            if in_raw_math:
                output.append(line)
                if stripped.startswith(raw_end):
                    in_raw_math = False
                    raw_end = ""
                index += 1
                continue

            if stripped.startswith("```"):
                close_list()
                in_code = True
                code_lines = []
                index += 1
                continue

            raw_end = self._raw_block_end(stripped)
            if raw_end:
                close_list()
                in_raw_math = True
                output.append(line)
                if stripped.startswith(raw_end) or stripped.endswith(raw_end):
                    in_raw_math = False
                    raw_end = ""
                index += 1
                continue

            if self._is_table_start(lines, index):
                close_list()
                latex, consumed = self._render_table(lines[index:])
                output.append(latex)
                self.stats.tables += 1
                index += consumed
                continue

            heading = re.match(r"^(#{1,6})\s+(.+)$", stripped)
            if heading:
                close_list()
                level = len(heading.group(1))
                heading_title = heading.group(2).strip()
                if level == 1:
                    cleaned = self._clean_chapter_title(heading_title)
                    if previous_chapter_title and self._same_title(previous_chapter_title, cleaned):
                        index += 1
                        continue
                    previous_chapter_title = cleaned
                    self.stats.chapters += 1
                elif level == 2:
                    self.stats.sections += 1
                output.append(self._render_heading(level, heading_title))
                index += 1
                continue

            if not stripped:
                close_list()
                output.append("")
                index += 1
                continue

            item_match = re.match(r"^\s*[-*]\s+(.+)$", line)
            enum_match = re.match(r"^\s*\d+[.)]\s+(.+)$", line)
            if item_match:
                if list_type != "itemize":
                    close_list()
                    output.append("\\begin{itemize}")
                    list_type = "itemize"
                output.append("\\item " + self._format_inline(item_match.group(1)))
                index += 1
                continue
            if enum_match:
                if list_type != "enumerate":
                    close_list()
                    output.append("\\begin{enumerate}")
                    list_type = "enumerate"
                output.append("\\item " + self._format_inline(enum_match.group(1)))
                index += 1
                continue

            if stripped.startswith(">"):
                close_list()
                quote = stripped.lstrip(">").strip()
                output.append("\\begin{tcolorbox}[colback=noteBg,colframe=noteFrame,title=提示,breakable]")
                output.append(self._format_inline(quote))
                output.append("\\end{tcolorbox}")
                index += 1
                continue

            close_list()
            if self._looks_raw_latex(stripped):
                output.append(line)
            else:
                output.append(self._format_inline(line) + "\n")
            index += 1

        close_list()
        if in_code and code_lines:
            output.append(self._render_code_block(code_lines))
            self.stats.code_blocks += 1
        return "\n".join(output)

    def _preamble(self, title: str) -> str:
        return rf"""\documentclass[UTF8,openany,zihao=-4]{{ctexbook}}
\usepackage[a4paper,top=2.6cm,bottom=2.6cm,left=2.5cm,right=2.5cm]{{geometry}}
\usepackage{{fontspec}}
\usepackage{{xeCJK}}
\setCJKmainfont{{{self.cjk_main_font}}}[Path=C:/Windows/Fonts/]
\setCJKsansfont{{{self.cjk_sans_font}}}[Path=C:/Windows/Fonts/]
\setmainfont{{Times New Roman}}
\setsansfont{{Arial}}
\usepackage{{amsmath,amssymb,amsthm}}
\usepackage{{booktabs,longtable,tabularx,array}}
\usepackage[most]{{tcolorbox}}
\usepackage{{enumitem}}
\usepackage{{fancyhdr}}
\usepackage{{hyperref}}
\usepackage[table]{{xcolor}}
\usepackage{{titlesec}}
\hypersetup{{colorlinks=true,linkcolor=blue!50!black,urlcolor=blue!50!black}}
\definecolor{{noteBg}}{{HTML}}{{FFF8E6}}
\definecolor{{noteFrame}}{{HTML}}{{C28B00}}
\definecolor{{chapterBlue}}{{HTML}}{{1F4E79}}
\newtheorem{{definition}}{{定义}}[chapter]
\newtheorem{{theorem}}{{定理}}[chapter]
\newtheorem{{example}}{{例题}}[chapter]
\newtcolorbox{{summarybox}}{{colback=blue!3!white,colframe=chapterBlue,breakable}}
\setlist{{nosep,leftmargin=2em}}
\pagestyle{{fancy}}
\fancyhf{{}}
\fancyhead[LE,RO]{{\thepage}}
\fancyhead[LO]{{\nouppercase{{\rightmark}}}}
\fancyhead[RE]{{\nouppercase{{\leftmark}}}}
\title{{\Huge\bfseries {escape_latex(title)}\\[0.6em]\Large 课程复习教材}}
\author{{Course Note Agents}}
\date{{\today}}
\begin{{document}}
\frontmatter
\maketitle
\tableofcontents
\mainmatter
"""

    @staticmethod
    def _title_from_markdown(markdown: str) -> str | None:
        for line in markdown.splitlines():
            if line.startswith("# "):
                return line[2:].strip()
        return None

    @staticmethod
    def _drop_first_title(markdown: str) -> str:
        lines = markdown.splitlines()
        for idx, line in enumerate(lines):
            if line.startswith("# "):
                return "\n".join(lines[idx + 1 :]).strip()
        return markdown

    @staticmethod
    def _drop_duplicate_chapter_stubs(markdown: str) -> str:
        lines = markdown.splitlines()
        output: list[str] = []
        index = 0
        while index < len(lines):
            line = lines[index]
            if line.startswith("# "):
                title = line[2:].strip()
                lookahead = index + 1
                while lookahead < len(lines) and not lines[lookahead].strip():
                    lookahead += 1
                if lookahead < len(lines) and lines[lookahead].startswith("# "):
                    next_title = lines[lookahead][2:].strip()
                    stripped_next = MarkdownLatexRenderer._clean_chapter_title(next_title)
                    if title and stripped_next and (title in stripped_next or stripped_next in title):
                        index += 1
                        continue
            output.append(line)
            index += 1
        return "\n".join(output)

    @staticmethod
    def _clean_chapter_title(title: str) -> str:
        return re.sub(r"^第[一二三四五六七八九十百\d]+章\s*", "", title).strip()

    @staticmethod
    def _same_title(left: str, right: str) -> bool:
        return left == right or (left and right and (left in right or right in left))

    def _render_heading(self, level: int, title: str) -> str:
        if level == 1:
            return "\\chapter{" + self._format_heading_text(self._clean_chapter_title(title)) + "}"
        if level == 2:
            return "\\section{" + self._format_heading_text(title) + "}"
        if level == 3:
            return "\\subsection{" + self._format_heading_text(title) + "}"
        if level == 4:
            return "\\subsubsection{" + self._format_heading_text(title) + "}"
        return "\\paragraph{" + self._format_heading_text(title) + "}"

    def _format_heading_text(self, text: str) -> str:
        return self._format_inline(text).replace("\n", " ")

    @staticmethod
    def _raw_block_end(stripped: str) -> str:
        if stripped.startswith("\\["):
            return "\\]"
        match = re.match(r"\\begin\{(equation\*?|align\*?|gather\*?|multline\*?)\}", stripped)
        if match:
            return f"\\end{{{match.group(1)}}}"
        return ""

    @staticmethod
    def _looks_raw_latex(stripped: str) -> bool:
        return stripped.startswith("\\begin{") or stripped.startswith("\\end{") or stripped in {"\\]", "\\)"}

    @staticmethod
    def _is_table_start(lines: list[str], index: int) -> bool:
        if index + 1 >= len(lines):
            return False
        current = lines[index].strip()
        separator = lines[index + 1].strip()
        return current.startswith("|") and current.endswith("|") and bool(re.match(r"^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?$", separator))

    def _render_table(self, lines: list[str]) -> tuple[str, int]:
        table_lines: list[str] = []
        for line in lines:
            stripped = line.strip()
            if not stripped.startswith("|") or not stripped.endswith("|"):
                break
            table_lines.append(stripped)
        rows = [self._split_table_row(line) for line in table_lines]
        if len(rows) >= 2:
            rows.pop(1)
        column_count = max((len(row) for row in rows), default=1)
        spec = "|".join(["X"] * column_count)
        output = [f"\\begin{{tabularx}}{{\\textwidth}}{{|{spec}|}}", "\\hline"]
        for row_index, row in enumerate(rows):
            padded = row + [""] * (column_count - len(row))
            output.append(" & ".join(self._format_inline(cell) for cell in padded) + r" \\")
            output.append("\\hline")
            if row_index == 0:
                output.append("\\rowcolor{blue!6}")
        output.append("\\end{tabularx}")
        return "\n".join(output), len(table_lines)

    @staticmethod
    def _split_table_row(line: str) -> list[str]:
        return [cell.strip() for cell in line.strip().strip("|").split("|")]

    def _render_code_block(self, code_lines: list[str]) -> str:
        output = ["\\begin{tcolorbox}[colback=black!2,colframe=black!35,breakable]", "\\ttfamily\\small"]
        for line in code_lines:
            output.append(escape_latex(line).replace(" ", r"\ ") + r"\\")
        output.append("\\end{tcolorbox}")
        return "\n".join(output)

    def _format_inline(self, text: str) -> str:
        parts = re.split(r"(\$[^$]+\$)", text)
        output: list[str] = []
        for part in parts:
            if part.startswith("$") and part.endswith("$") and len(part) > 1:
                output.append(part)
            else:
                output.append(format_markdown_text(part))
        return "".join(output)


def format_markdown_text(text: str) -> str:
    parts = re.split(r"(`[^`]+`)", text)
    output: list[str] = []
    for part in parts:
        if part.startswith("`") and part.endswith("`") and len(part) >= 2:
            output.append(r"\texttt{" + escape_latex(part[1:-1]) + "}")
        else:
            output.append(format_bold_text(part))
    return "".join(output)


def format_bold_text(text: str) -> str:
    output: list[str] = []
    position = 0
    for match in re.finditer(r"\*\*(.+?)\*\*", text):
        output.append(escape_latex(text[position : match.start()]))
        output.append(r"\textbf{" + escape_latex(match.group(1)) + "}")
        position = match.end()
    output.append(escape_latex(text[position:]))
    return "".join(output)


def escape_latex(text: str) -> str:
    return "".join(SPECIALS.get(ch, ch) for ch in text)
