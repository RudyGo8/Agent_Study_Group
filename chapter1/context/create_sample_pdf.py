"""
创建测试用样例 PDF
生成一份包含多种货币金额和计算的财务报告 PDF
"""

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
import os


def create_financial_report():
    """创建用于测试的样例财务报告 PDF"""

    # 创建 PDF
    filename = "sample_financial_report_q1_2024.pdf"
    doc = SimpleDocTemplate(filename, pagesize=letter)

    # "Flowable" 对象的容器
    elements = []

    # 定义样式
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#1f4788'),
        spaceAfter=30,
        alignment=TA_CENTER
    )

    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=16,
        textColor=colors.HexColor('#1f4788'),
        spaceAfter=12,
    )

    # 标题
    elements.append(Paragraph("Global Corporation Financial Report", title_style))
    elements.append(Paragraph("Q1 2024 - Quarterly Results", styles['Heading2']))
    elements.append(Spacer(1, 0.5*inch))

    # 执行摘要
    elements.append(Paragraph("Executive Summary", heading_style))
    summary_text = """This report presents the financial performance of Global Corporation
    for the first quarter of 2024. The company operates in multiple regions with
    transactions in various currencies. Total consolidated revenue for Q1 2024
    reached $45.8 million USD, representing a 12% increase year-over-year."""
    elements.append(Paragraph(summary_text, styles['BodyText']))
    elements.append(Spacer(1, 0.3*inch))

    # 区域收入表
    elements.append(Paragraph("Regional Revenue Breakdown", heading_style))

    revenue_data = [
        ['Region', 'Local Currency', 'Q1 2024 Revenue', 'Q4 2023 Revenue', 'Growth %'],
        ['North America', 'USD', '$15,250,000', '$14,100,000', '8.16%'],
        ['Europe', 'EUR', '€11,340,000', '€10,800,000', '5.00%'],
        ['United Kingdom', 'GBP', '£8,920,000', '£8,500,000', '4.94%'],
        ['Asia Pacific', 'JPY', '¥1,245,000,000', '¥1,180,000,000', '5.51%'],
        ['Singapore', 'SGD', 'S$4,180,000', 'S$3,950,000', '5.82%'],
    ]

    revenue_table = Table(revenue_data, colWidths=[2*inch, 1.2*inch, 1.5*inch, 1.5*inch, 0.8*inch])
    revenue_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))

    elements.append(revenue_table)
    elements.append(Spacer(1, 0.3*inch))

    # 运营支出
    elements.append(Paragraph("Operating Expenses by Department", heading_style))

    expense_data = [
        ['Department', 'Q1 2024 (USD)', 'Q4 2023 (USD)', 'Change'],
        ['Research & Development', '$8,450,000', '$7,900,000', '+$550,000'],
        ['Sales & Marketing', '$6,230,000', '$6,100,000', '+$130,000'],
        ['General & Administrative', '$4,180,000', '$4,050,000', '+$130,000'],
        ['Operations', '$9,870,000', '$9,500,000', '+$370,000'],
        ['Total Operating Expenses', '$28,730,000', '$27,550,000', '+$1,180,000'],
    ]

    expense_table = Table(expense_data, colWidths=[2.5*inch, 1.5*inch, 1.5*inch, 1.2*inch])
    expense_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -2), colors.lightgrey),
        ('BACKGROUND', (0, -1), (-1, -1), colors.yellow),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))

    elements.append(expense_table)
    elements.append(Spacer(1, 0.3*inch))

    # 关键财务指标
    elements.append(Paragraph("Key Financial Metrics", heading_style))

    metrics_text = """
    • Gross Profit Margin: 37.2%<br/>
    • Operating Profit Margin: 18.4%<br/>
    • Net Profit Margin: 14.8%<br/>
    • EBITDA: $10,250,000 USD<br/>
    • Cash Flow from Operations: $8,930,000 USD<br/>
    • Total Assets: $125,400,000 USD<br/>
    • Total Liabilities: $48,200,000 USD<br/>
    • Shareholders' Equity: $77,200,000 USD<br/>
    """
    elements.append(Paragraph(metrics_text, styles['BodyText']))

    # 加一个分页符
    elements.append(PageBreak())

    # 使用的汇率
    elements.append(Paragraph("Currency Exchange Rates (as of March 31, 2024)", heading_style))

    exchange_data = [
        ['Currency Pair', 'Exchange Rate', 'Previous Quarter', 'Change'],
        ['USD/EUR', '0.9234', '0.9156', '+0.85%'],
        ['USD/GBP', '0.7891', '0.7823', '+0.87%'],
        ['USD/JPY', '149.85', '147.23', '+1.78%'],
        ['USD/SGD', '1.3452', '1.3389', '+0.47%'],
    ]

    exchange_table = Table(exchange_data, colWidths=[2*inch, 1.5*inch, 1.5*inch, 1.2*inch])
    exchange_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))

    elements.append(exchange_table)
    elements.append(Spacer(1, 0.3*inch))

    # 投资组合
    elements.append(Paragraph("Investment Portfolio Performance", heading_style))

    portfolio_text = """The company's investment portfolio showed strong performance in Q1 2024:

    • Fixed Income Securities: $23,450,000 USD (yielding 4.2% annually)
    • Equity Investments: $18,750,000 USD (up 8.3% this quarter)
    • Real Estate Holdings: $31,200,000 USD (appreciation of 3.1%)
    • Cash and Cash Equivalents: $15,890,000 USD

    Total portfolio value: $89,290,000 USD, representing a 5.7% increase from Q4 2023."""

    elements.append(Paragraph(portfolio_text, styles['BodyText']))
    elements.append(Spacer(1, 0.3*inch))

    # 未来预测
    elements.append(Paragraph("Q2 2024 Projections", heading_style))

    projection_data = [
        ['Metric', 'Q1 2024 Actual', 'Q2 2024 Projected', 'Growth'],
        ['Total Revenue', '$45,800,000', '$48,500,000', '+5.9%'],
        ['Operating Expenses', '$28,730,000', '$29,800,000', '+3.7%'],
        ['Net Income', '$6,780,000', '$7,450,000', '+9.9%'],
        ['EPS (Earnings Per Share)', '$2.34', '$2.57', '+9.8%'],
    ]

    projection_table = Table(projection_data, colWidths=[2.5*inch, 1.5*inch, 1.5*inch, 1*inch])
    projection_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.lightblue),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))

    elements.append(projection_table)
    elements.append(Spacer(1, 0.3*inch))

    # 页脚
    footer_text = """
    <para alignment="center">
    <b>Note:</b> All financial figures are preliminary and subject to audit.<br/>
    For more information, please contact: investor.relations@globalcorp.com<br/>
    Global Corporation © 2024 - Confidential Financial Report
    </para>
    """
    elements.append(Spacer(1, 0.5*inch))
    elements.append(Paragraph(footer_text, styles['Normal']))

    # 生成 PDF
    doc.build(elements)

    print(f"Sample PDF created: {filename}")
    return filename


def create_simple_expense_report():
    """创建一份更简单的支出报告，用于快速测试"""

    filename = "simple_expense_report.pdf"
    doc = SimpleDocTemplate(filename, pagesize=A4)

    elements = []
    styles = getSampleStyleSheet()

    # 标题
    elements.append(Paragraph("Quarterly Expense Report", styles['Title']))
    elements.append(Spacer(1, 0.2*inch))

    # 简单的支出数据
    elements.append(Paragraph("Q1 2024 Regional Expenses", styles['Heading2']))

    expense_text = """
    Our company has the following expenses for Q1 2024:

    <b>United States Office:</b> $2,500,000 USD<br/>
    <b>United Kingdom Office:</b> £1,800,000 GBP<br/>
    <b>Japan Office:</b> ¥380,000,000 JPY<br/>
    <b>European Union Office:</b> €2,100,000 EUR<br/>
    <b>Singapore Office:</b> S$3,200,000 SGD<br/>

    These expenses include salaries, operations, marketing, and R&D costs.

    Additional financial metrics:
    • Total headcount: 1,250 employees globally
    • Average expense per employee: varies by region
    • Projected Q2 expense reduction target: 8% across all regions
    """

    elements.append(Paragraph(expense_text, styles['BodyText']))

    # 生成 PDF
    doc.build(elements)

    print(f"Simple PDF created: {filename}")
    return filename


if __name__ == "__main__":
    # 创建两份 PDF
    create_financial_report()
    create_simple_expense_report()

    # 如有需要则创建 PDF 的 fixtures 目录
    os.makedirs("fixtures/pdfs", exist_ok=True)

    # 把 PDF 移到测试目录
    import shutil
    for pdf in ["sample_financial_report_q1_2024.pdf", "simple_expense_report.pdf"]:
        if os.path.exists(pdf):
            shutil.move(pdf, f"fixtures/pdfs/{pdf}")

    print("\nPDFs created in fixtures/pdfs/ directory")
    print("You can host these PDFs online or use a local server for testing")
