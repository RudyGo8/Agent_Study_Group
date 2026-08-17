#!/usr/bin/env python3
"""检查多语言版本的结构完整性。

防止主页或某章 README 改动后，其它语言版本跟不上而漂移。CI 中运行；
本地也可直接 `python scripts/check_i18n_consistency.py` 跑。

核心原则：**自动发现语言，不硬编码**。下次有人加新语言（日语、韩语…）时，
CI 自动适配，无需改脚本。

目录约定（中文为主语言）：
  - 中文主 README：仓库根目录 README.md（不放进 docs/）
  - 其它语言主 README：docs/<locale>/README.md（如 docs/en/README.md）
  - 学习建议：docs/<locale>/LEARNING.md（含中文 docs/zh-CN/LEARNING.md）
  - 章节 README：中文默认 chapterN/README.md；其它语言 chapterN/README.<locale>.md
    （ISO 639-1 + ISO 3166-1，如 README.en.md、README.zh-TW.md）

严格规则：**只要某语言有自己的主 README，CI 就要求它完整**：
  - 10 章 chapter README（中文为 README.md，其它为 README.<locale>.md）
  - docs/<locale>/LEARNING.md
  - 每章项目数与中文版对齐
  - git clone 命令数对齐
  - 内容速览表 ≥5 列

退出码：0 = 全部一致；1 = 发现不一致。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CHAPTERS = range(1, 11)


def chapter_suffix(locale: str) -> str:
    """章节 README 后缀：中文（zh-CN）默认为空 → README.md；其它如 en → .en。"""
    if locale == "zh-CN":
        return ""
    return f".{locale}"


def main_readme_path(locale: str) -> Path:
    if locale == "zh-CN":
        return ROOT / "README.md"
    return ROOT / "docs" / locale / "README.md"


def learning_path(locale: str) -> Path:
    return ROOT / "docs" / locale / "LEARNING.md"


def project_count_in_table(path: Path) -> int:
    """统计 chapter README 表格里项目数据行数（含 ✅/📖/🚧 类型列的行）。"""
    if not path.exists():
        return -1
    pattern = re.compile(r"^\|.*\| [✅📖🚧]+ \|")
    return sum(
        1 for line in path.read_text(encoding="utf-8").splitlines() if pattern.match(line)
    )


def count_git_clones(path: Path) -> int:
    if not path.exists():
        return -1
    return len(re.findall(r"^git clone ", path.read_text(encoding="utf-8"), re.MULTILINE))


def toc_table_columns(path: Path) -> int:
    """主 README 内容速览表第一个数据行的列数。"""
    if not path.exists():
        return -1
    for line in path.read_text(encoding="utf-8").splitlines():
        if re.match(r"^\| \d+ \|", line):
            return line.count("|") - 1
    return -1


def discover_locales() -> list[str]:
    """发现所有主语言 locale。

    - 中文（zh-CN）始终包含（根目录 README.md）
    - 其余：docs/<locale>/README.md 存在即纳入
    """
    locales = ["zh-CN"]
    docs = ROOT / "docs"
    if docs.is_dir():
        for path in sorted(docs.iterdir()):
            if path.is_dir() and path.name != "zh-CN" and (path / "README.md").exists():
                locales.append(path.name)
    return locales


def main() -> int:
    errors: list[str] = []

    # ===== 自动发现语言 =====
    locales = discover_locales()

    print("== 自动发现语言 ==")
    print(f"  发现 {len(locales)} 个主 README（全部要求完整翻译）:")
    for locale in locales:
        print(f"    {locale}  (chapter suffix: {chapter_suffix(locale)!r})")
    print()

    # ===== 检查 1：每个发现的主 README 都有完整结构 =====
    print("== 检查 1：主 README 内容速览表结构（≥5 列）==")
    for locale in locales:
        path = main_readme_path(locale)
        cols = toc_table_columns(path)
        if cols < 5:
            errors.append(
                f"{path.relative_to(ROOT)} ({locale}) 内容速览表列数 {cols} < 5"
                "（应至少 5 列：章/主题/核心/正文/代码）"
            )
        else:
            print(f"  ✓ {locale}: {cols} 列")
    print()

    # ===== 检查 2：git clone 命令数对齐（以中文版为基准）=====
    print("== 检查 2：主 README git clone 命令数 ==")
    zh_clones = count_git_clones(main_readme_path("zh-CN"))
    print(f"  中文基准：{zh_clones} 条")
    for locale in locales:
        if locale == "zh-CN":
            continue
        path = main_readme_path(locale)
        count = count_git_clones(path)
        if count != zh_clones:
            errors.append(
                f"{path.relative_to(ROOT)} ({locale}) git clone 数 {count} ≠ 中文版 {zh_clones}"
            )
        else:
            print(f"  ✓ {locale}: {count} 条")
    print()

    # ===== 检查 3：每个主语言必须有 docs/<locale>/LEARNING.md =====
    print("== 检查 3：docs/<locale>/LEARNING.md 齐全 ==")
    for locale in locales:
        path = learning_path(locale)
        if not path.exists():
            errors.append(
                f"{path.relative_to(ROOT)} 不存在（{locale} 是主语言，需有学习建议文档）"
            )
        else:
            print(f"  ✓ {path.relative_to(ROOT)} ({locale})")
    print()

    # ===== 检查 4：每个主 README 语言必须有全部 10 章 README =====
    print("== 检查 4：chapterN/README[.locale].md 齐全 ==")
    for locale in locales:
        suffix = chapter_suffix(locale)
        missing = []
        for n in CHAPTERS:
            path = ROOT / f"chapter{n}/README{suffix}.md"
            if not path.exists():
                missing.append(str(n))
        if missing:
            errors.append(
                f"{locale} 缺章节 README：第 {', '.join(missing)} 章"
            )
        else:
            print(f"  ✓ {locale}: 10 章齐全")
    print()

    # ===== 检查 5：每章项目数对齐（所有主 README 语言）=====
    print("== 检查 5：每章项目数（所有语言对齐）==")
    zh_counts = {
        n: project_count_in_table(ROOT / f"chapter{n}/README.md")
        for n in CHAPTERS
    }
    total_zh = sum(zh_counts.values())
    print(f"  中文基准：{total_zh} 项目，分布 {[zh_counts[n] for n in CHAPTERS]}")
    for locale in locales:
        if locale == "zh-CN":
            continue
        suffix = chapter_suffix(locale)
        total = 0
        mismatches = []
        for n in CHAPTERS:
            path = ROOT / f"chapter{n}/README{suffix}.md"
            count = project_count_in_table(path)
            total += max(count, 0)
            zh = zh_counts[n]
            if count != zh:
                mismatches.append(f"第{n}章 {count}≠{zh}")
        if mismatches:
            errors.append(
                f"{locale} 项目数不一致（{len(mismatches)} 处）：{'; '.join(mismatches[:3])}"
            )
        else:
            print(f"  ✓ {locale}: {total} 项目对齐")
    print()

    # ===== 检查 6：主 README 语言切换栏完整性 =====
    print("== 检查 6：主 README 语言切换栏列出所有语言 ==")
    zh_text = main_readme_path("zh-CN").read_text(encoding="utf-8")
    switcher_match = re.search(
        r"\*\*[^*]*中文[^*]*\*\*.*?(?=\n\n|\n[^*])", zh_text, re.DOTALL
    )
    if switcher_match:
        switcher = switcher_match.group(0)
        missing_in_switcher = []
        for locale in locales:
            if locale == "zh-CN":
                continue
            # 语言切换栏应链接到 docs/<locale>/README.md
            if f"docs/{locale}/README.md" not in switcher:
                missing_in_switcher.append(locale)
        if missing_in_switcher:
            errors.append(
                f"README.md 语言切换栏缺少：{', '.join(missing_in_switcher)}"
            )
        else:
            print(f"  ✓ README.md 列出全部 {len(locales)} 种语言")
    else:
        print("  ⚠️ 未找到语言切换栏（跳过此项检查）")
    print()

    # ===== 汇总 =====
    if errors:
        print(f"❌ 发现 {len(errors)} 个问题：")
        for e in errors:
            print(f"   - {e}")
        print()
        print("修复提示：")
        print("  - 文件缺失：从中文版复制并翻译")
        print("  - 非中文主 README 放在 docs/<locale>/README.md")
        print("  - 学习建议放在 docs/<locale>/LEARNING.md")
        print("  - 项目数不一致：参考中文版 chapterN/README.md 同步项目列表")
        print("  - git clone 不一致：参考 README.md 附录段同步")
        print("  - 内容速览表结构：参考 README.md 的 5 列模板")
        print("  - 语言切换栏：参考 README.md 顶部，加入 docs/<locale>/README.md 链接")
        print("  - 章节 README 命名：中文为 README.md，其它为 README.<locale>.md（如 README.en.md）")
        return 1
    print("✓ 所有语言版本结构一致/完整")
    return 0


if __name__ == "__main__":
    sys.exit(main())
