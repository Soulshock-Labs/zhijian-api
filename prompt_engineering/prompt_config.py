"""
Prompt 工程配置和模板系统
可复现的、任何电脑都一致的 Prompt 生成引擎
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
from typing import Dict, List, Optional


class PromptTemplate:
    """中央 Prompt 管理系统"""

    def __init__(self, config_dir: Optional[Path] = None):
        self.config_dir = config_dir or Path(__file__).parent
        self.version = "1.0.0"
        self.examples = self._load_examples()
        self.philosophy_hints = self._load_philosophy()
        self.class_hints = self._load_class_hints()

    def _load_examples(self) -> List[Dict]:
        """加载参考范本"""
        path = self.config_dir / "reference_templates.json"
        if not path.exists():
            return []
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
                return data.get("templates", [])[:3]  # 前 3 个
        except Exception as e:
            print(f"[WARN] 加载参考范本失败: {e}")
            return []

    def _load_philosophy(self) -> Dict:
        """加载教育理念提示词"""
        path = self.config_dir / "philosophy_hints.json"
        if not path.exists():
            return self._default_philosophy()
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return self._default_philosophy()

    def _load_class_hints(self) -> Dict:
        """加载班级特征提示词"""
        path = self.config_dir / "class_level_hints.json"
        if not path.exists():
            return self._default_class_hints()
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return self._default_class_hints()

    @staticmethod
    def _default_philosophy() -> Dict:
        return {
            "以幼儿为中心": "强调观察和追随幼儿的兴趣，活动应由幼儿主导，教师提供支持和引导。",
            "探索与体验": "通过动手操作和亲身体验，让幼儿发现规律、解决问题、积累经验。",
            "游戏为主": "认为游戏是幼儿的主要活动形式，学习应该在游戏中自然发生。",
            "生活化教学": "将教学融入日常生活，让幼儿在吃、玩、睡等日常活动中学习。",
            "五大领域均衡": "健康、语言、社会、科学、艺术领域均等重要，不能偏废。",
        }

    @staticmethod
    def _default_class_hints() -> Dict:
        return {
            "小班": "3-4 岁幼儿。特点：以自我为中心，语言发展初期，动作粗大，情绪易变化。教学建议：多重复示范，简化指令，强调安全，活动时间短（10-15 分钟）。",
            "中班": "4-5 岁幼儿。特点：社交能力发展，语言更流畅，细动作改善，有初步规则意识。教学建议：平衡示范和探索，增加规则和角色扮演，活动时间 15-20 分钟。",
            "大班": "5-6 岁幼儿。特点：自主性强，逻辑思维发展，合作能力提升，求知欲旺盛。教学建议：强调自主探索，引入简单数学和字母，增加挑战难度，活动时间 20-25 分钟。",
        }

    def build_system_prompt(self) -> str:
        """构造系统 Prompt"""
        return textwrap.dedent("""
            你是一位拥有 15 年经验的资深幼儿园教研主任，曾在全国示范幼儿园工作。

            ## 核心职责
            编写符合《幼儿园教育指导纲要》、兼具园本特色的周计划和日教案。

            ## 绝对要求

            1. **活动具体性**：每个活动必须具体可执行
               - 包含真实的、可采购的材料清单
               - 提供分步骤的玩法描述（3-5 步，每步 20-30 字）
               - 禁止"体育运动""创意美术"这样的模糊表述

            2. **风格一致性**：所有输出必须模仿参考范本的结构、用词、逻辑
               - 不要自由创意，要遵循范本风格
               - 保持专业的、实用的语调

            3. **班级适配**：难度和表述必须符合年龄特性
               - 小班（3-4 岁）：更多示范、更多重复、动作简单、强调安全
               - 中班（4-5 岁）：平衡示范与探索、难度适中、初步规则
               - 大班（5-6 岁）：自主探索、挑战性高、数字和文字融入

            4. **五大领域均衡**：一周内不能集中在某个领域
               - 周内应各有 1-2 个活动（总共 5 个）
               - 五大领域：健康、语言、社会、科学、艺术

            ## 禁止

            - 编造不存在的活动或游戏名称
            - 写出"随意""自由发挥"这样模糊的表述
            - 一周内两个以上相同领域的活动
            - 写出与班级年龄不符的难度或风格
            - 儿歌内容与主题无关

            ## 输出格式

            严格的 JSON，无 Markdown，无其他文字。JSON 必须有效且可解析。
        """).strip()

    def build_user_prompt(
        self,
        theme: str,
        class_level: str,
        philosophy: str,
        activities: List[str],
    ) -> str:
        """构造用户 Prompt"""

        # 获取参考范本
        examples_text = self._format_examples(class_level)

        # 获取理念和班级提示
        phil_hint = self.philosophy_hints.get(philosophy, "")
        class_hint = self.class_hints.get(class_level, "")

        acts_str = "、".join(activities) if activities else "区域活动、户外活动"

        return textwrap.dedent(f"""
            【参考范本 - 必须参考这些优秀教案的结构和风格】

            {examples_text}

            【关键约束】
            - 主题：{theme}
            - 班级：{class_level}（{class_hint}）
            - 教育理念：{philosophy}
              {phil_hint}
            - 活动类型：{acts_str}

            【具体要求】

            1. 周目标：2-3 个，用行为动词，可测量、可观察
               示例：「培养幼儿的自理能力」「提升幼儿的合作意识」

            2. 五大领域（健康、语言、社会、科学、艺术）均衡分配，周内不重复

            3. 每日活动（周一至周五）包含：
               - day: "周一" 至 "周五"
               - domain: "健康" / "语言" / "社会" / "科学" / "艺术"
               - activity_name: 具体、有画面感的活动名称
                 ✓ 好例子：「踩高跷」「穿大鞋」「送快递的叔叔」
                 ✗ 坏例子：「体育运动」「创意美术」「户外活动」
               - materials: 3-5 项可采购或自制的材料
                 ✓ 好例子：["纸盒（30×20cm）", "小红旗", "泡沫盒"]
                 ✗ 坏例子：["体育器材", "美术用品"]
               - process: 分 3-5 步的玩法，每步 20-30 字
                 格式：「第一步：...（教师行为）。第二步：...（幼儿操作）。...」
               - observation: 3-5 项观察重点，用动词短语
                 ✓ 好例子："能否保持平衡" "是否主动帮助同伴" "能否用完整句子描述"
                 ✗ 坏例子："平衡能力" "合作精神"
               - teacher_hint: 教师的 1-2 句核心指导要点

            4. songs: 1-2 首儿歌名称或内容
               - 必须与主题相关
               - 可以是真实存在的儿歌，也可以是创意改编

            5. reflection: 周反思
               - 本周幼儿的发展亮点（观察到的具体行为）
               - 下周的关注点或改进方向
               - 80 字以内

            【输出 JSON 格式】
            {{
              "week_theme": "{theme}",
              "class_level": "{class_level}",
              "goals": ["目标 1", "目标 2"],
              "days": [
                {{
                  "day": "周一",
                  "domain": "健康",
                  "activity_name": "具体活动名称",
                  "materials": ["材料 1", "材料 2"],
                  "process": "分步骤的玩法描述（导入-示范-操作-延伸）",
                  "observation": ["观察点 1：能否...", "观察点 2：是否..."],
                  "teacher_hint": "教师核心指导要点"
                }},
                ...（周二至周五）
              ],
              "songs": ["儿歌名称或内容"],
              "reflection": "周反思（80 字以内）"
            }}

            只返回 JSON，不要其他文字。
        """).strip()

    def _format_examples(self, class_level: str) -> str:
        """格式化参考范本为 Prompt 的一部分"""
        if not self.examples:
            return "（暂无参考范本，请按照标准结构生成）"

        relevant = [
            e for e in self.examples if e.get("class_level") == class_level
        ][:2]

        if not relevant:
            relevant = self.examples[:2]

        result = []
        for i, ex in enumerate(relevant, 1):
            result.append(
                textwrap.dedent(f"""
                【参考范本 {i}】
                主题：{ex.get("week_theme", "未知")}
                班级：{ex.get("class_level", "未知")}
                目标：{", ".join(ex.get("goals", [])[:2])}
                周一活动：{ex.get("days", [{}])[0].get("activity_name", "未知")}
                - 材料：{", ".join(ex.get("days", [{}])[0].get("materials", []))}
                - 玩法摘要：{ex.get("days", [{}])[0].get("process", "")[:80]}...
                - 观察重点：{", ".join(ex.get("days", [{}])[0].get("observation", [])[:2])}
                """).strip()
            )

        return "\n".join(result)

    def get_version_info(self) -> Dict:
        """获取版本信息"""
        return {
            "version": self.version,
            "timestamp": "2026-04-14T00:00:00Z",
            "examples_count": len(self.examples),
            "philosophies": list(self.philosophy_hints.keys()),
            "class_levels": list(self.class_hints.keys()),
        }


# 全局实例
_PROMPT_TEMPLATE = None


def get_prompt_template() -> PromptTemplate:
    """获取全局 Prompt 模板实例"""
    global _PROMPT_TEMPLATE
    if _PROMPT_TEMPLATE is None:
        _PROMPT_TEMPLATE = PromptTemplate()
    return _PROMPT_TEMPLATE
