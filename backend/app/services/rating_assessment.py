"""PlayNow self-assessment, not a verified UTR or USTA rating.

Common recreational rating descriptions inform the original Chinese questions.
Only NTRP is assessed. The separate reserved UTR field is never written here.
"""
from decimal import Decimal, ROUND_HALF_UP

VERSION = "playnow_self_v1"
LEVELS = [Decimal("2.0") + Decimal("0.5") * index for index in range(8)]
QUICK_LEVELS = [
    {"value": 2, "name": "初识", "description": "能把球打过网，懂基本计分；连续回合较少，发球还不稳定。"},
    {"value": 3, "name": "入门", "description": "能进行慢节奏底线对拉，正手逐渐稳定，反手和发球仍需练习。"},
    {"value": 4, "name": "会打", "description": "正反手底线击球较稳定，能控制方向，一发和二发都能可靠进区。"},
    {"value": 5, "name": "熟练", "description": "能运用旋转、落点和网前战术，在比赛压力下仍能稳定执行。"},
]


def question(key, title, descriptions):
    return {"id": key, "title": title, "options": [
        {"value": index, "description": text} for index, text in enumerate(descriptions)
    ]}


QUESTIONS = [
    question("rally", "你的正手和底线相持表现如何？", [
        "主要练习把球打过网，常在两三拍内失误。", "能慢速短暂来回，方向和深度不稳定。",
        "能连续慢速对拉，正手较稳，中速来球仍易失误。", "中速相持较稳定，开始控制方向。",
        "能控制深度和方向，主动改变落点。", "能结合力量、旋转与角度组织进攻。",
        "面对高速来球仍能稳定回击并创造机会。", "持续高强度相持，能稳定攻防转换。",
    ]),
    question("backhand", "你的反手应对能力如何？", [
        "反手经常打不中或无法过网。", "能回慢球，但主要以挡球维持。",
        "慢球反手可以来回，方向和深度有限。", "中速反手较可靠，能控制基本方向。",
        "能在跑动中稳定回击，具备一定旋转与深度。", "能用反手改变线路，处理不同高度来球。",
        "反手可主动进攻，压力下仍有稳定性。", "高速攻防中能持续运用多种反手线路。",
    ]),
    question("serve", "你的一发和二发表现如何？", [
        "还在练习发进正确区域，双误较多。", "慢速发球能进区，二发不够可靠。",
        "一发开始稳定，二发以保守发进为主。", "能控制发球方向，二发成功率较稳定。",
        "一发有一定速度，二发可靠并带基础旋转。", "可运用旋转和落点，一发能创造优势。",
        "发球可主动得分，二发能承受接发压力。", "能按战术改变速度、旋转和落点，二发有质量。",
    ]),
    question("return", "你处理对方发球时的表现如何？", [
        "判断来球较困难，接发经常失误。", "能接慢速发球，但方向不可控。",
        "慢速发球能回到场内，中速发球比较吃力。", "中速接发可靠，能回到指定大致方向。",
        "能处理速度和旋转，回球有一定深度。", "能按对方发球质量选择防守或进攻。",
        "能稳定处理强力一发，并主动攻击二发。", "高强度比赛中能持续执行接发战术。",
    ]),
    question("net", "你的截击、高压和网前表现如何？", [
        "网前判断和触球还不熟悉。", "能挡回慢球，截击和高压较易失误。",
        "简单正手截击能完成，反手截击不稳定。", "正反手截击渐稳定，能完成简单高压。",
        "能控制网前落点，高压和移动衔接较可靠。", "能主动上网，运用截击和高压结束回合。",
        "能稳定处理低球、快球，网前有多种得分方式。", "高压对抗下能准确判断并连续完成网前攻防。",
    ]),
    question("match", "你的移动、战术与实际比赛表现如何？", [
        "主要关注把球回过去，正在熟悉站位和计分。", "了解基本规则，移动和回位常不及时。",
        "能完成友谊赛，会基础回位，连续发挥仍不稳定。", "能识别空档，运用简单战术并保持相持。",
        "能根据对手弱点选择线路，攻防移动较完整。", "常打业余比赛，能变换节奏并执行进攻组合。",
        "高水平业余竞争中仍能稳定执行完整战术。", "长期竞技训练，强对抗中能持续调整和掌控节奏。",
    ]),
]


def catalog():
    # Deliberately exclude the reserved UTR field from the client catalog.
    return {"version": VERSION, "quick_levels": QUICK_LEVELS, "questions": QUESTIONS,
            "notice": "按平时比赛中的表现选择。本结果为网球自评估算，仅供参考，可重新测评。"}


def validate_answers(mode, answers):
    if mode == "quick":
        if set(answers) != {"level"} or answers["level"] not in (2, 3, 4, 5):
            raise ValueError("请选择一个有效的快速定级档位")
    elif mode == "full":
        if set(answers) != {q["id"] for q in QUESTIONS}:
            raise ValueError("请完成全部定级问题")
        if any(value not in range(len(LEVELS)) for value in answers.values()):
            raise ValueError("问卷选项无效")
    else:
        raise ValueError("问卷模式无效")


def assess(mode, answers):
    validate_answers(mode, answers)
    if mode == "quick":
        return Decimal(answers["level"])
    else:
        # Equal skill weights avoid rating solely by years played or one best stroke.
        level = sum((LEVELS[value] for value in answers.values()), Decimal("0")) / len(QUESTIONS)
        return (level * 2).quantize(Decimal("1"), rounding=ROUND_HALF_UP) / 2
