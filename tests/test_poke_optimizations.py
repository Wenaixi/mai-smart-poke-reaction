from types import SimpleNamespace
from wenaixi_mai_smart_poke_reaction.core.state import PokeContext
from wenaixi_mai_smart_poke_reaction.core.reaction import ReactionExecutor
from wenaixi_mai_smart_poke_reaction.plugin import SmartPokePlugin


def test_parse_poke_details_with_full_personalized_suffixes():
    """验证包含发起者动作前缀、动作动词和目标个性后缀的完整解析。"""
    payload = {
        "user_id": "123456",
        "target_id": "931734681",
        "raw_info": [
            {"type": "qq", "txt": "真人机麦麦 "},
            {"type": "nor", "txt": "欢迎加入信息社生活部!"},
            {"type": "nor", "txt": "拍了拍"},
            {"type": "qq", "txt": "准大一姜丝丝,努力学习只为回家"},
            {"type": "nor", "txt": "的睡个好觉吃个水饺"},
        ],
    }

    raw_text, prefix, verb, full_action, suffix = SmartPokePlugin._parse_poke_details(payload)
    assert "真人机麦麦" in raw_text
    assert "欢迎加入信息社生活部!" in raw_text
    assert "拍了拍" in raw_text
    assert "的睡个好觉吃个水饺" in raw_text

    assert prefix == "欢迎加入信息社生活部!"
    assert verb == "拍了拍"
    assert "欢迎加入信息社生活部! 拍了拍" in full_action
    assert suffix == "的睡个好觉吃个水饺"


def test_build_llm_prompt_injects_personalized_raw_text_and_my_suffix():
    """验证个性化原话与麦麦自身后缀被精准注入到模型 Prompt 中。"""
    ctx = PokeContext()
    ctx.self_id = "931734681"
    ctx.target_id = "931734681"
    ctx.poker_id = "123456"
    ctx.poker_name = "真人机麦麦"
    ctx.action_prefix = "欢迎加入信息社生活部!"
    ctx.action_verb = "拍了拍"
    ctx.poke_action = "欢迎加入信息社生活部! 拍了拍"
    ctx.target_suffix = "的睡个好觉吃个水饺"
    ctx.my_suffix = "睡个好觉吃个水饺"
    ctx.raw_text = "真人机麦麦 欢迎加入信息社生活部!拍了拍麦麦的睡个好觉吃个水饺"
    ctx.is_group = True

    fake_config = SimpleNamespace(
        reaction=SimpleNamespace(
            llm_response_style="",
        )
    )
    fake_plugin = SimpleNamespace(config=fake_config)
    executor = ReactionExecutor(fake_plugin)

    messages = executor._build_llm_prompt(ctx, is_spam=False, persona="你是一个可爱的高中女高中生麦麦。")
    system_prompt = messages[0]["content"]

    # 验证包含系统原文
    assert "【QQ系统通知原文】" in system_prompt
    assert "真人机麦麦 欢迎加入信息社生活部!拍了拍麦麦的睡个好觉吃个水饺" in system_prompt

    # 验证包含个性化后缀提示
    assert "【个性化后缀提示】" in system_prompt
    assert "睡个好觉吃个水饺" in system_prompt

    # 验证包含动作修饰
    assert "【动作修饰】" in system_prompt
    assert "欢迎加入信息社生活部!" in system_prompt


import pytest
from unittest.mock import AsyncMock, MagicMock

@pytest.mark.asyncio
async def test_record_bystander_poke_to_context():
    """验证群友之间互戳（麦麦未参与/跟风前）能正确记录到 Maisaka 上下文。"""
    plugin = SmartPokePlugin()
    plugin.config = MagicMock()
    plugin.config.plugin = MagicMock()
    plugin.config.plugin.record_self_poke_to_context = True
    plugin.ctx = MagicMock()
    plugin.ctx.logger = MagicMock()
    plugin.ctx.maisaka = MagicMock()
    plugin.ctx.maisaka.context = MagicMock()
    plugin.ctx.maisaka.context.append = AsyncMock(return_value={"success": True, "index": 1})
    plugin.ctx.chat = MagicMock()
    plugin.ctx.chat.get_stream_by_group_id = AsyncMock(return_value={"session_id": "stream_group_123"})

    ctx = PokeContext()
    ctx.is_group = True
    ctx.group_id = "987654"
    ctx.poker_id = "11111"
    ctx.poker_name = "群友甲"
    ctx.target_id = "22222"
    ctx.target_name = "群友乙"
    ctx.poke_action = "拍了拍"
    ctx.raw_text = "群友甲 拍了拍群友乙"

    # 执行注入
    await plugin.record_bystander_poke_to_context(ctx)

    plugin.ctx.maisaka.context.append.assert_called_once_with(
        stream_id="stream_group_123",
        segments=[{"type": "text", "content": "群友甲 拍了拍群友乙（QQ轻量互动，非物理触碰）"}],
        visible_text="群友甲 拍了拍群友乙（QQ轻量互动，非物理触碰）",
        source_kind="plugin:smart_poke:bystander_mutual",
    )


@pytest.mark.asyncio
async def test_record_bystander_poke_with_custom_suffix_and_fallback():
    """验证群友之间互戳带有复杂个性化后缀时，无损记入上下文（覆盖 raw_text 与降级拼接）。"""
    plugin = SmartPokePlugin()
    plugin.config = MagicMock()
    plugin.config.plugin.record_self_poke_to_context = True
    plugin.ctx = MagicMock()
    plugin.ctx.logger = MagicMock()
    plugin.ctx.maisaka = MagicMock()
    plugin.ctx.maisaka.context = MagicMock()
    plugin.ctx.maisaka.context.append = AsyncMock(return_value={"success": True, "index": 1})
    plugin.ctx.chat = MagicMock()
    plugin.ctx.chat.get_stream_by_group_id = AsyncMock(return_value={"session_id": "stream_group_123"})
    plugin.resolve_member_name = AsyncMock(return_value="小红")

    # 场景 1：有完整系统原文
    ctx1 = PokeContext()
    ctx1.is_group = True
    ctx1.group_id = "987654"
    ctx1.raw_text = "小明 拍了拍小红的西瓜，说熟了吗"
    await plugin.record_bystander_poke_to_context(ctx1)
    plugin.ctx.maisaka.context.append.assert_called_with(
        stream_id="stream_group_123",
        segments=[{"type": "text", "content": "小明 拍了拍小红的西瓜，说熟了吗（QQ轻量互动，非物理触碰）"}],
        visible_text="小明 拍了拍小红的西瓜，说熟了吗（QQ轻量互动，非物理触碰）",
        source_kind="plugin:smart_poke:bystander_mutual",
    )

    # 场景 2：无系统原文但有 target_suffix 降级拼接
    plugin.ctx.maisaka.context.append.reset_mock()
    ctx2 = PokeContext()
    ctx2.is_group = True
    ctx2.group_id = "987654"
    ctx2.poker_name = "小明"
    ctx2.target_name = "小红"
    ctx2.poke_action = "拍了拍"
    ctx2.target_suffix = "的作业，说都交给我"
    ctx2.raw_text = ""
    await plugin.record_bystander_poke_to_context(ctx2)
    plugin.ctx.maisaka.context.append.assert_called_once_with(
        stream_id="stream_group_123",
        segments=[{"type": "text", "content": "小明拍了拍小红的作业，说都交给我（QQ轻量互动，非物理触碰）"}],
        visible_text="小明拍了拍小红的作业，说都交给我（QQ轻量互动，非物理触碰）",
        source_kind="plugin:smart_poke:bystander_mutual",
    )


@pytest.mark.asyncio
async def test_handle_send_poke_tool_execution():
    """验证 @Tool('send_poke') 工具方法执行与上下文写入。"""
    plugin = SmartPokePlugin()
    plugin.config = MagicMock()
    plugin.config.plugin.enabled = True
    plugin.config.plugin.record_self_poke_to_context = True
    plugin._napcat = MagicMock()
    plugin._napcat.send_poke = AsyncMock(return_value=True)
    plugin.resolve_member_name = AsyncMock(return_value="被戳人")
    plugin.record_self_poke_to_context = AsyncMock()

    res = await plugin.handle_send_poke(
        target_id="33333",
        group_id="987654",
        stream_id="stream_123",
    )
    assert res.get("success") is True
    assert "被戳人" in res.get("content", "")
    plugin._napcat.send_poke.assert_called_once_with(
        "33333", "987654", is_group=True, label="tool_send_poke"
    )
    plugin.record_self_poke_to_context.assert_called_once()


@pytest.mark.asyncio
async def test_llm_reply_with_tool_call_silent_1b():
    """验证 1B 自主静默权：大模型仅调用 send_poke 工具而不输出文字时，回戳执行且不发空消息。"""
    fake_plugin = MagicMock()
    fake_plugin.config.reaction.min_delay_seconds = 0.0
    fake_plugin.config.reaction.max_delay_seconds = 0.0
    fake_plugin.config.reaction.llm_temperature = 0.7
    fake_plugin.config.reaction.llm_model = ""
    fake_plugin.config.reaction.llm_max_tokens = 0
    fake_plugin.config.reaction.llm_context_messages = 0
    fake_plugin.config.reaction.llm_persona = ""
    fake_plugin.config.reaction.llm_response_style = ""
    fake_plugin.record_poked_by_to_context = AsyncMock()

    # 模拟大模型返回 tool_calls 但没有正文文本
    fake_result = {
        "success": True,
        "response": "",
        "tool_calls": [{"name": "send_poke", "parameters": {}}]
    }
    fake_plugin.ctx.llm.generate = AsyncMock(return_value=fake_result)
    fake_plugin.ctx.config.get = AsyncMock(return_value="你是一个可爱的猫娘")

    executor = ReactionExecutor(fake_plugin)
    executor._send_back_poke = AsyncMock(return_value=True)
    executor._safe_send_text = AsyncMock(return_value=True)

    ctx = PokeContext()
    ctx.poker_id = "12345"
    ctx.poker_name = "群友"
    ctx.is_group = True
    ctx.group_id = "67890"

    ok = await executor._send_llm_reply(ctx, "stream_test", is_spam=False)
    assert ok is True
    # 验证执行了回戳
    executor._send_back_poke.assert_called_once()
    # 验证没有发送文字消息（落实 1B 自主静默权）
    executor._safe_send_text.assert_not_called()


@pytest.mark.asyncio
async def test_llm_reply_with_text_and_tool_call():
    """验证图文+回戳联动：大模型既调侃又回戳。"""
    fake_plugin = MagicMock()
    fake_plugin.config.reaction.min_delay_seconds = 0.0
    fake_plugin.config.reaction.max_delay_seconds = 0.0
    fake_plugin.config.reaction.llm_temperature = 0.7
    fake_plugin.config.reaction.llm_model = ""
    fake_plugin.config.reaction.llm_max_tokens = 0
    fake_plugin.config.reaction.llm_context_messages = 0
    fake_plugin.config.reaction.llm_persona = ""
    fake_plugin.config.reaction.llm_response_style = ""
    fake_plugin.record_poked_by_to_context = AsyncMock()

    fake_result = {
        "success": True,
        "response": "干嘛戳我啦！",
        "tool_calls": [{"name": "send_poke"}]
    }
    fake_plugin.ctx.llm.generate = AsyncMock(return_value=fake_result)
    fake_plugin.ctx.config.get = AsyncMock(return_value="你是一个可爱的猫娘")

    executor = ReactionExecutor(fake_plugin)
    executor._send_back_poke = AsyncMock(return_value=True)
    executor._safe_send_text = AsyncMock(return_value=True)

    ctx = PokeContext()
    ctx.poker_id = "12345"
    ctx.poker_name = "群友"
    ctx.is_group = True
    ctx.group_id = "67890"

    ok = await executor._send_llm_reply(ctx, "stream_test", is_spam=False)
    assert ok is True
    # 回戳与文本都正常发出
    executor._send_back_poke.assert_called_once()
    executor._safe_send_text.assert_called_once_with("干嘛戳我啦！", "stream_test")


@pytest.mark.asyncio
async def test_cooldown_counter_poke_2b():
    """验证 2B 冷却期动作反击保底：底层直接回戳打手反击。"""
    plugin = SmartPokePlugin()
    plugin._napcat = MagicMock()
    plugin._napcat.send_poke = AsyncMock(return_value=True)
    plugin.record_self_poke_to_context = AsyncMock()

    ctx = PokeContext()
    ctx.poker_id = "55555"
    ctx.poker_name = "连戳怪"
    ctx.is_group = True
    ctx.group_id = "88888"

    await plugin._send_cooldown_counter_poke(ctx)
    # 验证底层 send_poke 被调用
    assert plugin._napcat.send_poke.called
    plugin.record_self_poke_to_context.assert_called_once()


def test_parse_poke_details_adaptive_verbs_and_custom_suffixes():
    """验证自适应算法能无损解析『掐一掐/拍一拍/咬了一口/给了一拳』等任意动词与后缀。"""
    # 用例 1：带前缀的「掐一掐」
    payload1 = {
        "user_id": "10001",
        "target_id": "3843894500",
        "self_id": "3843894500",
        "raw_info": [
            {"type": "qq", "txt": "张三 "},
            {"type": "nor", "txt": "突然跑过来"},
            {"type": "nor", "txt": "掐一掐"},
            {"type": "qq", "txt": "麦麦"},
            {"type": "nor", "txt": "的小脸蛋"},
        ],
    }
    raw1, prefix1, verb1, full1, suffix1 = SmartPokePlugin._parse_poke_details(payload1)
    assert "张三" in raw1 and "掐一掐" in raw1 and "小脸蛋" in raw1
    assert prefix1 == "突然跑过来"
    assert verb1 == "掐一掐"
    assert suffix1 == "的小脸蛋"

    # 用例 2：「拍一拍」+ 主人的个性后缀
    payload2 = {
        "user_id": "10001",
        "target_id": "3843894500",
        "self_id": "3843894500",
        "raw_info": [
            {"type": "qq", "txt": "主人 "},
            {"type": "nor", "txt": "拍一拍"},
            {"type": "qq", "txt": "小小麦"},
            {"type": "nor", "txt": "的作业，说都交给我"},
        ],
    }
    raw2, prefix2, verb2, full2, suffix2 = SmartPokePlugin._parse_poke_details(payload2)
    assert verb2 == "拍一拍"
    assert suffix2 == "的作业，说都交给我"

    # 用例 3：「咬了一口」
    payload3 = {
        "user_id": "20002",
        "target_id": "3843894500",
        "self_id": "3843894500",
        "raw_info": [
            {"type": "qq", "txt": "小李 "},
            {"type": "nor", "txt": "咬了一口"},
            {"type": "qq", "txt": "麦麦"},
            {"type": "nor", "txt": "的奶茶"},
        ],
    }
    raw3, prefix3, verb3, full3, suffix3 = SmartPokePlugin._parse_poke_details(payload3)
    assert verb3 == "咬了一口"
    assert suffix3 == "的奶茶"

    # 用例 4：生僻第三方动作「给了一拳」
    payload4 = {
        "user_id": "30003",
        "target_id": "40004",
        "self_id": "3843894500",
        "raw_info": [
            {"type": "qq", "txt": "小赵 "},
            {"type": "nor", "txt": "给了一拳"},
            {"type": "qq", "txt": "小周"},
            {"type": "nor", "txt": "的胸口"},
        ],
    }
    raw4, prefix4, verb4, full4, suffix4 = SmartPokePlugin._parse_poke_details(payload4)
    assert verb4 == "给了一拳"
    assert suffix4 == "的胸口"


