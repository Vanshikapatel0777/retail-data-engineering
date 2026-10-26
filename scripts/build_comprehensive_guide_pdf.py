"""
scripts/build_comprehensive_guide_pdf.py
=========================================
Generates a comprehensive, textbook-quality Master Data Engineering Guide PDF
for the Retail Sales Data Engineering project.

Topics covered in exhaustive detail:
1. Tutor Introduction & Foundational Concepts (Why every tool was chosen)
2. What the Project Does (Business logic, edge cases, Kaggle dataset)
3. Step-by-Step Manual Build Walkthrough (Code-by-code, function-by-function)
4. Engineering Rationale (Why it was built that way, trade-offs, idempotency)
5. Interview Masterclass (Elevator pitches, Q&A, spoken scripts)
"""

from __future__ import annotations

import os
from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether, HRFlowable
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PDF = PROJECT_ROOT / "docs" / "Retail_Data_Engineering_Master_Guide.pdf"


class NumberedCanvas(canvas.Canvas):
    """Two-pass canvas to dynamically compute and draw total page count and headers/footers."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        if self._pageNumber == 1:
            # Suppress headers and footers on the cover page
            return

        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#718096"))

        # Running Header
        self.drawString(54, 11 * inch - 36, "RETAIL SALES DATA ENGINEERING PIPELINE — MASTER TUTOR GUIDE")
        self.setStrokeColor(colors.HexColor("#E2E8F0"))
        self.setLineWidth(0.75)
        self.line(54, 11 * inch - 42, 8.5 * inch - 54, 11 * inch - 42)

        # Running Footer
        self.line(54, 45, 8.5 * inch - 54, 45)
        self.drawString(54, 32, "Author: Vanshika Patel | Portfolio & Interview Preparation Guide")
        page_str = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(8.5 * inch - 54, 32, page_str)
        self.restoreState()


def create_callout_box(title: str, text: str, styles: dict, box_type: str = "note") -> Table:
    """Renders a styled callout box (Note, Important, Architecture, or Interview Tip)."""
    color_map = {
        "note": (colors.HexColor("#EBF8FF"), colors.HexColor("#3182CE")),       # Blue
        "important": (colors.HexColor("#FFF5F5"), colors.HexColor("#E53E3E")),  # Red
        "tip": (colors.HexColor("#F0FFF4"), colors.HexColor("#38A169")),        # Green
        "arch": (colors.HexColor("#FAF5FF"), colors.HexColor("#805AD5")),       # Purple
    }
    bg_color, border_color = color_map.get(box_type, color_map["note"])

    header_style = ParagraphStyle(
        f"CalloutHeader_{box_type}",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=13,
        textColor=border_color,
    )
    body_style = ParagraphStyle(
        f"CalloutBody_{box_type}",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#2D3748"),
    )

    content = [
        Paragraph(title.upper(), header_style),
        Spacer(1, 4),
        Paragraph(text, body_style)
    ]

    t = Table([[content]], colWidths=[7.2 * inch])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), bg_color),
        ('BOX', (0, 0), (-1, -1), 1, border_color),
        ('LINEBEFORE', (0, 0), (0, -1), 4, border_color),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12),
    ]))
    return t


def create_code_block(code_text: str, styles: dict) -> Table:
    """Formats code in a clean terminal-like container."""
    code_style = ParagraphStyle(
        "CodeText",
        parent=styles["Normal"],
        fontName="Courier",
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#1A202C"),
    )
    # Escape XML entities
    safe_code = code_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br/>")
    p = Paragraph(safe_code, code_style)
    t = Table([[p]], colWidths=[7.2 * inch])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#F7FAFC")),
        ('BOX', (0, 0), (-1, -1), 0.75, colors.HexColor("#E2E8F0")),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
    ]))
    return t


def build_pdf():
    OUTPUT_PDF.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(OUTPUT_PDF),
        pagesize=letter,
        leftMargin=0.65 * inch,
        rightMargin=0.65 * inch,
        topMargin=0.65 * inch,
        bottomMargin=0.65 * inch,
    )

    raw_styles = getSampleStyleSheet()

    # Custom Typography Palette
    styles = {
        "Title": ParagraphStyle(
            "CoverTitle",
            parent=raw_styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=24,
            leading=30,
            textColor=colors.HexColor("#1A365D"),
            alignment=0,
        ),
        "Subtitle": ParagraphStyle(
            "CoverSubtitle",
            parent=raw_styles["Normal"],
            fontName="Helvetica",
            fontSize=12,
            leading=16,
            textColor=colors.HexColor("#4A5568"),
            alignment=0,
        ),
        "H1": ParagraphStyle(
            "Header1",
            parent=raw_styles["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=16,
            leading=20,
            textColor=colors.HexColor("#1A365D"),
            spaceBefore=14,
            spaceAfter=6,
            keepWithNext=True,
        ),
        "H2": ParagraphStyle(
            "Header2",
            parent=raw_styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=16,
            textColor=colors.HexColor("#2B6CB0"),
            spaceBefore=10,
            spaceAfter=4,
            keepWithNext=True,
        ),
        "H3": ParagraphStyle(
            "Header3",
            parent=raw_styles["Heading3"],
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#2D3748"),
            spaceBefore=8,
            spaceAfter=3,
            keepWithNext=True,
        ),
        "Body": ParagraphStyle(
            "BodyTextCustom",
            parent=raw_styles["BodyText"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=14,
            textColor=colors.HexColor("#2D3748"),
            spaceAfter=6,
        ),
        "Bullet": ParagraphStyle(
            "BulletCustom",
            parent=raw_styles["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=13.5,
            textColor=colors.HexColor("#2D3748"),
            leftIndent=15,
            firstLineIndent=-10,
            spaceAfter=3,
        ),
        "Normal": raw_styles["Normal"],
    }

    story = []

    # =========================================================================
    # COVER PAGE
    # =========================================================================
    story.append(Spacer(1, 40))
    story.append(Paragraph("DATA ENGINEERING MASTERCLASS", ParagraphStyle(
        "CoverEyebrow", fontName="Helvetica-Bold", fontSize=10, leading=12, textColor=colors.HexColor("#3182CE")
    )))
    story.append(Spacer(1, 8))
    story.append(Paragraph("Retail Sales Data Engineering Pipeline", styles["Title"]))
    story.append(Spacer(1, 6))
    story.append(Paragraph("From Raw Kaggle Transactions to Analytics-Ready PostgreSQL Warehouse, Parquet Data Lake, and Azure Cloud Storage", styles["Subtitle"]))
    story.append(Spacer(1, 14))
    story.append(HRFlowable(width="100%", thickness=3, color=colors.HexColor("#1A365D"), spaceAfter=20))

    meta_text = """
    <b>Author / Candidate:</b> Vanshika Patel<br/>
    <b>Target Role:</b> Associate / Junior Data Engineer<br/>
    <b>Core Technologies:</b> Python 3.14, PostgreSQL 17, Apache Arrow / Parquet, SQLAlchemy 2, Psycopg 3, Pytest, Azure ADLS Gen2<br/>
    <b>Document Purpose:</b> Exhaustive tutor walkthrough explaining core data engineering principles, technical decisions, complete source code architecture, and interview defense strategies.
    """
    story.append(Paragraph(meta_text, styles["Body"]))
    story.append(Spacer(1, 20))

    story.append(create_callout_box(
        "HOW TO USE THIS GUIDE",
        "This document is divided into 5 structured sections. Read <b>Part I</b> to master the fundamental concepts as if taught by a senior tutor. Study <b>Part II</b> to understand the exact business problem and dataset. Review <b>Part III</b> for an exhaustive code-by-code walkthrough. Read <b>Part IV</b> to learn why specific architecture decisions were made. Finally, use <b>Part V</b> to rehearse your spoken responses for job interviews.",
        styles, "tip"
    ))
    story.append(PageBreak())

    # =========================================================================
    # PART I: THE TUTOR SECTION — CONCEPTS & THE "WHY"
    # =========================================================================
    story.append(Paragraph("PART I: Foundational Concepts & The Tutor's 'Why'", styles["H1"]))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#CBD5E0"), spaceAfter=10))

    story.append(Paragraph("1.1 What is Data Engineering?", styles["H2"]))
    story.append(Paragraph(
        "To understand data engineering, consider a water treatment plant. Raw water from a river is muddy, contaminated, and flows unpredictably. The municipal facility builds intake pumps, filtration beds, chemical treatments, and storage reservoirs before piping clean, safe drinking water to houses and factories. "
        "<b>In the tech industry, raw data is like muddy river water.</b> It arrives in different formats (Excel, CSV, JSON, streaming APIs) with corrupt characters, missing values, duplicates, and cancelled transactions. "
        "Data Engineers build the automated software pipelines, storage tanks (Data Lakes/Warehouses), and quality filtration systems that turn this raw sludge into trusted, analytics-ready data for Business Analysts, Data Scientists, and executive dashboards.",
        styles["Body"]
    ))

    story.append(Paragraph("1.2 The Core Paradigm: ETL vs. ELT (And Why We Use a Hybrid)", styles["H2"]))
    story.append(Paragraph(
        "One of the most frequent interview questions asks you to contrast ETL and ELT:",
        styles["Body"]
    ))
    story.append(Paragraph("• <b>ETL (Extract, Transform, Load):</b> Raw data is extracted from the source, transformed (cleaned, filtered, enriched) in an intermediate compute engine (like Python/Pandas or Spark), and only the clean data is loaded into the destination database. <i>Advantage:</i> Keeps junk data out of the warehouse. <i>Disadvantage:</i> Transformations are limited by Python memory.", styles["Bullet"]))
    story.append(Paragraph("• <b>ELT (Extract, Load, Transform):</b> Raw data is loaded directly into a high-capacity database/warehouse first, and SQL queries are used to transform it inside the database. <i>Advantage:</i> Extremely fast for massive datasets; raw data is preserved. <i>Disadvantage:</i> Staging tables must accept loose types (like everything stored as TEXT).", styles["Bullet"]))

    story.append(create_callout_box(
        "WHY OUR PROJECT USES A HYBRID ETL + ELT ARCHITECTURE",
        "In our pipeline, we do not choose one dogmatically. We use <b>ETL for data quality</b> and <b>ELT for business analytics</b>:<br/>"
        "1. <b>The ETL Stage (Python):</b> We extract Excel records and run 8 deterministic validation rules in Python. We separate clean from rejected rows <i>before</i> touching the database. This guarantees that corrupt values (e.g., text prices) never reach PostgreSQL.<br/>"
        "2. <b>The ELT Stage (PostgreSQL SQL):</b> Once clean data sits in PostgreSQL staging, we use modular SQL views (<code>analytics.fact_sales</code>) to perform business classifications (sales vs. returns vs. cancellations, date truncations, aggregates). This leverages PostgreSQL's relational engine and indexing for fast set-based querying.",
        styles, "arch"
    ))
    story.append(Spacer(1, 10))

    story.append(Paragraph("1.3 Storage Formats: CSV vs. Parquet (Why Columnar Storage Matters)", styles["H2"]))
    story.append(Paragraph(
        "Why didn't we just save our processed data as a clean CSV file? Because CSV is a <b>row-oriented plain-text format</b>, while modern data analytics demands <b>columnar binary storage</b> like Apache Parquet.",
        styles["Body"]
    ))

    storage_table_data = [
        ["Feature", "Row-Oriented (CSV)", "Columnar Binary (Apache Parquet)"],
        ["Layout on Disk", "Stores complete rows sequentially: row1, row2, row3.", "Stores each column sequentially: all quantities together, all prices together."],
        ["Analytical Query", "To sum 1 column, the disk must read every single byte of every row.", "<b>Projection Pushdown:</b> Only reads the single requested column, skipping all others."],
        ["Compression", "Very low compression because adjacent values have mixed types.", "<b>High Compression (Snappy):</b> Adjacent values are identical types, achieving ~80% reduction."],
        ["Schema & Types", "No schema metadata. Everything is text; types must be re-inferred.", "Strict binary metadata embedded in the file footer (int64, float64, timestamp)."],
        ["Industry Role", "Good for human-readable audit logs (like rejected records).", "The standard storage format for Data Lakes, Snowflake, Databricks, and AWS/Azure."]
    ]
    t_storage = Table(storage_table_data, colWidths=[1.3 * inch, 2.9 * inch, 3.0 * inch])
    t_storage.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#2B6CB0")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E0")),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(t_storage)
    story.append(Spacer(1, 10))

    story.append(Paragraph("1.4 Relational Database vs. Data Lake: Why We Have Both", styles["H2"]))
    story.append(Paragraph(
        "A common point of confusion is: <i>'If we have Parquet files, why do we need PostgreSQL? And if we have PostgreSQL, why do we need Parquet?'</i><br/>"
        "In modern enterprise data platforms, this is known as a <b>Lakehouse Pattern</b>:<br/>"
        "• <b>The Data Lake (Parquet on Azure ADLS Gen2):</b> Acts as our durable, cheap, scalable object storage layer. It can hold historical snapshots, massive partitions, and can be queried directly by distributed compute engines (Spark, Synapse, Databricks) without paying database license fees.<br/>"
        "• <b>The Relational Warehouse (PostgreSQL):</b> Serves business intelligence analysts who need immediate sub-second SQL queries, ACID transaction guarantees, role-based access control, and foreign key relations for business dashboards.",
        styles["Body"]
    ))

    story.append(Paragraph("1.5 Database Drivers & Abstraction: SQLAlchemy vs. Psycopg 3", styles["H2"]))
    story.append(Paragraph(
        "Connecting Python to PostgreSQL requires two cooperating layers:<br/>"
        "1. <b>Psycopg 3 (The Driver):</b> This is the low-level library that speaks PostgreSQL's binary wire protocol over TCP network sockets. It handles socket connections, SSL handshakes, and query transmission.<br/>"
        "2. <b>SQLAlchemy (The Abstraction Layer):</b> A high-level SQL toolkit. You never want individual functions opening raw database connections because creating TCP connections is expensive. SQLAlchemy manages a <b>Connection Pool</b> (reusing pre-opened connections), abstracts dialect differences, handles automatic rollbacks on error, and builds safe connection URLs via <code>quote_plus</code>.",
        styles["Body"]
    ))
    story.append(PageBreak())

    # =========================================================================
    # PART II: WHAT THE PROJECT DOES — BUSINESS & DATA CONTEXT
    # =========================================================================
    story.append(Paragraph("PART II: Business Problem & Data Journey", styles["H1"]))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#CBD5E0"), spaceAfter=10))

    story.append(Paragraph("2.1 The Kaggle Online Retail II Dataset", styles["H2"]))
    story.append(Paragraph(
        "The project uses the real-world <b>Online Retail II</b> dataset from the UCI Machine Learning Repository. It contains <b>525,461 transaction line items</b> from an e-commerce gift retailer based in the United Kingdom, spanning two years (2009 to 2011).",
        styles["Body"]
    ))

    dataset_cols = [
        ["Column Name", "Raw Example", "Data Type", "Business Role & Meaning"],
        ["Invoice / InvoiceNo", "536365, C536379", "VARCHAR", "Order ID. Invoices starting with 'C' indicate an order cancellation."],
        ["StockCode", "85123A, POST", "VARCHAR", "Product SKU code. Includes service codes like POST (postage)."],
        ["Description", "WHITE HANGING HEART...", "TEXT", "Product name. Missing in ~2-3% of rows."],
        ["Quantity", "6, -1, 24", "BIGINT", "Units sold. Negative values represent customer returns/credit notes."],
        ["InvoiceDate", "2010-12-01 08:26:00", "TIMESTAMP", "Exact transaction timestamp."],
        ["Price / UnitPrice", "2.55, 0.0, -10.0", "FLOAT", "Unit price in GBP (£). Zero price is valid (free sample); negative is invalid."],
        ["Customer ID", "17850.0, NaN", "FLOAT / NULL", "Customer identifier. Missing in ~25% of rows due to guest checkout."],
        ["Country", "United Kingdom, France", "VARCHAR", "Country of the purchasing customer."]
    ]
    t_data = Table(dataset_cols, colWidths=[1.3 * inch, 1.4 * inch, 1.1 * inch, 3.4 * inch])
    t_data.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#2B6CB0")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E0")),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(t_data)
    story.append(Spacer(1, 10))

    story.append(Paragraph("2.2 Critical Business Rules & Logic Handled", styles["H2"]))
    story.append(Paragraph(
        "Many junior developers make naive mistakes with this dataset. Our pipeline implements strict, documented business rules:",
        styles["Body"]
    ))
    story.append(Paragraph("1. <b>Returns vs. Cancellations:</b> Invoices starting with 'C' are cancellations. Negative quantities on regular invoices are customer returns. Both are kept in the clean dataset! Why? Because returns and cancellations are real business events that reduce net revenue. If you reject them, you falsely inflate company profits.", styles["Bullet"]))
    story.append(Paragraph("2. <b>Guest Checkouts (Missing Customer IDs):</b> Over 25% of transactions have no Customer ID because customers checked out as guests. If you run <code>df.dropna()</code>, you eliminate 130,000+ sales and £2M+ in revenue. We preserve missing Customer IDs as database <code>NULL</code> values.", styles["Bullet"]))
    story.append(Paragraph("3. <b>Zero Price vs. Negative Price:</b> An item with <code>price = 0</code> is valid (a free promotional sample). An item with <code>price &lt; 0</code> is corrupt accounting data and is routed to the rejected dataset.", styles["Bullet"]))
    story.append(Paragraph("4. <b>Exact Duplicate Invoices:</b> A composite key of <code>(invoice, stockcode, invoicedate, quantity, price)</code> identifies accidental duplicate line entries. The first line is kept; duplicate copies are logged to the rejected CSV with reason <code>duplicate;</code>.", styles["Bullet"]))
    story.append(Paragraph("5. <b>Derived Line Amount:</b> Computed as: <code>line_amount = quantity * price</code>. Returns yield negative line amounts, which naturally subtract from gross sales when summed.", styles["Bullet"]))

    story.append(Spacer(1, 6))
    story.append(create_callout_box(
        "THE 100% RECONCILIATION INVARIANT",
        "A senior data engineering principle enforced in our pipeline is the mathematical reconciliation invariant:<br/>"
        "<b>Total Source Input Rows = Clean Output Rows + Rejected Output Rows</b><br/>"
        "If 1,010 rows enter the pipeline, and 1,000 pass while 10 are rejected, the pipeline verifies <code>1,010 == 1,000 + 10</code>. If a single row is dropped silently, the pipeline logs an integrity warning. This ensures total auditability for compliance.",
        styles, "important"
    ))
    story.append(PageBreak())

    # =========================================================================
    # PART III: HOW IT WAS BUILT MANUALLY — CODE WALKTHROUGH
    # =========================================================================
    story.append(Paragraph("PART III: Step-by-Step Code Walkthrough", styles["H1"]))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#CBD5E0"), spaceAfter=10))

    story.append(Paragraph("3.1 Module 1: Centralized Configuration (src/config.py)", styles["H2"]))
    story.append(Paragraph(
        "<b>Why it exists:</b> Hardcoding file paths or database passwords inside pipeline scripts causes security leaks and environment fragility. <code>config.py</code> is the single source of truth for the entire application.",
        styles["Body"]
    ))
    story.append(Paragraph(
        "<b>Key Code Structure & Decisions:</b><br/>"
        "• <code>PROJECT_ROOT = Path(__file__).resolve().parent.parent</code> dynamically detects the root directory, so the script works no matter which terminal folder you run it from.<br/>"
        "• <code>urllib.parse.quote_plus</code> is wrapped around the database password. This prevents special characters like <code>@</code> or <code>#</code> from corrupting the SQLAlchemy connection URL.<br/>"
        "• <code>__repr__</code> masks passwords: <code>password='***'</code>, so printing the config never leaks credentials in logs.",
        styles["Body"]
    ))
    story.append(create_code_block("""# src/config.py snippet
def get_connection_url(self, db_name: str | None = None) -> str:
    target_db = db_name or self.name
    # quote_plus safely encodes passwords with special characters (@, #, %)
    pw_encoded = quote_plus(self._password)
    return f"postgresql+psycopg://{self.user}:{pw_encoded}@{self.host}:{self.port}/{target_db}"

def __repr__(self) -> str:
    # Zero-secret leakage: password masked in logs
    return f"DatabaseConfig(host={self.host!r}, port={self.port}, db={self.name!r}, user={self.user!r}, password='***')"
""", styles))
    story.append(Spacer(1, 10))

    story.append(Paragraph("3.2 Module 2: Ingestion & Extraction (src/etl.py)", styles["H2"]))
    story.append(Paragraph(
        "<b>Why it exists:</b> The raw Kaggle file contains multiple sheets (<code>Year 2009-2010</code> and <code>Year 2010-2011</code>). Reading 500K rows twice or loading the wrong sheet breaks the pipeline.",
        styles["Body"]
    ))
    story.append(Paragraph(
        "<b>Key Code Structure & Decisions:</b><br/>"
        "• <code>inspect_workbook(path)</code> uses <code>openpyxl.load_workbook(..., read_only=True)</code> to read only sheet metadata in milliseconds without parsing any rows.<br/>"
        "• <code>_read_sheet()</code> uses <code>dtype=object</code> to prevent Pandas from coercing numbers prematurely.<br/>"
        "• Adds <code>df['_sheet_source'] = sheet_name</code> to every sheet before concatenation to maintain full data lineage.",
        styles["Body"]
    ))
    story.append(create_code_block("""# src/etl.py snippet
def extract(source_path: Path) -> ExtractResult:
    sheet_names = inspect_workbook(source_path)  # openpyxl read_only inspection
    raw_frames = []
    for sheet in sheet_names:
        df_raw = _read_sheet(source_path, sheet)
        df_norm = normalize_headers(df_raw)
        df_norm["_sheet_source"] = sheet  # Data Lineage Tracking
        raw_frames.append(df_norm)
    combined = pd.concat(raw_frames, ignore_index=True, sort=False)
    return ExtractResult(df=combined, source_row_count=len(combined), sheets_loaded=sheet_names)
""", styles))
    story.append(Spacer(1, 10))

    story.append(Paragraph("3.3 Module 3: Validation & Quality Gate (src/validation.py)", styles["H2"]))
    story.append(Paragraph(
        "<b>Why it exists:</b> This is the heart of the ETL layer. It separates clean from rejected records using 8 business validation rules.",
        styles["Body"]
    ))
    story.append(Paragraph(
        "<b>Key Code Structure & Decisions:</b><br/>"
        "• <code>flag_missing_required()</code> flags records where <code>invoice</code>, <code>stockcode</code>, <code>quantity</code>, <code>price</code>, or <code>invoicedate</code> are null or blank.<br/>"
        "• <code>flag_non_numeric()</code> attempts numeric coercion with <code>errors='coerce'</code>. Any value that was present but becomes NaN is tagged as <code>non_numeric_price;</code>.<br/>"
        "• <code>flag_duplicates()</code> evaluates <code>(invoice, stockcode, invoicedate, quantity, price)</code> to identify duplicate transactions.<br/>"
        "• Automatically tags cancellations: <code>df['is_cancellation'] = df['invoice'].str.startswith('C')</code>.<br/>"
        "• Calculates: <code>df['line_amount'] = df['quantity'] * df['price']</code>.",
        styles["Body"]
    ))
    story.append(create_code_block("""# src/validation.py snippet
# Composite key deduplication
dup_mask = df.duplicated(subset=['invoice', 'stockcode', 'invoicedate', 'quantity', 'price'], keep="first")
dup_df = df[dup_mask].copy()
dup_df['rejection_reason'] = "duplicate; "

# Derived cancellation flag and financial line amount
passing['is_cancellation'] = passing['invoice'].astype(str).str.strip().str.upper().str.startswith("C")
passing['line_amount'] = passing['quantity'] * passing['price']
""", styles))
    story.append(PageBreak())

    story.append(Paragraph("3.4 Module 4: Parquet Lakehouse Storage (src/transform.py)", styles["H2"]))
    story.append(Paragraph(
        "<b>Why it exists:</b> Converts the clean validated DataFrame into an optimized, binary, typed Apache Parquet file for downstream analytical processing.",
        styles["Body"]
    ))
    story.append(Paragraph(
        "<b>Key Code Structure & Decisions:</b><br/>"
        "• Explicit PyArrow Schema: Defines exact data types (<code>string</code>, <code>int64</code>, <code>timestamp[us]</code>, <code>float64</code>) to prevent schema drift.<br/>"
        "• <code>pq.write_table(..., compression='snappy', row_group_size=100_000)</code> writes columnar row groups of 100K rows for optimal disk I/O.<br/>"
        "• <code>write_rejected_csv()</code> uses <code>encoding='utf-8-sig'</code>. The Byte Order Mark (BOM) ensures that business users opening the rejected file in Microsoft Excel on Windows do not see garbled characters.<br/>"
        "• <code>verify_parquet_roundtrip()</code> immediately reads the Parquet file back and verifies row counts and column parity.",
        styles["Body"]
    ))
    story.append(create_code_block("""# src/transform.py snippet
table = pa.Table.from_pandas(df, preserve_index=False)
pq.write_table(
    table, str(output_path),
    compression="snappy",        # Fast compression with ~80% size reduction
    row_group_size=100_000,      # 100K-row groups for efficient projection scans
    write_statistics=True,
)
# Automated roundtrip verification
assert verify_parquet_roundtrip(df, output_path) == True
""", styles))
    story.append(Spacer(1, 10))

    story.append(Paragraph("3.5 Module 5: PostgreSQL Loading (src/load_postgres.py)", styles["H2"]))
    story.append(Paragraph(
        "<b>Why it exists:</b> Loads the clean Parquet records into relational PostgreSQL staging tables while managing connections safely.",
        styles["Body"]
    ))
    story.append(Paragraph(
        "<b>Key Code Structure & Decisions:</b><br/>"
        "• <code>create_database_if_missing()</code> connects to the default <code>postgres</code> administrative database with <code>AUTOCOMMIT</code> isolation to check if <code>retail_dw</code> exists. If missing, it creates the database automatically.<br/>"
        "• <code>load_staging()</code> uses <code>df.to_sql(..., method='multi', chunksize=5000)</code>. Instead of inserting 500K individual rows or one massive query that crashes RAM, it batches records into 5,000-row chunks.<br/>"
        "• Uses <code>if_exists='replace'</code> to provide an **idempotent full-refresh staging strategy**.",
        styles["Body"]
    ))
    story.append(create_code_block("""# src/load_postgres.py snippet
df.to_sql(
    name="stg_transactions",
    schema="staging",
    con=engine,
    if_exists="replace",     # Idempotent: dropping and reloading guarantees exact state
    index=False,
    chunksize=5000,          # 5K-row chunks to prevent database timeouts & OOM
    method="multi",          # Batches multi-row INSERT statements
)
""", styles))
    story.append(Spacer(1, 10))

    story.append(Paragraph("3.6 Module 6: SQL Analytics & Views (sql/)", styles["H2"]))
    story.append(Paragraph(
        "<b>Why it exists:</b> The database layer performs the ELT business transformations using modular SQL views.",
        styles["Body"]
    ))
    story.append(Paragraph("• <b>sql/01_create_schema.sql:</b> Creates separate <code>staging</code> (ETL landing) and <code>analytics</code> (business layer) schemas.", styles["Bullet"]))
    story.append(Paragraph("• <b>sql/02_create_staging.sql:</b> Adds B-tree performance indexes on <code>invoicedate</code>, <code>customerid</code>, <code>country</code>, and <code>is_cancellation</code>.", styles["Bullet"]))
    story.append(Paragraph("• <b>sql/03_transform_sales.sql:</b> Builds <code>analytics.fact_sales</code>, classifying transaction types (<code>'sale'</code>, <code>'return'</code>, <code>'cancellation'</code>, <code>'free_item'</code>) and extracting year, month, and day-of-week.", styles["Bullet"]))
    story.append(Paragraph("• <b>sql/04_analytics_views.sql:</b> Builds 5 business KPI views: Daily Net Sales, Monthly Trends (AOV), Top Products by Revenue, Country Sales, and Return Analysis.", styles["Bullet"]))
    story.append(Paragraph("• <b>sql/05_quality_checks.sql:</b> Runs automated post-load SQL assertions verifying row counts, checking for null values, and proving <code>line_amount = quantity * price</code>.", styles["Bullet"]))
    story.append(PageBreak())

    story.append(Paragraph("3.7 Module 7: Orchestrator & CLI (src/run_pipeline.py)", styles["H2"]))
    story.append(Paragraph(
        "<b>Why it exists:</b> Coordinates all pipeline stages in sequence, parses CLI arguments (<code>--local-only</code>, <code>--create-db</code>, <code>--upload-azure</code>), logs execution, and writes immutable audit records to <code>logs/audit_runs.jsonl</code>.",
        styles["Body"]
    ))
    story.append(create_code_block("""# Run the pipeline from terminal:
python -m src.run_pipeline --local-only

# Sample audit record written to logs/audit_runs.jsonl:
{
  "run_id": "3588b8ce",
  "start_time": "2026-10-25T14:25:09Z",
  "end_time": "2026-10-25T14:25:11Z",
  "source_row_count": 1010,
  "clean_row_count": 1000,
  "rejected_row_count": 10,
  "duplicate_count": 2,
  "status": "SUCCESS",
  "local_only": true
}
""", styles))
    story.append(Spacer(1, 10))

    story.append(Paragraph("3.8 Module 8: Optional Cloud Lakehouse Upload (src/azure_upload.py)", styles["H2"]))
    story.append(Paragraph(
        "<b>Why it exists:</b> Uploads processed Parquet and rejected CSV files to Microsoft Azure Data Lake Storage Gen2 (ADLS Gen2). Uses dynamic imports so local development works 100% offline without failing if Azure packages or credentials are missing.",
        styles["Body"]
    ))
    story.append(Spacer(1, 10))

    story.append(Paragraph("3.9 Automated Testing Suite (tests/)", styles["H2"]))
    story.append(Paragraph(
        "Our test suite contains <b>89 automated tests</b> across 5 modules that execute in under 3 seconds using pytest. We test using small synthetic DataFrames (mock data) so developers can verify code changes without downloading 500K rows or running PostgreSQL:",
        styles["Body"]
    ))
    story.append(Paragraph("• <code>test_validation.py</code> (40+ tests): Asserts header mapping, missing invoice rejection, negative price rejection, return preservation, and reconciliation invariant.", styles["Bullet"]))
    story.append(Paragraph("• <code>test_transform.py</code>: Verifies Parquet read/write roundtrip, idempotency of overwrites, and CSV writing.", styles["Bullet"]))
    story.append(Paragraph("• <code>test_config.py</code>: Tests URL encoding, missing password errors, and password masking.", styles["Bullet"]))
    story.append(Paragraph("• <code>test_azure.py</code>: Tests graceful skipping when Azure credentials are not present.", styles["Bullet"]))
    story.append(Paragraph("• <code>test_etl.py</code>: Tests multi-sheet discovery, missing file errors, and schema compatibility.", styles["Bullet"]))
    story.append(PageBreak())

    # =========================================================================
    # PART IV: WHY IT WAS BUILT THAT WAY — TRADE-OFFS & FAILURE MODES
    # =========================================================================
    story.append(Paragraph("PART IV: Architectural Trade-Offs & Decisions", styles["H1"]))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#CBD5E0"), spaceAfter=10))

    decisions_data = [
        ["Architectural Decision", "What We Chose", "What We Rejected & Why"],
        ["Processing Engine", "Python 3 + Pandas + PyArrow", "<b>Rejected Apache Spark / PySpark:</b> The dataset is ~525K rows (~100MB). Spark has significant JVM overhead and cluster costs. Using Spark for 100MB is over-engineering; Pandas with PyArrow is 10x faster and runs on any local machine."],
        ["Pipeline Strategy", "Idempotent Full Refresh", "<b>Rejected Complex Streaming / CDC:</b> Retail transaction logs arrive in daily/weekly batches. A full-refresh staging pattern with transactional replacement eliminates orphan records and synchronization bugs."],
        ["Data Lake File Format", "Apache Parquet (Snappy)", "<b>Rejected Raw CSV / JSON:</b> CSV has no type safety and takes 80MB. Parquet takes 17MB, embeds schemas, and enables projection pushdown."],
        ["Database Staging Load", "SQLAlchemy Multi-Insert (Chunksize=5000)", "<b>Rejected Single-row INSERT / Massive Bulk Load:</b> Single-row inserts are too slow (hours for 500K rows). Single massive inserts trigger database socket timeouts and OOM errors. 5K chunks balance throughput and RAM."],
        ["SQL Analytics Layer", "Modular SQL Database Views", "<b>Rejected Python Aggregations:</b> Computing AOV and monthly trends in SQL views allows BI tools (Tableau, Power BI, Metabase) to query PostgreSQL directly with real-time updates."],
        ["Error Handling Strategy", "Rejection Routing (Input = Clean + Rejected)", "<b>Rejected Silent df.dropna():</b> Dropping bad rows silently destroys data lineage and accounting trust. Writing rejected rows to CSV allows business users to audit why an order failed."]
    ]
    t_decisions = Table(decisions_data, colWidths=[1.4 * inch, 2.3 * inch, 3.5 * inch])
    t_decisions.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#2B6CB0")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E0")),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(t_decisions)
    story.append(Spacer(1, 14))

    story.append(Paragraph("4.2 Failure Modes & How the Pipeline Recovers", styles["H2"]))
    story.append(Paragraph("• <b>PostgreSQL Offline / Refused:</b> The pipeline has a <code>--local-only</code> flag. If PostgreSQL is stopped, it processes data, writes Parquet and rejected CSV files, and computes analytics from Parquet without crashing.", styles["Bullet"]))
    story.append(Paragraph("• <b>Corrupt / Password Failure:</b> <code>config.py</code> validates environment variables at startup and catches auth errors with friendly instructions pointing to troubleshooting guides.", styles["Bullet"]))
    story.append(Paragraph("• <b>Schema Drift (New Column Names):</b> <code>normalize_headers()</code> handles case differences (<code>InvoiceNo</code>, <code>invoiceno</code>, <code>Invoice</code>), strips spaces, and aliases common column names.", styles["Bullet"]))
    story.append(Paragraph("• <b>Special Characters in Password:</b> <code>quote_plus()</code> ensures passwords containing <code>@</code>, <code>#</code>, <code>%</code>, or <code>/</code> do not corrupt the SQLAlchemy connection URL.", styles["Bullet"]))
    story.append(PageBreak())

    # =========================================================================
    # PART V: INTERVIEW MASTERCLASS & SPOKEN DEFENSE
    # =========================================================================
    story.append(Paragraph("PART V: Interview Masterclass & Spoken Defense", styles["H1"]))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#CBD5E0"), spaceAfter=10))

    story.append(Paragraph("5.1 Spoken Elevator Pitches (Practice Out Loud)", styles["H2"]))

    story.append(create_callout_box(
        "THE 30-SECOND PITCH (FOR SCREENING CALLS)",
        "<i>'I built an end-to-end retail data engineering pipeline in Python and PostgreSQL that processes over 525,000 real-world e-commerce transactions. The pipeline extracts multi-sheet Excel data, enforces 8 automated data quality checks, and stores clean data in a Snappy-compressed Parquet lakehouse format, saving 80% storage space. It then batch-loads clean records into an indexed PostgreSQL staging warehouse, where modular SQL views calculate daily sales, return rates, and product rankings. The entire pipeline is idempotent, covered by 89 automated pytest tests, and includes optional Azure ADLS Gen2 cloud synchronization.'</i>",
        styles, "tip"
    ))
    story.append(Spacer(1, 10))

    story.append(create_callout_box(
        "THE 90-SECOND TECHNICAL PITCH (FOR TECHNICAL ROUNDS)",
        "<i>'In e-commerce datasets, raw transaction logs are messy—they contain duplicate orders, cancelled invoices, negative quantities, and missing customer IDs from guest checkouts. If loaded blindly, financial revenue metrics get distorted.<br/>"
        "To solve this, I designed a hybrid ETL/ELT architecture:<br/>"
        "1. In the ETL layer, Python and Pandas inspect the Excel workbook metadata using openpyxl, normalize column headers, and enforce 8 business validation rules. We separate clean from invalid records, routing rejected records to an audited CSV with explicit error tags to guarantee our reconciliation invariant: Input = Clean + Rejected.<br/>"
        "2. For the Data Lake layer, clean records are cast to explicit PyArrow types and written to columnar Parquet with Snappy compression, enabling projection pushdown.<br/>"
        "3. For the Warehouse layer, data is chunk-loaded into PostgreSQL staging using SQLAlchemy and Psycopg 3. Downstream SQL views classify records into sales, returns, and cancellations, computing key metrics like Net Sales and Average Order Value.<br/>"
        "The project is production-hardened with zero-secret logging, automated audit tracking in JSONL, and 89 automated unit tests running in under 3 seconds.'</i>",
        styles, "arch"
    ))
    story.append(Spacer(1, 10))

    story.append(Paragraph("5.2 Top 5 Tough Interview Questions & How to Answer", styles["H2"]))

    qa_list = [
        ("Q1: Why did you keep negative quantities in the clean dataset?",
         "Because in retail accounting, negative quantities represent legitimate customer returns or credit notes. If an invoice starts with 'C', it is an order cancellation; if a normal invoice has a negative quantity, it is a return. If you automatically reject negative quantities, you overstate company sales. In my pipeline, they are preserved and flagged with `is_cancellation` so SQL views subtract returns from gross sales to calculate true Net Revenue."),

        ("Q2: How did you handle the 25% missing Customer IDs?",
         "About 25% of rows had no Customer ID because online customers frequently check out as guests. Dropping these rows with `dropna()` would destroy 25% of sales volume. I classified `customerid` as an optional field, storing it as database `NULL`. When calculating customer-specific metrics like Customer Lifetime Value (CLV), queries filter `WHERE customerid IS NOT NULL`, while total revenue queries include all transactions."),

        ("Q3: What does idempotency mean in your pipeline?",
         "Idempotency means running the pipeline multiple times on the same input yields the exact same state without duplicating records. Parquet files are written with atomic overwrite semantics. In PostgreSQL staging, we use a transactional full-refresh strategy (`if_exists='replace'` in chunked batches). Downstream SQL transformations are implemented as database VIEWs (`CREATE OR REPLACE VIEW`), so they always compute dynamically over staging data."),

        ("Q4: Why Parquet instead of CSV for clean data?",
         "Parquet is a columnar binary format with Snappy compression. A 500K-row dataset takes ~18MB in Parquet versus ~85MB in CSV (~80% reduction). More importantly, Parquet enables projection pushdown: analytical queries like `SELECT SUM(line_amount) FROM sales` only read that single column from disk, skipping all other columns. It is also the native standard for cloud tools like Databricks and Azure Synapse."),

        ("Q5: Why did you write 89 automated tests for a small project?",
         "Automated testing separates amateur scripts from professional software engineering. In real data engineering, pipelines process critical financial data. A bug in date parsing or duplicate handling can silently miscalculate revenue. My 89 unit tests use small synthetic DataFrames to verify edge cases (negative prices, missing invoices, cancellations, date formats, roundtrip I/O) in under 3 seconds without needing a live database.")
    ]

    for q, a in qa_list:
        story.append(Paragraph(f"<b>{q}</b>", styles["H3"]))
        story.append(Paragraph(a, styles["Body"]))
        story.append(Spacer(1, 4))

    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"Successfully generated Master Guide PDF at: {OUTPUT_PDF}")


if __name__ == "__main__":
    build_pdf()
