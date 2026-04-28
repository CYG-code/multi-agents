from __future__ import annotations

# Rule-triggered messages
SILENCE_REASON_TEMPLATE = "房间沉默已超过 {seconds} 秒，需要重新推动讨论。"
SILENCE_STRATEGY = "提出一个具体问题，邀请成员基于已有观点给出下一步分析。"

MONOPOLY_REASON_TEMPLATE = "同一成员连续发送了 {count} 条消息，请邀请其他成员参与。"
MONOPOLY_STRATEGY = "点名一位暂未发言或发言较少的同学，邀请其补充观点。"

TIME_PROGRESS_PHASE_TEXT = {
    "early": "前期",
    "middle": "中期",
    "late": "后期",
}
TIME_PROGRESS_REASON_TEMPLATE = (
    "时间节点提醒：已进行 {elapsed_minutes} 分钟（命中 {node_minutes} 分钟节点），"
    "当前处于{phase_text}，判断为{progress_text}。"
)
TIME_PROGRESS_PROGRESS_TEXT = {
    "normal": "进度正常",
    "slow": "进度偏慢",
}
TIME_PROGRESS_STRATEGY_SLOW = (
    "请用 5-8 分钟明确分工并收敛：先确认当前状态，再确定下一步目标，"
    "最后指定每位同学的短任务。诊断信息：{progress_details}"
)
TIME_PROGRESS_STRATEGY_NORMAL = (
    "请继续保持节奏并做一次小结：确认当前状态是否清晰、下一步目标是否可执行，"
    "必要时提前安排收敛动作。诊断信息：{progress_details}"
)

# Mention-triggered websocket text
MENTION_UNSUPPORTED = "当前版本暂不支持该智能体。"
MENTION_ACCEPTED = "已收到召唤。"
MENTION_QUEUED = "已进入处理队列。"
MENTION_REASON_TEMPLATE = "学生 {student_name} 通过 @{role} 主动召唤。"
MENTION_STRATEGY = "优先回应该同学的提问，并给出可继续讨论的下一步。"

# Committee defaults and routing text
COMMITTEE_DEFAULT_REASON = "专家委员会建议进行一次引导。"

D_REASON = {
    "D1": "社会协作中缺少 D1（监控并维持共享理解）行为。",
    "D3": "社会协作中缺少 D3（调整团队组织）行为。",
    "B1": "社会协作中缺少 B1（建立共享表征）行为。",
}
D_STRATEGY = {
    "D1": "请主持人引导全组对当前问题理解做一次对齐检查。",
    "D3": "请总结者先梳理现有分工，再由主持人组织必要的分工调整。",
    "B1": "请主持人引导学生明确关键概念定义与边界，确认理解一致。",
}

SOCIAL_D2_REASON = "行动沟通较多但缺少 D2（监控并评价方案结果）行为。"
SOCIAL_D2_STRATEGY = "请批判者引导小组用反例和证据检查当前行动结果质量。"

SOCIAL_ROLE_ORG_REASON = "团队角色理解或组织规则不足（A3/B3 缺失）。"
SOCIAL_ROLE_ORG_STRATEGY = "请主持人明确角色分工与协作规则，减少并行讨论冲突。"

SUPPRESS_MONOPOLY_REASON = "近期已由 monopoly 规则处理连续单人主导问题，委员会不重复派发鼓励者。"
SUPPRESS_MONOPOLY_OBSERVE = "观察是否转为长期参与不均衡问题。"

LOW_BEHAVIOR_REASON = "行为投入偏低，存在低参与或单人主导风险。"
LOW_BEHAVIOR_STRATEGY = "请鼓励者点名低参与成员补充观点，再由主持人确认下一步分工。"

SUPPRESS_SILENCE_REASON = "近期已由 silence 规则处理全组沉默，委员会暂不重复发起同类社会维度干预。"
SUPPRESS_SILENCE_OBSERVE = "观察互动承接是否在下一轮恢复。"

LOW_SOCIAL_REASON = "社会投入偏低，出现互动承接不足。"
LOW_SOCIAL_STRATEGY = "请主持人组织一次结构化回应轮，确保成员彼此承接观点。"

LOW_COGNITIVE_REASON = "认知投入不足，观点多样性偏低。"
LOW_COGNITIVE_STRATEGY = "请批判者提出关键反例并要求证据验证方案边界。"

LOW_EMOTIONAL_REASON = "情感投入偏低，出现焦虑/挫败/冲突信号。"
LOW_EMOTIONAL_STRATEGY = "请鼓励者先稳态，再推动小步目标确认。"

OBSERVE_REASON = "四维投入总体稳定，建议继续观察，不强制干预。"
OBSERVE_NEXT = "关注是否出现沉默成员增多、互动承接下降或证据不足。"
