"""Pipeline 处理器外移回归测试"""


def test_result_processors_import_from_new_locations():
    from merco.skills.processors import SkillViewProcessor
    from merco.tools.processors.truncation import TruncationProcessor

    assert TruncationProcessor.__name__ == "TruncationProcessor"
    assert SkillViewProcessor.__name__ == "SkillViewProcessor"


def test_recoveries_import_from_new_locations():
    from merco.context.recovery import ContextCompressRecovery
    from merco.core.recovery.model_fallback import ModelFallbackRecovery
    from merco.core.recovery.wait import WaitRecovery
    from merco.tools.recovery import ToolReduceRecovery

    assert WaitRecovery.__name__ == "WaitRecovery"
    assert ContextCompressRecovery.__name__ == "ContextCompressRecovery"
    assert ToolReduceRecovery.__name__ == "ToolReduceRecovery"
    assert ModelFallbackRecovery.__name__ == "ModelFallbackRecovery"
