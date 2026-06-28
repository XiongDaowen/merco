"""Pipeline 处理器外移回归测试"""


def test_result_processors_import_from_new_locations():
    from merco.tools.processors.truncation import TruncationProcessor
    from merco.skills.processors import SkillViewProcessor

    assert TruncationProcessor.__name__ == "TruncationProcessor"
    assert SkillViewProcessor.__name__ == "SkillViewProcessor"
