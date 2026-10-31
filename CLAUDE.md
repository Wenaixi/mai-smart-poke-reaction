# TAIY2020 smart poke plugin

## 官方上游与版本溯源
- 官方仓库（Upstream Repository）：https://github.com/TAIY2020/smart_poke_plugin
- 官方作者（Author / Maintainer）：TAIY2020
- 功能定位：智能戳一戳反应与动作生成插件
- 本地演进定位：基于官方上游最新版本，融入本地生产环境兼容性定制与稳定性加固。
- 本地专属定制：本地深度排查定位并修复隐蔽展开式 model= 传参问题，确保戳一戳 LLM 回复正常。


## 插件基本信息

- 插件 ID：`TAIY2020.smart_poke_plugin`
- 频率：high
- 描述：戳一戳插件（被动响应戳）

## 主要功能 / 配置要点

- hook timeout 5000ms (ab3bd5b)
- proactive task queue limit
- except:pass 已改为 logger.debug (cf177a1)

## 接入依赖

- MaiBot SDK 2.x（`MaiBotPlugin` 基类 + `Action`/`Command`/`HookHandler`）
- 容器内一律用服务名（`napcat` / `core`），禁止 `127.0.0.1`
- 配置通过 `PluginConfigBase`（Pydantic v2）

## 关键日志（启动标志）

插件加载时输出 `xxx 已加载`。如未加载，参考 MaiBot 启动日志 `已加载=N 失败=M 未激活=K`。

## 用法

由 MaiBot LLM 自主调用或通过命令触发。详见 plugin 文档或上游 README。

## 历史脚注

- 2026-08-15：自动生成（深度 plan B10）
- 本仓库是主人本地副本，服务器 `/MaiBot/plugins/` 是 runtime。
- 修改走工作流（本机改 → 本机 commit → 部署服务器 → 验证加载）。

- 2026-10-31: 彻底移除固定回复词库，优化提示词植入 QQ 戳一戳轻量社交认知
  - **背景**：根据主人要求，彻底取消戳一戳中死板生硬的预设文本（如"何意味"、"干啥"、"好烦"、"停！手！"等）；同时优化提示词，向模型解释戳一戳只是 QQ 的轻量社交小功能（打招呼/拍肩提醒/顺手提到某人），并不带恶意或攻击性，引导麦麦按真实人设自然随口回应。
  - **改动**：
    1. 移除 `core/reaction.py` 中的 `_send_text` 静态回复抽取逻辑，决策树移除 `text` 分支，言语回应 100% 交由 LLM 动态生成；
    2. 任何异常与软失败级联降级统一回退到自然回戳（`_send_back_poke`），不再喷出预设词；
    3. 清空 `config.toml` 与 `config.example.toml` 中的 `[fallback]` 词库，将 `text_weight` 降为 0.0，调优 `llm_weight=0.4`、`back_poke_weight=0.6`；
    4. 重构 `_build_llm_prompt`，明确灌注功能认知，约束回复为 3~20 字内简短白话随口一回。
  - **验证**：新增单元测试 2 项全绿。

- 2026-10-31: 深度支持 QQ 原生个性化戳一戳（发起者动作前缀 + 谓语 + 麦麦个性后缀）
  - **背景**：针对主人提出的个性化戳一戳（如"真人机麦麦 欢迎加入信息社生活部!拍了拍准大一姜丝丝,努力学习只为回家的睡个好觉吃个水饺"），排查发现原适配器与插件硬编码只截取索引 2 与 4，或在首个 nor 处截断，丢失了动作修饰与搞笑后缀。
  - **改动**：
    1. `core/state.py`：PokeContext 增加 `raw_text`、`action_prefix`、`action_verb`、`target_suffix` 和 `my_suffix`；
    2. `plugin.py`：实现 `_parse_poke_details`，无损组合系统原话并结构化提取三要素；
    3. `core/reaction.py`：重构 `_build_llm_prompt`，向大模型灌注【QQ系统通知原文】与【个性化后缀提示】，引导麦麦敏锐捕捉对方触发的部位或设定（如水饺、生活部）自然调侃随口一回。
  - **验证**：新增端到端全量字段与 Prompt 注入测试用例，pytest 100% 通过。
