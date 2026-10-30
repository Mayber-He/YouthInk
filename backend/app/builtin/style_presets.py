"""Built-in style templates for YouthInk novels (Design Doc Section 7.3)."""

from __future__ import annotations

from typing import Any

DEFAULT_FORBIDDEN_EXPRESSIONS: list[str] = [
    "不由得",
    "嘴角勾起一抹弧度",
    "心中五味杂陈",
    "眼中闪过一丝",
    "命运的齿轮开始转动",
    "嘴角微微上扬",
    "深邃的眼眸",
    "不知为何",
    "莫名地",
]

BUILTIN_STYLE_TEMPLATES: list[dict[str, Any]] = [
    {
        "name": "清新校园",
        "is_builtin": 1,
        "pov": "第三人称限知",
        "tense_feel": "当下进行感",
        "tone": "清新治愈",
        "sentence_pref": "长短交错",
        "dialogue_ratio": "适中",
        "desc_focus": "环境氛围、动作细节",
        "pacing": "慢热细腻",
        "example_paras": [
            "五月的风穿过走廊尽头的香樟树，把刚发下来的物理试卷吹得哗啦作响。林夏用笔帽压住卷角，抬头时正好撞进前排少年转过来的视线里。",
            "操场边的自动贩卖机吐出一罐冰镇柠檬茶，铝罐外壁很快凝出一层细密的水珠。他什么也没说，只是把拉环拉开半寸，推到她手边。"
        ],
        "forbidden_exprs": DEFAULT_FORBIDDEN_EXPRESSIONS,
    },
    {
        "name": "细腻暗恋",
        "is_builtin": 1,
        "pov": "第一人称",
        "tense_feel": "回忆追述感",
        "tone": "细腻文艺",
        "sentence_pref": "长短交错",
        "dialogue_ratio": "少",
        "desc_focus": "心理、环境氛围",
        "pacing": "慢热细腻",
        "example_paras": [
            "那年高二整个漫长的雨季，我都在练习一件毫无意义的事——在课间操散场的人潮里，用余光准确找到那件左袖口沾了一点蓝黑墨水的校服。",
            "有些名字在心里念了上千遍，真正喊出口的时候，却轻得像粉笔灰落在讲台边沿。"
        ],
        "forbidden_exprs": DEFAULT_FORBIDDEN_EXPRESSIONS,
    },
    {
        "name": "轻松欢脱",
        "is_builtin": 1,
        "pov": "第三人称限知",
        "tense_feel": "当下进行感",
        "tone": "轻松搞笑",
        "sentence_pref": "短句为主",
        "dialogue_ratio": "多",
        "desc_focus": "对话推进、动作细节",
        "pacing": "紧凑推进",
        "example_paras": [
            "「年级第一怎么了？年级第一抢食堂糖醋排骨也得排队！」陈橙把饭卡拍在刷卡机上，气势汹汹地护住最后一份小排。",
            "旁边的周牧慢条斯理地端起餐盘：「不抢，我刚跟阿姨打听过了，后厨还有一锅刚出炉的。」"
        ],
        "forbidden_exprs": DEFAULT_FORBIDDEN_EXPRESSIONS,
    },
    {
        "name": "青春疼痛",
        "is_builtin": 1,
        "pov": "第三人称限知",
        "tense_feel": "回忆追述感",
        "tone": "虐心、现实向",
        "sentence_pref": "偏重长句",
        "dialogue_ratio": "适中",
        "desc_focus": "心理、动作细节",
        "pacing": "慢热细腻",
        "example_paras": [
            "高考结束那天傍晚，天桥下的霓虹灯一盏接一盏亮起来。他们站在十字路口的两端，谁都没有先迈出那一步，好像只要不道别，那个夏天就还不算真正散场。",
            "后来她才明白，十七岁许下的诺言不是假的，只是那时候的他们还不知道，时间比誓言重得多。"
        ],
        "forbidden_exprs": DEFAULT_FORBIDDEN_EXPRESSIONS,
    },
]
