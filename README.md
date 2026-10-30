# laopanpdf

将老潘网站保存的 `cerDeclarePrint.html` 申报表网页重建为 A4 完整打印版 PDF，解决原网站打印时表格被截断、跨页拆断、末页意见栏错位等问题。

## 安装

### 方式一：导入技能包

在支持 `.skill` 技能包的 Kimi 客户端中导入本仓库根目录的 `laopanpdf.skill`，然后刷新技能列表。

### 方式二：复制源码目录

将本仓库中的 `laopanpdf/` 整个目录复制到目标客户端的 skills 目录，刷新或重启客户端。安装后应能发现名为 `laopanpdf` 的技能。

## 使用

把从同一网站完整保存的 HTML 网页交给 Kimi，并输入：

```text
/laopanpdf 用这个网页生成完整 PDF
```

技能会重新抽取当前网页数据，生成 PDF 和逐页预览，不会复用此前申报表的数据。第 3～6 页直接按照 HTML 的实际列宽、行高、合并单元格和字段位置重建，不再把不同栏目套入固定列数模板。

## 命令行独立运行

```bash
python3 laopanpdf/scripts/laopanpdf.py input.html -o output.pdf --qa-dir qa
```

## 依赖与中文字体

安装 Python 依赖：

```bash
python3 -m pip install -r laopanpdf/requirements.txt
```

脚本按以下顺序选择中文字体：

1. 命令行参数 `--font-regular`、`--font-bold`。
2. `LAOPANPDF_FONT_REGULAR`、`LAOPANPDF_FONT_BOLD` 或 Kimi Work 的 `DAIMON_CJK_FONT_REGULAR`、`DAIMON_CJK_FONT_BOLD`。
3. 自动检测常见 macOS、Windows、Linux 中文字体；找不到粗体时复用常规字体。

自动检测失败时手动指定：

```bash
python3 laopanpdf/scripts/laopanpdf.py input.html -o output.pdf \
  --font-regular "/path/to/Chinese-Regular.ttf" \
  --font-bold "/path/to/Chinese-Bold.ttf"
```

## 文件

- `laopanpdf/SKILL.md`：触发条件与执行规范。
- `laopanpdf/scripts/laopanpdf.py`：网页解析、PDF 生成与逐页预览脚本。
- `laopanpdf/requirements.txt`：跨平台 Python 依赖清单。
- `laopanpdf.skill`：可移植安装包。
