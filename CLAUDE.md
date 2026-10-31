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
打破硬编码索引，无损还原 QQ 原生个性化原话（发起者动作修饰 + 动词 + 麦麦个性后缀），注入真实调侃提示词；彻底拔除死板固定回复。

---

## 上游项目与开源溯源
- **原作者 / 组织**：`TAIY2020`
- **官方上游仓库**：[https://github.com/TAIY2020/smart_poke_plugin](https://github.com/TAIY2020/smart_poke_plugin)
- **开源许可证**：`MIT`
- **分支演进模式**：本仓库作为主人的深度定制与生产维护分支（`Wenaixi/smart_poke_plugin`）。在保持与官方上游架构演进对齐的同时，锁死并持续维护针对本服务器生产环境的稳定性补丁与核心特性。
