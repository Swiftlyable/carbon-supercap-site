# -*- coding: utf-8 -*-
"""
classics.py — 领域经典文献清单（专家整理）
============================================================
- match:  论文标题中必然出现的特征子串（用于 OpenAlex 检索与校验）
- author: 第一作者姓氏（校验用）
- year:   发表年份（校验允许 ±1）
- note:   中文点评（对三维导电网络领域的意义）
由 fetch_papers.py 检索匹配后写入 papers.json（classic=true），
并生成 data/classics.json 供首页「经典文献」栏目使用。
"""

CLASSICS = [
    # ---- 奠基与机理 ----
    {
        "match": "materials for electrochemical capacitors",
        "author": "Simon", "year": 2008,
        "note": "奠基综述：系统阐述电容储能材料与机理，碳材料孔径-离子匹配关系成为后续导电网络设计的理论起点。",
    },
    {
        "match": "true performance metrics in electrochemical energy storage",
        "author": "Gogotsi", "year": 2011,
        "note": "提出器件级性能基准与 Ragone 图使用的经典警告，指导本领域以面电容/体积电容而非单一 F/g 评价电极。",
    },
    {
        "match": "carbons and electrolytes for advanced supercapacitors",
        "author": "Béguin", "year": 2014,
        "note": "碳/电解液匹配综述：孔径与离子尺寸、溶剂化效应的系统梳理，是孔结构工程与导电网络协同设计的依据。",
    },
    {
        "match": "carbon-based materials as supercapacitor electrodes",
        "author": "Zhang", "year": 2009,
        "note": "碳基超级电容器电极材料经典综述：活性炭/CNT/石墨烯三大体系性能边界与改性路线的全面比较。",
    },
    {
        "match": "nanostructures from 0 to 3 dimensions",
        "author": "Yu", "year": 2015,
        "note": "0D–3D 纳米结构超级电容器电极综述：维度-性能关联的经典总结，本网站「维度工程」知识框架的来源之一。",
    },
    # ---- 石墨烯 3D 化里程碑 ----
    {
        "match": "produced by activation of graphene",
        "author": "Zhu", "year": 2011,
        "note": "KOH 活化微波剥离石墨烯：比表面约 3100 m²/g 且保持导电骨架，活化造孔与导电网络结合的标志性工作。",
    },
    {
        "match": "self-assembled graphene hydrogel via a one-step hydrothermal process",
        "author": "Xu", "year": 2010,
        "note": "水热自组装一步制备石墨烯 3D 水凝胶，开创了自组装策略构建三维石墨烯网络的主流路线。",
    },
    {
        "match": "three-dimensional flexible and conductive interconnected graphene networks grown by chemical vapour deposition",
        "author": "Chen", "year": 2011,
        "note": "CVD 在镍泡沫上生长 3D 互联石墨烯网络——3D 导电网络的里程碑：共价互联的连续电子通道首次被完整演示。",
    },
    {
        "match": "liquid-mediated dense integration of graphene materials",
        "author": "Yang", "year": 2013,
        "note": "液相致密化集成石墨烯：兼顾密度与导电网络的高体积性能电极，回应了 3D 多孔网络振实密度低的工程矛盾。",
    },
    {
        "match": "laser scribing of high-performance and flexible graphene-based electrochemical capacitors",
        "author": "El-Kady", "year": 2012,
        "note": "激光直写还原 GO 制备图案化 3D 石墨烯电极，无粘结剂、柔性、可规模化的器件范式。",
    },
    {
        "match": "graphene-based supercapacitor with an ultrahigh energy density",
        "author": "Liu", "year": 2010,
        "note": "曲面化 rGO 抑制片层堆叠，能量密度约 85 Wh/kg 的早期实证，3D 化抑制 π-π 堆叠理念的代表。",
    },
    {
        "match": "graphene double-layer capacitor with ac line-filtering performance",
        "author": "Miller", "year": 2010,
        "note": "垂直取向石墨烯电极实现 120 Hz 交流滤波——证明高取向导电网络对功率特性的极限意义。",
    },
    # ---- 碳纳米管网络 ----
    {
        "match": "high power electrochemical capacitors based on carbon nanotube electrodes",
        "author": "Niu", "year": 1997,
        "note": "CNT 超级电容器开山之作：一维导电网络电极的起源，渗透网络概念的早期实践。",
    },
    {
        "match": "shape-engineerable and highly densely packed single-walled carbon nanotubes",
        "author": "Futaba", "year": 2006,
        "note": "致密自支撑 SWCNT 电极：1D 网络高密度工程的经典，为后续 CNT 网络设计提供结构模板。",
    },
    {
        "match": "printable thin film supercapacitors using single-walled carbon nanotubes",
        "author": "Kaempgen", "year": 2009,
        "note": "可印刷 CNT 薄膜超级电容器：1D 网络柔性化与器件集成的早期代表。",
    },
    # ---- 气凝胶 / 弹性网络 ----
    {
        "match": "ultralight and highly compressible graphene aerogels",
        "author": "Hu", "year": 2013,
        "note": "超轻可压缩石墨烯气凝胶：3D 网络机械弹性与结构稳定性的标志性工作，启发了可压缩储能器件方向。",
    },
    {
        "match": "biomimetic superelastic graphene-based cellular monoliths",
        "author": "Qiu", "year": 2012,
        "note": "仿生蜂窝石墨烯整体材料：微结构-宏观弹性关联，为柔性/承压储能提供材料基础。",
    },
    {
        "match": "highly compression-tolerant supercapacitor based on polypyrrole-mediated graphene foam",
        "author": "Zhao", "year": 2013,
        "note": "可压缩超级电容器典型器件：3D 石墨烯泡沫骨架在承压状态下保持导电通路的直接演示。",
    },
    # ---- 复合网络与器件 ----
    {
        "match": "freestanding three-dimensional graphene/MnO2 composite networks",
        "author": "He", "year": 2013,
        "note": "3D 石墨烯/MnO₂ 超轻自支撑复合电极：导电网络骨架担载赝电容材料的范式性工作。",
    },
    {
        "match": "flexible solid-state supercapacitors based on three-dimensional graphene hydrogel films",
        "author": "Xu", "year": 2013,
        "note": "3D 石墨烯水凝胶膜固态柔性器件：自支撑网络走向全固态柔性应用的关键一步。",
    },
    {
        "match": "3-dimensional graphene carbon nanotube carpet-based microsupercapacitors",
        "author": "Lin", "year": 2013,
        "note": "石墨烯/CNT 三维地毯结构微型超级电容器：1D+2D 复合导电网络在微型器件中的示范。",
    },
    {
        "match": "ultrahigh-power micrometre-sized supercapacitors based on onion-like carbon",
        "author": "Pech", "year": 2010,
        "note": "洋葱碳微型超级电容器：0D 颗粒点接触网络在超高扫描速率下的性能标杆。",
    },
    # ---- 生物质与新兴导电网络 ----
    {
        "match": "a high-performance carbon for supercapacitors obtained by carbonization of a seaweed biopolymer",
        "author": "Raymundo-Piñero", "year": 2006,
        "note": "海藻生物质碳：生物质路线高比电容经典，天然分级孔结构的早期价值证明。",
    },
    {
        "match": "conductive MOF electrodes for stable supercapacitors with high areal capacitance",
        "author": "Sheberla", "year": 2017,
        "note": "导电 MOF 电极：本征导电骨架实现高面电容的范例，为三维导电网络设计提供了碳之外的思路参照。",
    },
    {
        "match": "graphene and graphene-based materials for energy storage applications",
        "author": "Zhu", "year": 2014,
        "note": "石墨烯储能应用高被引综述：石墨烯电极、三维组装与复合体系的全景整理。",
    },
]
