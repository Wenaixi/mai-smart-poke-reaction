from types import SimpleNamespace
from TAIY2020_smart_poke_plugin.core.state import PokeContext
from TAIY2020_smart_poke_plugin.core.reaction import ReactionExecutor
from TAIY2020_smart_poke_plugin.plugin import SmartPokePlugin


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
