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
