# -*- coding: utf-8 -*-
"""
vocab.py — 共享受控词表与权威期刊清单
被 fetch_papers.py（打标签）与 build_data.py（统计/关系图）共同引用
"""

# ---------------------------------------------------------------------------
# 权威期刊清单（WoS/JCR Q1 收录的本领域主流期刊，用于 quality 标记）
# ---------------------------------------------------------------------------
CORE_JOURNALS = {
    # Nature / Science 家族
    "nature", "nature communications", "nature materials",
    "nature nanotechnology", "nature energy", "nature reviews materials",
    "science", "proceedings of the national academy of sciences of the united states of america",
    # Cell 家族
    "joule", "matter", "chem", "cell reports physical science",
    # Wiley
    "advanced materials", "advanced energy materials", "advanced functional materials",
    "advanced science", "small", "small methods", "small structures",
    "angewandte chemie international edition", "energy & environmental materials",
    "carbon energy", "infomat", "susmat", "batteries & supercaps",
    # ACS
    "acs nano", "nano letters", "journal of the american chemical society",
    "acs energy letters", "acs applied materials & interfaces",
    "acs applied energy materials", "chemical reviews",
    "accounts of chemical research", "chemistry of materials",
    # RSC
    "energy & environmental science", "journal of materials chemistry a",
    "chemical society reviews", "materials horizons", "nanoscale",
    "green chemistry",
    # Elsevier
    "carbon", "journal of power sources", "electrochimica acta",
    "energy storage materials", "nano energy", "chemical engineering journal",
    "materials today", "journal of energy storage", "journal of energy chemistry",
    "progress in materials science", "renewable and sustainable energy reviews",
    "materials today energy", "journal of colloid and interface science",
    "composites part b: engineering",
    # Springer / 其他
    "nano-micro letters", "nano research", "science china materials",
    "advanced composites and hybrid materials", "electrochemical energy reviews",
    "escience", "journal of materials science & technology",
}

# ---------------------------------------------------------------------------
# 受控词表：用于给论文打标签（论文关系图 / 筛选器 / 统计的基础）
# 元组: (标签中文名, 类别, [匹配正则列表])
# 类别: material 材料 / strategy 构建策略 / metric 性能指标 / application 应用
# ---------------------------------------------------------------------------
VOCAB = [
    # ---- 材料 ----
    ("活性炭 AC", "material", [r"\bactivated\s+carbons?\b", r"\bAC\s+electrode", r"activated\s+AC"]),
    ("碳纳米管 CNT", "material", [r"carbon\s+nanotubes?", r"\bCNTs?\b", r"\bSWCNT", r"\bMWCNT"]),
    ("石墨烯", "material", [r"\bgraphene\b", r"graphene\s+(?:nanosheets?|films?|foam|hydrogel|aerogel)"]),
    ("氧化石墨烯 GO/rGO", "material", [r"graphene\s+oxide", r"\brGO\b", r"\bGO\s+nanosheet", r"reduced\s+graphene"]),
    ("碳气凝胶", "material", [r"carbon\s+aerogels?", r"graphene\s+aerogels?", r"carbon\s+cryogel"]),
    ("多孔碳", "material", [r"porous\s+carbons?", r"mesoporous\s+carbon", r"microporous\s+carbon", r"hierarchical\s+porous"]),
    ("生物质碳", "material", [r"biomass[\- ]derived", r"biomass\s+carbons?"]),
    ("碳纤维/织物", "material", [r"carbon\s+(?:fibers?|fibres?|fabrics?|cloth|textile)", r"\bCNF\b", r"carbon\s+nanofiber"]),
    ("泡沫碳", "material", [r"carbon\s+foams?", r"graphene\s+foams?"]),
    ("碳化物衍生碳 CDC", "material", [r"carbide[\- ]derived"]),
    ("MXene 复合", "material", [r"\bMXene", r"\bTi3C2"]),
    ("MOF 衍生碳", "material", [r"metal[\- ]organic\s+framework", r"\bZIF[\- ]?8", r"\bMOF[\- ]derived", r"\bMOFs\b"]),
    ("炭黑 CB", "material", [r"carbon\s+black"]),
    ("碳点", "material", [r"carbon\s+(?:dots|quantum\s+dots)"]),
    # ---- 构建策略 ----
    ("CVD 生长", "strategy", [r"chemical\s+vapor\s+deposition", r"\bCVD\b"]),
    ("模板法", "strategy", [r"templat(?:e|ing|ed)", r"sacrificial\s+template"]),
    ("自组装", "strategy", [r"self[\- ]assembl"]),
    ("水热/溶剂热", "strategy", [r"hydrothermal", r"solvothermal"]),
    ("冷冻干燥/冰模板", "strategy", [r"freeze[\- ]dry", r"ice[\- ]template", r"ice\s+templat"]),
    ("静电纺丝", "strategy", [r"electrospinn"]),
    ("3D 打印", "strategy", [r"3D\s+print", r"direct\s+ink\s+writing", r"\bDIW\b"]),
    ("化学活化", "strategy", [r"\bKOH\b", r"chemical\s+activation", r"activator"]),
    ("碳化", "strategy", [r"carboniz", r"pyrolysi"]),
    ("激光加工", "strategy", [r"laser[\- ]induced", r"laser\s+scribing"]),
    ("焊接/交联", "strategy", [r"welding", r"soldering", r"cross[\- ]link"]),
    ("杂原子掺杂", "strategy", [r"nitrogen[\- ]doped", r"\bN[\- ]doped", r"heteroatom[\- ]doped", r"doping"]),
    # ---- 性能指标 ----
    ("比电容", "metric", [r"specific\s+capacitance", r"gravimetric\s+capacitance", r"F\s*g[−\-]?1", r"F/g"]),
    ("能量密度", "metric", [r"energy\s+density"]),
    ("功率密度", "metric", [r"power\s+density"]),
    ("倍率性能", "metric", [r"rate\s+(?:performance|capability|ability)"]),
    ("循环稳定性", "metric", [r"cycling\s+stability", r"cycle\s+life", r"capacitance\s+retention", r"cycle\s+performance"]),
    ("面电容", "metric", [r"areal\s+capacitance", r"F\s*cm[−\-]?2", r"mF\s*cm[−\-]?2"]),
    # ---- 应用 ----
    ("柔性器件", "application", [r"flexible"]),
    ("可穿戴", "application", [r"wearable"]),
    ("微型超级电容器 MSC", "application", [r"micro[\- ]supercapacitor", r"\bMSC\b"]),
    ("纤维状器件", "application", [r"fiber[\- ]shaped", r"yarn[\- ]shaped", r"fibre[\- ]shaped"]),
    ("固态电解质", "application", [r"solid[\- ]state"]),
    ("非对称器件", "application", [r"asymmetric"]),
]

# 各类别的展示颜色（对应 dataviz 参考调色板槽位）
CATEGORY_COLORS = {
    "material": 0,     # blue
    "strategy": 1,     # orange
    "application": 2,  # aqua
    "metric": 4,       # magenta
}
