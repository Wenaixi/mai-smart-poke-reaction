import sys, types
from pathlib import Path

plugin_root = Path(__file__).resolve().parent.parent
if str(plugin_root.parent) not in sys.path:
    sys.path.insert(0, str(plugin_root.parent))
if str(plugin_root) not in sys.path:
    sys.path.insert(0, str(plugin_root))

if "maibot_sdk" not in sys.modules:
    sdk = types.ModuleType("maibot_sdk")
    sdk.__path__ = []
    sdk.MaiBotPlugin = type("MaiBotPlugin", (), {})
    sdk.Field = lambda default=None, **kwargs: kwargs.get("default_factory", lambda: default)() if "default_factory" in kwargs else default
    sdk.PluginConfigBase = type("PluginConfigBase", (), {})
    sdk.Command = lambda *a, **k: (lambda f: f)
    sdk.HookHandler = lambda *a, **k: (lambda f: f)
    sdk.Tool = lambda *a, **k: (lambda f: f)
    sdk.Action = lambda *a, **k: (lambda f: f)
    sys.modules["maibot_sdk"] = sdk

if "maibot_sdk.types" not in sys.modules:
    types_mod = types.ModuleType("maibot_sdk.types")
    types_mod.ErrorPolicy = type("ErrorPolicy", (), {"SKIP": "skip", "RAISE": "raise"})
    types_mod.HookMode = type("HookMode", (), {"BLOCKING": "blocking", "OBSERVE": "observe"})
    types_mod.HookOrder = type("HookOrder", (), {"EARLY": "early", "NORMAL": "normal", "LATE": "late"})
    class _TPI:
        def __init__(self, name="", param_type="string", description="", required=True, enum_values=None):
            self.name = name
            self.param_type = param_type
            self.description = description
            self.required = required
            self.enum_values = enum_values or []
    types_mod.ToolParameterInfo = _TPI
    types_mod.ToolParamType = type("ToolParamType", (), {"STRING": "string", "INTEGER": "integer", "BOOLEAN": "boolean", "FLOAT": "float", "NUMBER": "number"})
    sys.modules["maibot_sdk.types"] = types_mod
