#!/usr/bin/env python3
"""将 cerDeclarePrint 网页打印件重建为不分断表格的 A4 PDF。"""

import argparse
from html import escape
import json
import os
from pathlib import Path
import re

from bs4 import BeautifulSoup
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

PAGE_W, PAGE_H = A4
MARGIN_X = 15 * mm
CONTENT_W = PAGE_W - 2 * MARGIN_X


def clean(text):
    return re.sub(r"\s+", " ", str(text).replace("\xa0", " ")).strip()


def norm(text):
    return re.sub(r"\s+", "", str(text).replace("\xa0", ""))


def table_rows(table):
    result = []
    for tr in table.find_all("tr"):
        cells = tr.find_all(["td", "th"], recursive=False)
        values = [clean(cell.get_text(" ", strip=True)) for cell in cells]
        start = 0
        end = len(values)
        while start < end and not values[start]:
            start += 1
        while end > start and not values[end - 1]:
            end -= 1
        values = values[start:end]
        cells = cells[start:end]
        if any(values):
            result.append((values, cells))
    return result


def find_inner_table(soup, *terms):
    for table in soup.find_all("table"):
        if table.find("table"):
            continue
        text = norm(table.get_text())
        if all(norm(term) in text for term in terms):
            return table
    raise ValueError("未找到网页栏目：" + "、".join(terms))


def find_row(rows, term, start=0):
    for index in range(start, len(rows)):
        values = rows[index][0]
        if any(norm(term) in norm(value) for value in values):
            return index, values
    raise ValueError("未找到网页字段：" + term)


def parse_html(input_path):
    soup = BeautifulSoup(input_path.read_text(encoding="utf-8"), "html.parser")
    full_text = clean(soup.get_text(" ", strip=True))
    case_match = re.search(r"卷宗号\s*[：:]\s*([A-Z0-9]+)", full_text)
    if not case_match:
        raise ValueError("未找到卷宗号")

    cover_table = find_inner_table(soup, "房地产估价机构", "备案等级申报表", "填报时间")
    cover_rows = table_rows(cover_table)
    cover = {}
    for label in ["机构名称", "申报等级", "申报事项", "填报时间"]:
        row_index, row = find_row(cover_rows, label)
        candidates = [value for value in row if value and norm(label) not in norm(value)]
        if not candidates and row_index > 0:
            candidates = [value for value in cover_rows[row_index - 1][0] if value and norm(label) not in norm(value)]
        if not candidates:
            raise ValueError("封面字段为空：" + label)
        cover[label] = candidates[0]

    promise_box = soup.find("div", class_="box")
    if not promise_box:
        raise ValueError("未找到企业法定代表人承诺")
    promise_cells = promise_box.find_all("td", class_="spyshx")
    if len(promise_cells) < 2:
        raise ValueError("法定代表人承诺内容不完整")
    promise_intro = clean(promise_cells[0].get_text(" ", strip=True))
    promise_text = clean(promise_cells[1].get_text(" ", strip=True))
    id_match = re.search(r"(\d{17}[\dXx])", promise_intro)
    if not id_match:
        raise ValueError("未找到法定代表人身份证号码")
    promise_id = id_match.group(1)

    basic_table = find_inner_table(soup, "基本情况", "机构名称", "经营范围")
    basic_rows = table_rows(basic_table)
    _, company_row = find_row(basic_rows, "机构名称")
    _, legal_row = find_row(basic_rows, "法定代表人")
    _, office_row = find_row(basic_rows, "办公地址")
    _, registration_row = find_row(basic_rows, "登记注册类型")
    _, capital_row = find_row(basic_rows, "注册资本")
    _, scope_row = find_row(basic_rows, "经营范围")
    _, record_level_row = find_row(basic_rows, "房地产估价机构备案等级")
    _, record_date_row = find_row(basic_rows, "取得备案的时间")
    manager_heading, _ = find_row(basic_rows, "机构主要负责人")
    manager_header, manager_headings = find_row(basic_rows, "姓名", manager_heading)
    managers = [values for values, _ in basic_rows[manager_header + 1:] if len(values) == len(manager_headings)]

    capital_table = find_inner_table(soup, "出资情况", "出资总人数")
    capital_rows = table_rows(capital_table)
    capital_header, capital_headings = find_row(capital_rows, "国籍")
    capital_summary, capital_summary_row = find_row(capital_rows, "出资总人数", capital_header)
    capitals = [values for values, _ in capital_rows[capital_header + 1:capital_summary] if len(values) == len(capital_headings)]

    appraiser_table = find_inner_table(soup, "估价师情况", "机构人员总人数")
    appraiser_rows = table_rows(appraiser_table)
    appraiser_header, appraiser_headings = find_row(appraiser_rows, "性别")
    appraiser_summary, appraiser_summary_row = find_row(appraiser_rows, "机构人员总人数", appraiser_header)
    appraisers = [values for values, _ in appraiser_rows[appraiser_header + 1:appraiser_summary] if len(values) == len(appraiser_headings)]

    project_table = find_inner_table(soup, "具有代表性的", "上两年度独立承担")
    project_rows = table_rows(project_table)
    project_header, project_headings = find_row(project_rows, "具有代表性的")
    project_summary, project_summary_row = find_row(project_rows, "上两年度独立承担", project_header)
    projects = [values for values, _ in project_rows[project_header + 1:project_summary] if len(values) == len(project_headings)]

    final_table = find_inner_table(soup, "机构简介", "机构申报意见")
    final_rows = table_rows(final_table)
    _, intro_row = find_row(final_rows, "机构简介")
    intro_index, intro_values = None, None
    for index, (values, cells) in enumerate(final_rows):
        if values and norm(values[0]) == "机构简介":
            intro_index, intro_values = index, cells
            break
    if intro_index is None or len(intro_values) < 2:
        raise ValueError("机构简介内容不完整")
    intro_paragraphs = [clean(part) for part in intro_values[1].get_text("\n", strip=True).splitlines() if clean(part)]
    _, consent_row = find_row(final_rows, "同意进行")
    consent = next(value for value in consent_row if "同意进行" in value)

    return {
        "case_no": case_match.group(1),
        "cover": cover,
        "promise_id": promise_id,
        "promise_text": promise_text,
        "basic": {
            "company": company_row[1],
            "legal_row": legal_row,
            "office_row": office_row,
            "registration_row": registration_row,
            "capital_row": capital_row,
            "scope": scope_row[1],
            "record_level_row": record_level_row,
            "record_date_row": record_date_row,
            "manager_headings": manager_headings,
            "managers": managers,
        },
        "capital": {"headings": capital_headings, "rows": capitals, "summary": capital_summary_row[0]},
        "appraiser": {"headings": appraiser_headings, "rows": appraisers, "summary": appraiser_summary_row[0]},
        "project": {"headings": project_headings, "rows": projects, "summary": project_summary_row[0]},
        "intro_paragraphs": intro_paragraphs,
        "consent": consent,
    }


def make_style(name, size=10, leading=None, align=TA_CENTER, bold=False, indent=0):
    return ParagraphStyle(
        name,
        fontName="DaimonCJK-Bold" if bold else "DaimonCJK",
        fontSize=size,
        leading=leading or size * 1.45,
        alignment=align,
        firstLineIndent=indent,
        wordWrap="CJK",
        textColor=colors.black,
        spaceBefore=0,
        spaceAfter=0,
    )


cell = make_style("cell", 9.2, 13)
cell_small = make_style("cell_small", 8.2, 11.5)
cell_left = make_style("cell_left", 9.2, 13, TA_LEFT)
section_style = make_style("section", 12, 17, bold=True)
header_style = make_style("header", 10, 14, TA_RIGHT)
body_style = make_style("body", 11, 23, TA_LEFT, indent=22)
intro_style = make_style("intro", 10.5, 20, TA_LEFT)


def p(text, style=cell, raw=False):
    value = str(text) if raw else escape(str(text))
    return Paragraph(value.replace("\n", "<br/>"), style)


def build_pdf(data, output_path):
    regular_font = os.environ.get("DAIMON_CJK_FONT_REGULAR")
    bold_font = os.environ.get("DAIMON_CJK_FONT_BOLD")
    if not regular_font or not bold_font:
        raise RuntimeError("Daimon 中文字体不可用")
    pdfmetrics.registerFont(TTFont("DaimonCJK", regular_font))
    pdfmetrics.registerFont(TTFont("DaimonCJK-Bold", bold_font))
    pdfmetrics.registerFontFamily("DaimonCJK", normal="DaimonCJK", bold="DaimonCJK-Bold", italic="DaimonCJK", boldItalic="DaimonCJK-Bold")

    def case_header():
        table = Table([[p("卷宗号：" + data["case_no"], header_style)]], colWidths=[CONTENT_W])
        table.setStyle(TableStyle([
            ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        return table

    def section_title(text):
        table = Table([[p(text, section_style)]], colWidths=[CONTENT_W])
        table.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 1.1, colors.black),
            ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ]))
        return table

    def form_table(rows, widths, header_rows=0, small=False):
        cooked = []
        for r, row in enumerate(rows):
            cooked_row = []
            for c, value in enumerate(row):
                style = cell_small if small else cell
                if r < header_rows:
                    style = make_style("th", 8.8 if small else 9.4, 12 if small else 13)
                cooked_row.append(value if hasattr(value, "wrap") else p(value, style))
            cooked.append(cooked_row)
        table = Table(cooked, colWidths=widths, hAlign="CENTER", repeatRows=header_rows)
        commands = [
            ("GRID", (0, 0), (-1, -1), 0.6, colors.black),
            ("BOX", (0, 0), (-1, -1), 1.1, colors.black),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]
        if header_rows:
            commands.append(("LINEBELOW", (0, header_rows - 1), (-1, header_rows - 1), 0.8, colors.black))
        table.setStyle(TableStyle(commands))
        return table

    def summary_table(text, height=None):
        table = Table([[p(text, cell_left)]], colWidths=[CONTENT_W], rowHeights=[height] if height else None)
        table.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 1.1, colors.black), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ]))
        return table

    doc = SimpleDocTemplate(
        str(output_path), pagesize=A4, leftMargin=MARGIN_X, rightMargin=MARGIN_X,
        topMargin=12 * mm, bottomMargin=12 * mm,
        title="房地产估价机构备案等级申报表", author=data["cover"]["机构名称"], subject="完整打印版",
    )
    story = []

    # 1. 封面
    story += [case_header(), Spacer(1, 34 * mm)]
    story += [p("房地产估价机构\n\n备案等级申报表", make_style("cover_title", 24, 34, bold=True)), Spacer(1, 34 * mm)]
    cover_data = []
    for index, label in enumerate(["机构名称", "申报等级", "申报事项", "填报时间"]):
        cover_data.append([
            p(label + "：", make_style("cover_label", 12, 18, TA_RIGHT, bold=True)),
            p(data["cover"][label], make_style("cover_value", 11, 18)),
        ])
    cover = Table(cover_data, colWidths=[95, CONTENT_W - 95], rowHeights=[38] * 4)
    cover.setStyle(TableStyle([
        ("LINEBELOW", (1, 0), (1, -1), 0.8, colors.black), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    story += [cover, Spacer(1, 39 * mm), p("云南省住房和城乡建设厅", make_style("cover_footer", 13, 20, bold=True)), PageBreak()]

    # 2. 法定代表人承诺
    story += [Spacer(1, 14 * mm), p("企业法定代表人承诺", make_style("promise_title", 18, 28, bold=True)), Spacer(1, 14 * mm)]
    intro = "本人<u>&nbsp;&nbsp;{}&nbsp;&nbsp;</u>（企业法定代表人）<u>&nbsp;&nbsp;{}&nbsp;&nbsp;</u>（身份证号码）郑重承诺：".format(
        escape(data["basic"]["legal_row"][1]), escape(data["promise_id"])
    )
    story += [p(intro, make_style("promise_intro", 11, 23, TA_LEFT), raw=True), Spacer(1, 5 * mm)]
    story += [p(data["promise_text"], body_style), Spacer(1, 17 * mm)]
    story += [p("企业法定代表人：（签字）____________________（公章）", make_style("signature", 11, 22, TA_RIGHT))]
    story += [Spacer(1, 10 * mm), p("________年________月________日", make_style("date", 11, 22, TA_RIGHT)), PageBreak()]

    # 3. 基本情况、备案情况、负责人情况
    basic = data["basic"]
    story += [case_header(), section_title("基 本 情 况")]
    def expand_pair_row(row):
        if len(row) == 6:
            return row
        if len(row) == 4:
            return [row[0], row[1], "", row[2], row[3], ""]
        raise ValueError("基本情况行的单元格数量异常：" + "｜".join(row))

    legal = expand_pair_row(basic["legal_row"])
    office = expand_pair_row(basic["office_row"])
    registration = expand_pair_row(basic["registration_row"])
    capital = expand_pair_row(basic["capital_row"])
    basic_rows = [
        ["机构名称", basic["company"], "", "", "", ""],
        legal,
        office,
        registration,
        capital,
        ["经营范围", basic["scope"], "", "", "", ""],
    ]
    basic_table = form_table(basic_rows, [82, 85, 85, 74, 74, CONTENT_W - 400])
    basic_table.setStyle(TableStyle([
        ("SPAN", (1, 0), (5, 0)), ("SPAN", (1, 2), (2, 2)), ("SPAN", (4, 2), (5, 2)),
        ("SPAN", (1, 3), (2, 3)), ("SPAN", (4, 3), (5, 3)), ("SPAN", (1, 4), (2, 4)),
        ("SPAN", (4, 4), (5, 4)), ("SPAN", (1, 5), (5, 5)),
    ]))
    story += [basic_table, Spacer(1, 5 * mm), section_title("申报前房地产估价机构备案情况")]
    level = basic["record_level_row"]
    dates = basic["record_date_row"]
    record_rows = [
        level,
        [dates[0], dates[1], dates[2], dates[3]],
        ["", "", dates[4], dates[5]],
    ]
    record = form_table(record_rows, [130, 80, 105, CONTENT_W - 315], small=True)
    record.setStyle(TableStyle([("SPAN", (0, 1), (0, 2)), ("SPAN", (1, 1), (1, 2))]))
    story += [record, Spacer(1, 5 * mm), section_title("机构主要负责人及各部门负责人情况（不含兼职人员）")]
    story += [form_table([basic["manager_headings"]] + basic["managers"], [48, 36, 48, 90, 60, 62, 45, CONTENT_W - 389], header_rows=1, small=True), PageBreak()]

    # 4. 出资情况
    story += [case_header(), section_title("出 资 情 况")]
    story += [form_table([data["capital"]["headings"]] + data["capital"]["rows"], [50, 40, 125, 85, 65, 50, CONTENT_W - 415], header_rows=1, small=True)]
    story += [summary_table(data["capital"]["summary"]), PageBreak()]

    # 5. 估价师情况
    story += [case_header(), section_title("估 价 师 情 况")]
    story += [form_table([data["appraiser"]["headings"]] + data["appraiser"]["rows"], [50, 36, 45, 82, 128, 75, CONTENT_W - 416], header_rows=1, small=True)]
    story += [summary_table(data["appraiser"]["summary"], height=70), PageBreak()]

    # 6. 代表性估价项目
    story += [case_header()]
    story += [form_table([data["project"]["headings"]] + data["project"]["rows"], [110, 85, 45, 45, 57, 57, 58, CONTENT_W - 457], header_rows=1, small=True)]
    story += [summary_table(data["project"]["summary"], height=75), PageBreak()]

    # 7. 机构简介与意见栏
    story += [case_header()]
    intro_text = "<br/>".join(escape(part) for part in data["intro_paragraphs"])
    intro_para = Paragraph(intro_text, intro_style)

    def vertical_label(columns):
        label = Table([[p("\n".join(text), cell_small) for text in columns]], colWidths=[23 * 3 / len(columns)] * len(columns))
        label.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        return label

    date_text = "&nbsp;&nbsp;&nbsp;&nbsp;年&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;月&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;日"
    agency_block = Table([
        [p(data["consent"], make_style("agency_consent", 10, 19, TA_LEFT)), ""],
        ["", p("（盖章）", make_style("agency_seal", 10, 18, TA_RIGHT))],
        ["", p(date_text, make_style("agency_date", 10, 18, TA_RIGHT), raw=True)],
    ], colWidths=[275, CONTENT_W - 85 - 14 - 275], rowHeights=[45, 28, 28])
    agency_block.setStyle(TableStyle([
        ("SPAN", (0, 0), (0, 2)), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    final_rows = [
        [p("机\n构\n简\n介"), intro_para],
        [p("机\n构\n申\n报\n意\n见"), agency_block],
        [vertical_label(["州市级", "住房城乡建设", "主管部门意见"]), p("<br/><br/>（盖章）<br/><br/>" + date_text, make_style("city_opinion", 10, 20, TA_RIGHT), raw=True)],
        [vertical_label(["省级", "住房城乡建设", "主管部门意见"]), p("<br/><br/>（盖章）<br/><br/>" + date_text, make_style("province_opinion", 10, 20, TA_RIGHT), raw=True)],
        [p("备\n案\n情\n况"), ""],
    ]
    final_table = Table(final_rows, colWidths=[85, CONTENT_W - 85], rowHeights=[180, 115, 120, 120, 60])
    final_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.6, colors.black), ("BOX", (0, 0), (-1, -1), 1.1, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story += [final_table]
    doc.build(story)


def render_qa(pdf_path, qa_dir):
    import pypdfium2 as pdfium
    from PIL import Image, ImageDraw

    qa_dir.mkdir(parents=True, exist_ok=True)
    document = pdfium.PdfDocument(str(pdf_path))
    images = []
    for index, page in enumerate(document):
        image = page.render(scale=1.5).to_pil().convert("RGB")
        path = qa_dir / f"page-{index + 1:03d}.png"
        image.save(path)
        images.append(image)
    thumb_w, thumb_h, gap, label_h, cols = 300, 424, 16, 24, 3
    rows = (len(images) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * thumb_w + (cols + 1) * gap, rows * (thumb_h + label_h) + (rows + 1) * gap), "#dddddd")
    draw = ImageDraw.Draw(sheet)
    for index, image in enumerate(images):
        thumb = image.copy()
        thumb.thumbnail((thumb_w, thumb_h))
        x = gap + (index % cols) * (thumb_w + gap)
        y = gap + (index // cols) * (thumb_h + label_h + gap)
        sheet.paste(thumb, (x, y))
        draw.text((x, y + thumb_h + 4), f"Page {index + 1}", fill="black")
    sheet.save(qa_dir / "contact-sheet.png")
    return len(images)


def main():
    parser = argparse.ArgumentParser(description="从 cerDeclarePrint 保存网页生成完整 A4 PDF")
    parser.add_argument("input", type=Path, help="保存的 cerDeclarePrint HTML 网页")
    parser.add_argument("-o", "--output", type=Path, help="输出 PDF 路径")
    parser.add_argument("--qa-dir", type=Path, help="逐页预览与联系表输出目录")
    args = parser.parse_args()
    input_path = args.input.expanduser().resolve()
    if not input_path.is_file():
        raise FileNotFoundError(input_path)
    output = (args.output or input_path.with_name(input_path.stem + "_完整打印版.pdf")).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    data = parse_html(input_path)
    build_pdf(data, output)
    result = {"output": str(output), "case_no": data["case_no"]}
    if args.qa_dir:
        qa_dir = args.qa_dir.expanduser().resolve()
        result["pages"] = render_qa(output, qa_dir)
        result["contact_sheet"] = str(qa_dir / "contact-sheet.png")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
