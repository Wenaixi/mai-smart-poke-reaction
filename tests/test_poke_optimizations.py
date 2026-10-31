"""测试智能戳一戳：取消固定回复与提示词优化。"""

import pytest
from unittest.mock import MagicMock
from core.state import PokeContext
from core.reaction import ReactionExecutor

class DummyConfig:
    class Reaction:
        back_poke_weight = 0.6
        emoji_weight = 0.2
        llm_weight = 0.4
        llm_response_style = ""
    reaction = Reaction()

    class Fallback:
        normal_replies = []
        spam_replies = []
        silent_replies = []
    fallback = Fallback()

class DummyPlugin:
    config = DummyConfig()
    ctx = MagicMock()

def test_decide_reaction_kind_no_text():
    """验证决策不再包含 text 选项，只返回 poke、emoji、llm。"""
    plugin = DummyPlugin()
    executor = ReactionExecutor(plugin)

    # 多次抽取，确保不会返回已移除的 "text"
    kinds = {executor._decide_reaction_kind(is_spam=False) for _ in range(50)}
    assert "text" not in kinds
    assert kinds.issubset({"poke", "emoji", "llm"})

def test_build_llm_prompt_explains_qq_poke_feature():
    """验证提示词清晰包含 QQ 戳一戳小功能说明与轻量社交认知。"""
    plugin = DummyPlugin()
    executor = ReactionExecutor(plugin)

    ctx = PokeContext()
    ctx.cooldown_key = "group_123"
    ctx.poker_id = "10001"
    ctx.poker_name = "小天"
    ctx.target_id = "931734681"
    ctx.group_id = "123"
    ctx.is_group = True
    ctx.poke_action = "拍了拍"
    ctx.stream_id = "stream_1"
    ctx.self_id = "931734681"

    prompt = executor._build_llm_prompt(ctx, is_spam=False, persona="你是一个可爱的高中女生麦麦。")
    assert len(prompt) == 2
    system_msg = prompt[0]["content"]
    user_msg = prompt[1]["content"]

    # 验证关键认知描述
    assert "轻量社交互动小功能" in system_msg
    assert "通常用于打招呼、轻拍提醒、或者顺手提到别人" in system_msg
    assert "没有任何身体接触或恶意攻击意味" in system_msg
    assert "简短白话" in system_msg

    # 验证暴戳提示
    prompt_spam = executor._build_llm_prompt(ctx, is_spam=True, persona="你是一个可爱的高中女生麦麦。")
    user_spam_msg = prompt_spam[1]["content"]
    assert "连续多次" in user_spam_msg
    assert "连拍了好几下提醒你" in user_spam_msg
