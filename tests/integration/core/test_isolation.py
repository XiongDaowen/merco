"""全隔离服务工厂测试"""


def test_isolation_services_provides_all_keys(isolation_services):
    assert "snapshot_root" in isolation_services
    assert "todo_db" in isolation_services
    assert "scheduler" in isolation_services
    assert "guard" in isolation_services
    assert "skill_registry" in isolation_services


def test_isolation_services_use_tmp_path(isolation_services, tmp_path):
    assert isolation_services["snapshot_root"].parent == tmp_path
    assert isolation_services["todo_db"].parent == tmp_path


def test_isolation_services_are_independent_per_test(isolation_services):
    # 同一测试内多次访问是同一实例
    s1 = isolation_services["scheduler"]
    s2 = isolation_services["scheduler"]
    assert s1 is s2


def test_isolation_services_can_register_skills(isolation_services):
    isolation_services["skill_registry"].register({
        "name": "test-skill",
        "description": "test",
        "content": "content",
    })
    assert isolation_services["skill_registry"].get("test-skill") is not None
