"""Scope of the monitor: an explicit allow-list of 13 core reports (owner decision, Nov 2026).

Every other publication is registered as metadata only (status out_of_scope, or phase2 for the reports planned next).
`ingest` says how much of a family is read: latest = the newest edition only (the file embeds its history),
all_2026 = every 2026 edition (the report has fewer than 8 periods in its latest file).
Wholesale prices and the non-oil trade editions are details of Prices and Trade, never cards of their own.
"""
import re

CORE = [
    # id, Arabic name, group, frequency, title regex (English title), exclude regex, ingest policy
    dict(id="cpi", prefix="consumer-price-index", name_ar="الرقم القياسي لأسعار المستهلك", group="prices", freq="monthly", rx=r"^Consumer Price Index", ingest="latest"),
    dict(id="ppi", prefix="producer-price-index-for", name_ar="الرقم القياسي لأسعار المنتجين", group="prices", freq="monthly", rx=r"^Producer Price Index", ingest="latest"),
    dict(id="avgprices", prefix="average-service-prices-for", name_ar="متوسطات أسعار السلع والخدمات", group="prices", freq="monthly", rx=r"^Average (service )?prices", ingest="all_2026"),
    dict(id="rei", prefix="real-estate-price-index", name_ar="الرقم القياسي لأسعار العقارات", group="prices", freq="quarterly", rx=r"^Real Estate Price Index", ingest="latest"),
    dict(id="gdp_flash", prefix="gdp-flash", name_ar="التقديرات السريعة للناتج المحلي", group="growth", freq="quarterly", rx=r"^GDP\s*-\s*Flash", ingest="latest"),
    dict(id="gdp_na", prefix="gdp-national-accounts", name_ar="الناتج المحلي والحسابات القومية", group="growth", freq="quarterly", rx=r"^GDP and National Accounts", ingest="latest"),
    dict(id="ipi", prefix="industrial-production-index-1", name_ar="الرقم القياسي للإنتاج الصناعي", group="growth", freq="monthly", rx=r"^Industrial Production Index", ingest="latest"),
    dict(id="trade", prefix="international-trade-in-goods", name_ar="التجارة الدولية للسلع", group="trade", freq="monthly", rx=r"^International Trade in Goods", ingest="latest"),
    dict(id="fdi", prefix="foreign-direct-investment", name_ar="الاستثمار الأجنبي المباشر", group="trade", freq="quarterly", rx=r"^Foreign Direct Investment", ingest="latest"),
    dict(id="labor", prefix="labor-market-statistics", name_ar="إحصاءات سوق العمل", group="labour", freq="quarterly", rx=r"^Labou?r Market Statistics", ingest="latest"),
    dict(id="bci", prefix="business-confidence-index-for", name_ar="مؤشر ثقة الأعمال", group="confidence", freq="monthly", rx=r"^Business Confidence Index", ingest="latest"),
    dict(id="cci", prefix="consumer-confidence-index", name_ar="مؤشر ثقة المستهلك", group="confidence", freq="quarterly", rx=r"^Consumer Confidence Index", ingest="latest"),
    dict(id="tourism", prefix="tourism-establishments", name_ar="إحصاءات منشآت السياحة", group="tourism", freq="quarterly", rx=r"^Tourism Establishments Statistics", ingest="latest"),
]
DETAIL = [dict(id="nonoil", prefix="non-oil-trade", name_ar="التجارة غير النفطية", parent="trade", freq="monthly", rx=r"^Non oil International trade in goods", ingest="latest"),
          dict(id="wpi", prefix="wholesale-price-index", name_ar="الرقم القياسي لأسعار الجملة", parent="ppi", freq="monthly", rx=r"^Wholesale Price Index", ingest="latest")]
PHASE2 = [r"^Register-based Labou?r", r"^Wholesale and Retail Trade", r"^International Trade in Services", r"^Umrah"]


def dataset_prefix(p):
    """Stable dataset-id prefix of a publication's family, so every edition lands in the same datasets."""
    f = family(p)
    return f["prefix"] if f else None


def family(p):
    """Return the CORE or DETAIL entry a publication belongs to, or None."""
    t = p.get("title_en", "")
    for f in CORE + DETAIL:
        if re.search(f["rx"], t, re.I) and p.get("frequency") == f["freq"]:
            return f
    return None


def in_scope(p):
    return family(p) is not None


def classify(p):
    """Scope status for the register: core/detail -> None (normal flow); phase2 or out_of_scope otherwise."""
    if family(p):
        return None
    t = p.get("title_en", "")
    return "phase2" if any(re.search(x, t, re.I) for x in PHASE2) else "out_of_scope"
