"""反应执行器：戳到麦麦后的反应主流程。

被 ``SmartPokePlugin.handle_poke_event`` 在 ``react_probability`` 命中后调用。
按权重抽样回戳 / 表情 / 文字三种反应；任意路径失败按既定级联回退避免 mark_reacted
了却什么都没发的尴尬。

同时持有 ``silent_reply``——``react_probability`` 未命中时按 ``silent_chat_probability``
偶尔挤一句沉默回复池。
"""

from __future__ import annotations

import asyncio
import random
import re
from typing import TYPE_CHECKING, Any

from .state import PokeContext


if TYPE_CHECKING:
    from ..plugin import SmartPokePlugin


# llm_persona 留空且全局人设读取失败时的最终兜底，与 Host 默认人设保持一致。
_DEFAULT_LLM_PERSONA = "你是一个大二女大学生，现在正在上网和群友聊天。"


class ReactionExecutor:
    """戳到麦麦后的反应主流程。"""

    def __init__(self, plugin: "SmartPokePlugin") -> None:
        self._plugin = plugin

    # ===== 公开入口 =====

    async def silent_reply(self, ctx: PokeContext) -> None:
        """``react_probability`` 未命中时按 ``silent_chat_probability`` 概率挤一句。

        冷却在"确认能挤出一句话"后才消耗（解析 stream_id 成功且回复池非空），
        避免 stream_id 解析失败 / 池为空时白白冷却用户。
        """
        plugin = self._plugin
        try:
            stream_id = await plugin.resolve_stream_id_for_context(ctx, allow_open=True)
            if not stream_id:
                plugin.ctx.logger.debug(
                    "[silent_reply] 无法解析 stream_id (group=%s, poker=%s)，静默放弃",
                    ctx.group_id, ctx.poker_id,
                )
                return
            pool = plugin.config.fallback.silent_replies
            if not pool:
                plugin.ctx.logger.debug("[silent_reply] silent 回复池为空，按沉默语义放弃发送")
                return
            # 二次确认滑动窗口 + 逐人冷却：silent_reply 的 mark 在后台任务里执行，
            # 与正常命中分支（mark 在主链同步完成）之间存在窗口，并发事件可能在此期间
            # 填满频率窗口、或抢先对同一人 mark 冷却。这里在 mark 前各补一次确认；
            # peek / in_cooldown / mark 三者连续同步执行（中间无 await），原子地占用冷却，
            # 避免与正常反应或另一次 silent_reply 撞车双发。
            max_per_minute = plugin.config.reaction.max_reactions_per_minute
            if max_per_minute > 0 and plugin._state.peek_reaction_window(ctx.cooldown_key, 60) >= max_per_minute:
                plugin.ctx.logger.debug(
                    "[silent_reply] 派发到 mark 之间窗口被填满，静默放弃 (poker=%s)",
                    ctx.poker_id,
                )
                return
            if plugin._state.in_cooldown(
                ctx.cooldown_key, ctx.poker_id, plugin.config.reaction.cooldown_seconds
            ):
                plugin.ctx.logger.debug(
                    "[silent_reply] 派发到 mark 之间已进入冷却，静默放弃 (poker=%s)",
                    ctx.poker_id,
                )
                return
            react_token = plugin._state.mark_reacted(ctx.cooldown_key, ctx.poker_id)
            await self._delay_a_bit()
            # 同 react_to_poke：延迟后确认未被同一人更晚的反应取代，避免连戳叠加嘀咕
            if self._superseded(ctx, react_token, "silent_reply"):
                return
            # 确认会真正嘀咕一句后才记"对方戳了我"前因，与 react_to_poke 各档口径一致：
            # 被取代而放弃的任务不写入，避免上下文堆叠多条"X戳了戳我"。
            await plugin.record_poked_by_to_context(ctx)
            await self._safe_send_text(random.choice(pool), stream_id)
        except Exception:
            plugin.ctx.logger.exception("silent_reply 发送失败")

    async def react_to_poke(
        self,
        ctx: PokeContext,
        is_spam: bool,
        poke_count: int,
        react_token: float | None = None,
    ) -> None:
        """戳到麦麦后的反应主流程：抽样 → 延迟 → 四档回复（poke/emoji/text/llm）+ 级联回退。

        ``react_token`` 为主链 ``mark_reacted`` 返回的时间戳；延迟结束、真正发送前用它
        二次确认本次反应未被同一人更晚的戳取代（``max_delay_seconds > cooldown_seconds``
        时同一人连戳会各派发一个反应任务），被取代则放弃发送，避免两条回复叠着发出。
        """
        plugin = self._plugin
        try:
            stream_id = await plugin.resolve_stream_id_for_context(ctx, allow_open=True)
            if not stream_id:
                plugin.ctx.logger.debug(
                    "[smart_poke] 无法解析 stream_id (group=%s, poker=%s)，静默放弃响应",
                    ctx.group_id, ctx.poker_id,
                )
                return

            plugin.ctx.logger.info(
                "[smart_poke] 交付大模型智能体自主决策: is_spam=%s, poke_count=%d, poker=%s, scene=%s",
                is_spam,
                poke_count,
                ctx.poker_name or ctx.poker_id,
                "群聊" if ctx.is_group else "私聊",
            )

            # 彻底拔除死板随机加权抽签与百分百强制回戳：完全交付大模型自主心智决策（支持说话、回戳、无声回戳、或淡定不理睬）
            await self._send_llm_reply(ctx, stream_id, is_spam, react_token)
        except Exception:
            plugin.ctx.logger.exception("反应戳一戳时出错")

    # ===== 内部：延迟与抽样 =====

    async def _delay_a_bit(self) -> None:
        cfg = self._plugin.config.reaction
        lo = max(0.0, cfg.min_delay_seconds)
        hi = max(lo, cfg.max_delay_seconds)
        delay = random.uniform(lo, hi) if hi > 0 else 0
        if delay > 0:
            await asyncio.sleep(delay)

    def _superseded(
        self, ctx: PokeContext, react_token: float | None, label: str
    ) -> bool:
        """延迟后、发送前的二次确认：本次反应是否已被同一人更晚的戳取代。

        命中时打 debug 并返回 ``True``，调用方据此放弃发送，规避
        ``max_delay_seconds > cooldown_seconds`` 时同一人连戳叠加回复。
        ``react_token`` 为 ``None``（理论上不会，仅作防御）时视为未被取代。
        """
        if react_token is None:
            return False
        if self._plugin._state.is_reaction_superseded(
            ctx.cooldown_key, ctx.poker_id, react_token
        ):
            self._plugin.ctx.logger.debug(
                "[%s] 反应在思考延迟期间被同一人更新的戳取代，放弃本次发送 (poker=%s)",
                label, ctx.poker_id,
            )
            return True
        return False

    # ===== 内部：发送实现 =====

    async def _send_back_poke(
        self, ctx: PokeContext, is_spam: bool = False, stream_id: str = ""
    ) -> bool:
        """通过 NapCat 适配器发送回戳，支持多次连续戳。

        防自戳死循环：ignore_self_poke=False 时若让麦麦回戳自己，新的 send_poke
        会再触发一条 notify.poke 被本插件接收，导致无限循环。

        每两次之间 0.3~0.8s 随机短延迟避免请求扎堆触发风控；
        任一中途失败立即停止（可能已被风控）。
        """
        plugin = self._plugin
        if ctx.poker_id == ctx.self_id:
            plugin.ctx.logger.warning(
                "拒绝回戳麦麦自己（self_id=%s）以避免戳一戳事件死循环", ctx.self_id,
            )
            return False

        max_times = max(1, plugin.config.reaction.back_poke_max_times)
        times = max_times if is_spam else random.randint(1, max_times)

        any_success = False
        for i in range(times):
            ok = await plugin._napcat.send_poke(
                ctx.poker_id, ctx.group_id, is_group=ctx.is_group, label="back_poke"
            )
            if ok:
                any_success = True
            else:
                break
            if i < times - 1:
                await asyncio.sleep(random.uniform(0.3, 0.8))

        if times > 1 and any_success:
            plugin.ctx.logger.debug(
                "[back_poke] 连戳 %d 次 (is_spam=%s, max=%d)",
                times, is_spam, max_times,
            )
        # 连戳成功 N 次只注入一条，避免 Replyer 上下文里堆 N 条「我回戳了 X」噪音
        if any_success:
            await plugin.record_self_poke_to_context(
                label="back_poke",
                target_id=ctx.poker_id,
                target_name=ctx.poker_name,
                group_id=ctx.group_id,
                is_group=ctx.is_group,
                # 复用 react_to_poke 已解析（含冷群 open_session）的 stream_id，
                # 避免 record 内部按 ctx.stream_id（notify 路径常为空）再回查一次；
                # 解析失败时退回 ctx.stream_id，与原行为一致。
                stream_id=stream_id or ctx.stream_id,
            )
        return any_success

    def _context_sync_kwargs(self) -> dict[str, Any]:
        """开启「写入上下文」时，让 ctx.send 把这条回复按 Host 标准聊天记录格式
        （带说话人前缀、等同麦麦正常发言）同步进 maisaka 历史，而非旁白式系统事件；
        关闭时返回空 dict，发送行为不变。仅在该会话已有活跃 runtime 时 Host 才会记入。
        """
        if self._plugin.config.plugin.record_self_poke_to_context:
            return {"sync_to_maisaka_history": True, "maisaka_source_kind": "smart_poke"}
        return {}

    async def _safe_send_text(self, text: str, stream_id: str) -> bool:
        try:
            # ctx.send.text 在发送业务失败时返回 False（不抛异常），必须接住返回值，
            # 否则级联回退（文字失败→回退回戳）会因误判成功而失效。
            # 开启写入上下文时透传 sync 参数，让 Host 以正常聊天记录格式记入这条回复
            # （覆盖文字 / LLM / 沉默档，都走本方法发送）。
            ok = await self._plugin.ctx.send.text(text, stream_id, **self._context_sync_kwargs())
            return bool(ok)
        except Exception:
            self._plugin.ctx.logger.exception("发送文字回复失败")
            return False

    async def _send_emoji(self, stream_id: str) -> bool:
        """发送一张表情包。Host 序列化表情时固定输出 ``base64`` 字段。"""
        plugin = self._plugin
        try:
            emoji = await plugin._emoji.pick_emoji()
            if not isinstance(emoji, dict):
                return False

            emoji_data = emoji.get("base64")
            if not isinstance(emoji_data, str) or not emoji_data:
                return False

            # 同 _safe_send_text：emoji 发送失败时 ctx.send.emoji 返回 False 而非抛异常，
            # 接住返回值才能让 react_to_poke 正确回退到回戳/文字。
            # 开启写入上下文时透传 sync 参数，让 Host 以正常聊天记录格式记入这条表情。
            ok = await plugin.ctx.send.emoji(emoji_data, stream_id, **self._context_sync_kwargs())
            return bool(ok)
        except Exception:
            plugin.ctx.logger.exception("发送表情失败")
            return False

    # ===== 内部：LLM 反应档 =====

    async def _send_llm_reply(
        self,
        ctx: PokeContext,
        stream_id: str,
        is_spam: bool,
        react_token: float | None = None,
    ) -> bool:
        """调 ``ctx.llm.generate`` 生成一句拟人回复并发出（不走主链路）。

        思考延迟与生成 ``asyncio.gather`` 并行，让生成耗时被"装作在思考"的时间吸收：
        净增延迟 ≈ ``max(0, 生成耗时 − 思考延迟)``，命中时体感与回复池秒回基本一致。

        任何失败（RPC 异常 / 业务 success=False / 空响应 / 发送失败）都返回 ``False``，
        交由 ``react_to_poke`` 级联回退到回复池或回戳，避免 mark 了却什么都没发。
        """
        plugin = self._plugin
        cfg = plugin.config.reaction

        lo = max(0.0, cfg.min_delay_seconds)
        hi = max(lo, cfg.max_delay_seconds)
        delay = random.uniform(lo, hi) if hi > 0 else 0.0

        POKE_TOOLS = [
            {
                "type": "function",
                "function": {
                    "name": "send_poke",
                    "description": "向当前群聊中戳麦麦的用户发送 QQ 官方戳一戳互动动作（用于趣味打招呼、提醒对方、反击或随口逗趣，非物理触碰）。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "target_id": {
                                "type": "string",
                                "description": "要戳的用户 QQ 号，可留空（默认回戳当前互动对象）",
                            }
                        },
                    },
                },
            }
        ]

        async def _prepare_and_generate() -> Any:
            persona = await self._resolve_persona()
            context_text = await self._fetch_recent_context(stream_id)
            prompt = self._build_llm_prompt(ctx, is_spam, persona, context_text)
            gen_kwargs: dict[str, Any] = {
                "prompt": prompt,
                "temperature": cfg.llm_temperature,
                "tools": POKE_TOOLS,
            }
            model = cfg.llm_model.strip()
            if model:
                gen_kwargs["task_name"] = model
            if cfg.llm_max_tokens > 0:
                gen_kwargs["max_tokens"] = cfg.llm_max_tokens
            return await plugin.ctx.llm.generate(**gen_kwargs)

        try:
            _, result = await asyncio.gather(
                asyncio.sleep(delay),
                _prepare_and_generate(),
            )
        except Exception:
            plugin.ctx.logger.debug("[llm] 生成链调用异常，回退到底层回戳", exc_info=True)
            return False

        tool_calls = self._extract_tool_calls(result)
        text = self._extract_llm_text(result)

        called_send_poke = any(
            (tc.get("name") in ("send_poke", "poke") if isinstance(tc, dict) else False)
            or (tc.get("function", {}).get("name") in ("send_poke", "poke") if isinstance(tc, dict) and isinstance(tc.get("function"), dict) else False)
            for tc in tool_calls
        )

        # 若大模型输出无视或主动留空（且未调工具），属于自主决定不理睬，尊重模型意愿保持静默，绝不强制回退回戳
        if text.strip() in ("不理睬", "无视", "忽略", "[不理睬]", "[无视]", "[忽略]", "pass", "ignore"):
            text = ""

        if not text and not called_send_poke:
            if isinstance(result, dict) and result.get("success") is not False:
                plugin.ctx.logger.info("[llm] 大模型自主决定不予理睬本次戳一戳（普通小功能而已），淡定保持静默")
                return True
            plugin.ctx.logger.debug("[llm] 生成失败或异常，回退到底层回戳")
            return False

        if self._superseded(ctx, react_token, "llm"):
            return True

        # 确认未被连戳取代，记入"对方戳了我"前因
        await plugin.record_poked_by_to_context(ctx)

        # 执行回戳动作（来自模型决策的工具调用）
        if called_send_poke:
            await self._send_back_poke(ctx, is_spam=is_spam, stream_id=stream_id)

        # 发送调侃正文（落实 1B 自主静默权：若模型只调用回戳工具而不发文字，则 text 为空不发消息）
        if text:
            ok = await self._safe_send_text(text, stream_id)
            if ok:
                plugin.ctx.logger.info("[llm] 已发送生成回复: %r (is_spam=%s, called_poke=%s)", text, is_spam, called_send_poke)
            return ok

        # 若模型仅调用回戳工具（无文本正文），到此处回戳已完成，直接返回 True（达成 1B 自主静默权）
        plugin.ctx.logger.info("[llm] 模型选择仅调用 send_poke 回戳而不发文字 (落实自主静默权 1B)")
        return True

    async def _fetch_recent_context(self, stream_id: str) -> str:
        """按 ``reaction.llm_context_messages`` 拉取最近聊天记录并格式化为可读文本。

        默认 0：不拉历史，返回空串（戳一戳作为独立轻量交互，压低首 token 延迟，
        与原行为一致）。>0 时用 ``message.get_recent`` + ``message.build_readable``
        拉取最近若干条并格式化，让被戳回复能接住群里 / 对话正在聊的话题。

        这两次 RPC 在 ``_send_llm_reply`` 的思考延迟 / 生成 gather **之前**串行，
        故仅在用户主动开启（>0）时才付出这点拉取延迟；任一步失败一律降级为空串，
        绝不影响主回复生成。
        """
        cfg = self._plugin.config.reaction
        try:
            limit = int(getattr(cfg, "llm_context_messages", 0) or 0)
        except (ValueError, TypeError):
            limit = 0
        if limit <= 0 or not stream_id:
            return ""
        ctx = self._plugin.ctx
        try:
            recent = await ctx.message.get_recent(stream_id, limit=limit)
        except Exception:
            ctx.logger.debug("[llm] 拉取上下文消息失败 (stream=%s)", stream_id, exc_info=True)
            return ""
        if not isinstance(recent, list) or not recent:
            return ""
        try:
            # build_readable 输出带说话人名 / 相对时间的标准聊天记录串，并自动替换 bot 名。
            readable = await ctx.message.build_readable(recent, timestamp_mode="relative")
        except Exception:
            ctx.logger.debug("[llm] 格式化上下文消息失败 (stream=%s)", stream_id, exc_info=True)
            return ""
        return readable.strip() if isinstance(readable, str) else ""

    async def _resolve_persona(self) -> str:
        """解析 LLM 人设：插件显式配置 > 麦麦全局人设 > 兜底。

        留空 ``llm_persona`` 时自动读 Host 全局 ``personality.personality``——
        ``ctx.config.get`` 在本 Host 实为读宿主全局配置（见 _cap_config_get，
        ``_get_nested_config_value(global_config, key)``），而非插件自身 config，
        故能直接拿到麦麦人设，让戳一戳与主聊天语气一致；读取失败再回落到与 Host
        默认一致的兜底人设。
        """
        raw_configured = getattr(self._plugin.config.reaction, "llm_persona", "")
        configured = str(raw_configured or "").strip()
        if configured:
            return configured
        try:
            global_persona = await self._plugin.ctx.config.get("personality.personality", "")
        except Exception:
            self._plugin.ctx.logger.debug("[llm] 读取全局人设失败，使用兜底人设", exc_info=True)
            global_persona = ""
        if isinstance(global_persona, str) and global_persona.strip():
            return global_persona.strip()
        return _DEFAULT_LLM_PERSONA

    def _build_llm_prompt(
        self, ctx: PokeContext, is_spam: bool, persona: str, context_text: str = ""
    ) -> list[dict[str, str]]:
        """组装更自然生动的 prompt：明确说明戳一戳是 QQ 轻量提醒/打招呼功能，引导模型按真实人设随口回复。"""
        scene = "群聊" if ctx.is_group else "私聊"
        poker = (ctx.poker_name or "").strip() or "有人"
        action = (ctx.poke_action or "").strip() or "戳了戳"

        raw_info_block = ""
        if ctx.raw_text:
            raw_info_block = f"【QQ系统通知原文】「{ctx.raw_text}」\n"

        personalized_block = ""
        if ctx.my_suffix:
            personalized_block = (
                f"【个性化后缀提示】对方触发了你的 QQ 戳一戳个性后缀「{ctx.my_suffix}」。"
                "你可以顺着这个有趣的部位、动作或搞笑设定自然调皮地随口调侃一句。\n"
            )
        elif ctx.target_suffix:
            personalized_block = f"【个性化后缀】本次戳一戳带有后缀「{ctx.target_suffix}」。\n"

        if ctx.action_prefix:
            personalized_block += f"【动作修饰】对方带有自定义动作前缀「{ctx.action_prefix}」。\n"

        system = (
            f"{persona}\n\n"
            f"【功能认知】在 QQ {scene}中，「戳一戳」（双击对方头像，系统提示「{poker} {action}了你」）只是 QQ 里的一个非常普通平常、随处可见的日常小功能，用于轻量提醒或无聊随手点一下，没什么大不了的，绝对不要大惊小怪或过度反应。"
            "使用「send_poke」工具即可实现回戳互动。\n"
            f"{raw_info_block}"
            f"{personalized_block}"
            f"现在「{poker}」在 {scene}里随手戳了你一下。\n"
            "你有完全自主的决定权，不要每次都一本正经回复，反应不要太大：\n"
            "1. 【淡定不理睬】：完全可以不理睬（直接输出空内容，假装没看见，不发文字也不回戳）；\n"
            "2. 【随手回戳】：如果想打招呼或随手互动，在后台调用「send_poke」工具即可；\n"
            "3. 【淡定随口调侃】：若当前聊天氛围适合且有话想说，随口回一句极简口语（3~15字内，像真人一样淡定随和，严禁大惊小怪或质问）；\n"
            "4. 想要回戳直接在后台调用工具即可，严禁在回复文字中添加『（回戳）』或任何动作括号旁白！"
        )
        style = self._plugin.config.reaction.llm_response_style.strip()
        if style:
            system += f"\n额外回复风格要求：{style}"
        if context_text:
            system += (
                "\n\n这是最近的聊天记录，仅供你了解当前氛围，不要直接回复其中的内容：\n"
                f"{context_text}"
            )

        notice_hint = f"（系统原文：{ctx.raw_text}）" if ctx.raw_text else f"（动作：{action}）"
        function_hint = "（QQ普通小功能，用于提醒或随手互动，可调用 send_poke 或不理睬）"
        if is_spam:
            user = f"「{poker}」连续多次{action}你{notice_hint}{function_hint}，反应不要太大，随口吐槽一句或随手反戳一下。"
        else:
            user = f"「{poker}」在{scene}里随手戳了你一下{notice_hint}{function_hint}。反应不要太大，可以淡定调侃、随手回戳、或干脆不理睬。"

        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

    @staticmethod
    def _extract_llm_text(result: Any) -> str:
        """从 generate 返回值取出回复文本；失败信封 / 空响应一律返回空串。"""
        if not isinstance(result, dict):
            return ""
        # 业务失败时 Host 返回 {"success": False, ...}，没有有效 response
        if result.get("success") is False:
            return ""
        text = str(result.get("response") or "").strip()
        if not text:
            return ""
        # LLM 偶尔把整句用成对引号包起来，剥一层让回复更像随口一说
        if len(text) >= 2 and text[0] in "\"'“「『" and text[-1] in "\"'”」』":
            text = text[1:-1].strip()
        return text

    @staticmethod
    def _extract_tool_calls(result: Any) -> list[dict[str, Any]]:
        """从 generate 返回值中提取 tool_calls 列表。"""
        if not isinstance(result, dict):
            return []
        calls = result.get("tool_calls") or result.get("tool_call") or result.get("function_call")
        if isinstance(calls, list):
            return [c for c in calls if isinstance(c, dict)]
        if isinstance(calls, dict):
            return [calls]
        return []
