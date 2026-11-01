# CLAUDE.md - 智能戳一戳插件 (Smart Poke Plugin) (TAIY2020_smart_poke_plugin)

## 1. 模块定位与系统职责
- **插件标识符**：`TAIY2020_smart_poke_plugin`
- **当前生效版本**：`v1.8.4`
- **托管仓库**：[`Wenaixi/smart_poke_plugin`](https://github.com/Wenaixi/smart_poke_plugin)
- **核心定位**：拟人化 QQ 戳一戳互动插件，支持根据人设随口回戳、文字调侃与贴表情回应。

## 2. 关键工程规范与配置说明
- **配置路径**：`config.toml`（所有业务调优与鉴权参数收敛于此）；
- **数据持久化**：优先遵循 MaiBot SDK 标准持久化规范，不直接向源码目录写入易失数据；
- **编码与日志规范**：严格遵循 PEP 8 风格，文档与代码注释杜绝 emoji，避免虚假套话。

## 3. 本地深度定制与稳定性修复
- **原生 Agent 工具体系**：正式声明并暴露标准 `@Tool("send_poke", chat_scope="group")`，将回戳动作作为大模型一等公民工具；
- **彻底拔除伪随机抽签**：删除旧版 `_decide_reaction_kind` 随机概率掷骰子，合法被戳事件 100% 触发专属大模型进行智能体自主思考；
- **落实自主静默权 (1B)**：大模型可自主选择纯口头回怼、说话附带回戳、或仅调用 `send_poke` 工具静默回戳不发文字；
- **落实冷却期打手反击 (2B)**：8 秒逐人冷却期内连续被戳，不调用大模型 API（省 Token 防封号），底层直接快速回戳 1~2 次打手反击，防刷且绝不装死；
- **全量上下文成对入库**：被戳互动、回戳动作、调侃发言以及纯群友互戳（麦麦未跟风）事件均无损成对沉淀入 Maisaka 聊天上下文（`bystander_mutual`）。

---

## 上游项目与开源溯源
- **原作者 / 组织**：`TAIY2020`
- **官方上游仓库**：[https://github.com/TAIY2020/smart_poke_plugin](https://github.com/TAIY2020/smart_poke_plugin)
- **开源许可证**：`MIT`
- **分支演进模式**：本仓库作为主人的深度定制与生产维护分支（`Wenaixi/smart_poke_plugin`）。在保持与官方上游架构演进对齐的同时，锁死并持续维护针对本服务器生产环境的稳定性补丁与核心特性。
