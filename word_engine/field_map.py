"""
word_engine.field_map — 关键字映射规则 + 教育理念词库

单元格文本 → 填充字段 key 的匹配规则（CELL_KEYWORD_MAP）。
教育理念专业词汇注入（PHILOSOPHY_HINTS）。
班级年龄特征约束（CLASS_LEVEL_HINTS）。

零外部依赖，可独立单测。
"""
from __future__ import annotations

from typing import Optional

# ──────────────────────────────────────────────
# 关键字映射表：单元格文本 → 填充字段 key
# 优先级从上到下，第一个匹配的规则生效
# ──────────────────────────────────────────────
CELL_KEYWORD_MAP: list[tuple[list[str], str]] = [
    (["基础信息", "基本信息"],                                     "class_info"),
    (["上周情况分析", "上周分析", "上周情况"],                      "children_baseline"),
    (["本周重点与难点", "重点与难点", "重点难点"],                  "key_difficulty"),
    (["幼儿已有经验", "已有经验", "前测"],                          "children_baseline"),
    (["本周活动总览表", "周活动总览", "周安排总览"],                "week_overview"),
    (["每日活动要点", "每日要点"],                                  "daily_points"),
    (["户外与体能活动", "体能活动"],                                "outdoor"),
    (["生活活动与保育", "保育"],                                    "life"),
    (["环境创设", "环创活动", "环境布置", "环创"],                  "environment"),
    (["家园共育", "家园互动", "家长工作", "家园社区互动", "家园活动", "家园"], "family"),
    (["个别化支持", "个别指导"],                                    "individual_support"),
    (["安全与风险提示", "安全提示", "风险提示", "安全"],            "safety_risk"),
    (["资源与材料清单", "材料清单", "资源清单"],                    "resource_list"),
    (["观察记录计划", "观察计划"],                                  "observation_plan"),
    (["周反思", "本周反思"],                                        "evaluation"),
    (["下周衔接", "下周计划", "衔接"],                              "next_week_plan"),
    (["午睡指导", "睡姿指导", "穿脱衣物", "衣物摆放", "睡前习惯"],  "nap_guidance"),
    (["教学主题", "活动主题", "本月主题", "单元主题", "主题"],      "theme"),
    (["教育理念", "课程理念", "理念", "风格"],                      "philosophy"),
    (["活动目标", "教学目标", "重点目标", "目标"],                  "goals"),
    (["活动准备", "材料准备", "准备"],                              "preparation"),
    (["指导要点"],                                                   "guidance"),
    (["晨间运动", "晨间", "早谈", "早  谈", "晨谈", "早操"],        "morning"),
    (["户外活动", "体育活动", "户外游戏", "户外"],                  "outdoor"),
    (["环创活动", "环境创设", "环创"],                              "environment"),
    (["生活活动", "一日生活", "生活"],                              "life"),
    (["学习活动", "集中活动", "教学活动"],                          "study"),
    (["游戏活动", "游戏"],                                          "game"),
    (["区域活动", "区角活动", "区域"],                              "area"),
    (["离园活动", "离园"],                                          "departure"),
    (["幼儿自主", "自主发起"],                                      "child_initiative"),
    (["评价与反思", "评价", "反思", "小结"],                        "evaluation"),
    (["班级", "班"],                                                "class_info"),
]

# 可填到周网格内容格的活动字段集合（不含 meta 字段）
_ACTIVITY_FIELDS = frozenset({
    "morning", "outdoor", "environment", "life", "study",
    "game", "area", "family", "departure", "evaluation", "nap_guidance",
})

WEEKLY_STANDARD_MODULES = [
    "基础信息", "本周主题", "周总目标（五大领域）", "本周重点与难点",
    "幼儿已有经验", "本周活动总览表", "每日活动要点", "区域活动设计",
    "户外与体能活动", "生活活动与保育", "环境创设", "家园共育",
    "个别化支持", "安全与风险提示", "资源与材料清单", "观察记录计划",
    "周反思", "下周衔接", "午睡指导",
]

ACTIVITY_LABEL_MAP = {
    "morning":     "🌅 晨间运动",
    "outdoor":     "🌿 户外活动",
    "environment": "🎨 环创活动",
    "life":        "🍽 生活活动",
    "area":        "🧩 区域活动",
    "family":      "👨‍👩‍👧 家园活动",
    "departure":   "🌙 离园活动",
}

WEEKDAY_TAGS = (
    ("星期一", "mon"), ("星期二", "tue"), ("星期三", "wed"),
    ("星期四", "thu"), ("星期五", "fri"),
    ("周一", "mon"),   ("周二", "tue"),   ("周三", "wed"),
    ("周四", "thu"),   ("周五", "fri"),
)

FIVE_DOMAINS = ("健康", "语言", "社会", "科学", "艺术")

# ──────────────────────────────────────────────
# 教育理念专业词汇库（补充 Prompt 提示词）
# ──────────────────────────────────────────────
PHILOSOPHY_HINTS: dict[str, str] = {
    "蒙氏教育（AMI/AMS）": (
        "请大量使用以下专业术语：操作教具、敏感期观察、三段式教学、工作周期、"
        "有准备的环境（Prepared Environment）、工作毯、混龄协作、内在纪律感。"
    ),
    "瑞吉欧教育": (
        "请大量使用以下专业术语：生成课程（Emergent Curriculum）、环境留痕（Documentation）、"
        "一百种语言、项目网络（Project Web）、呈现板（Documentation Panel）、协作解读。"
    ),
    "DAP 发展适宜性实践": (
        "请大量使用以下专业术语：发展适宜性、年龄适宜性、个体适宜性、"
        "最近发展区（ZPD）、支架式学习（Scaffolding）、真实性评估、文化回应性教学。"
    ),
    "华德福教育": (
        "请大量使用以下专业术语：生命节律、季节庆典、季节桌（Seasonal Table）、"
        "意志力、优律思美（Eurythmy）、故事讲述（Storytelling）、吸气-呼气节奏。"
    ),
    "项目化学习（PBL）": (
        "请大量使用以下专业术语：驱动性问题（Driving Question）、成果展示、"
        "评价量规（Rubric）、跨领域整合、真实受众、合作探究。"
    ),
    "自主游戏 / 游戏化课程": (
        "请大量使用以下专业术语：儿童视角、游戏观察、松散材料（Loose Parts）、"
        "低结构材料、游戏即工作、自由探索。"
    ),
    "传统文化 / 国学教育": (
        "请大量使用以下专业术语：二十四节气、节气文化、经典诵读、传统礼仪、"
        "传统游戏传承、非遗体验、文化认同。"
    ),
    "五大领域": (
        "请对应五大领域（健康、语言、社会、科学、艺术）分别阐述核心经验，"
        "并参照《3-6岁儿童学习与发展指南》的典型表现。"
    ),
}

# ──────────────────────────────────────────────
# 班级年龄特征约束（补充 Prompt 提示词）
# ──────────────────────────────────────────────
CLASS_LEVEL_HINTS: dict[str, str] = {
    "小班": (
        "【小班（3-4岁）特征】活动以感官体验、重复操作、生活自理为主；"
        "目标用词：感受、尝试、愿意、喜欢、在教师帮助下；"
        "活动时长短（10-15分钟）、材料大而安全、规则简单直接；"
        "户外侧重大肌肉运动（走跑跳爬）、区域侧重娃娃家与建构区。"
    ),
    "中班": (
        "【中班（4-5岁）特征】活动重探究尝试、规则合作、语言表达；"
        "目标用词：能够、学会、初步理解、主动参与、与同伴合作；"
        "活动时长中等（15-20分钟）、材料多样化、开始引入小组任务；"
        "户外增加器械组合与规则游戏、区域增加科学区与美工区深度。"
    ),
    "大班": (
        "【大班（5-6岁）特征】活动重深度探究、自主计划、问题解决、社会性成长；"
        "目标用词：自主、比较、发现规律、合作完成、独立表达观点；"
        "活动时长较长（20-30分钟）、材料低结构化、鼓励幼儿自主设计玩法；"
        "户外增加竞技合作与冒险挑战、区域强调项目式学习与跨区联动。"
    ),
}


def match_field(cell_text: str) -> Optional[str]:
    """根据单元格文本匹配应填充的字段 key，无匹配返回 None。
    同时检查原文和去空行拼合版，兼容 Word 多段拆字（如"集体\\n\\n活动"）。"""
    t = cell_text.strip()
    t_compact = "".join(t.split())
    for keywords, field in CELL_KEYWORD_MAP:
        for kw in keywords:
            if kw in t or kw in t_compact:
                return field
    return None


def _weekday_tag_from_header(text: str) -> Optional[str]:
    t = str(text or "").strip()
    t_compact = "".join(t.split())
    for alias, tag in WEEKDAY_TAGS:
        if alias in t or alias in t_compact:
            return tag
    return None


def _build_weekday_domain_plan(theme: str) -> dict[str, str]:
    """周维度五大领域均衡分配，起始位由主题名决定，避免固定顺序。"""
    seed = sum(ord(ch) for ch in str(theme or ""))
    start = seed % len(FIVE_DOMAINS)
    ordered = [FIVE_DOMAINS[(start + i) % len(FIVE_DOMAINS)] for i in range(5)]
    return {
        "mon": ordered[0], "tue": ordered[1], "wed": ordered[2],
        "thu": ordered[3], "fri": ordered[4],
    }
