"""Tests for swatprep.qa — QACheck primitives."""

from swatprep.qa import QACheck, all_pass, failures, warnings


def test_pass_check_is_ok():
    c = QACheck(name="test", status="pass", message="ok")
    assert c.is_ok() is True


def test_warn_check_is_ok():
    c = QACheck(name="test", status="warn", message="minor issue")
    assert c.is_ok() is True


def test_fail_check_is_not_ok():
    c = QACheck(name="test", status="fail", message="error")
    assert c.is_ok() is False


def test_failures_filters_correctly():
    checks = [
        QACheck("a", "pass", "ok"),
        QACheck("b", "fail", "bad"),
        QACheck("c", "warn", "minor"),
        QACheck("d", "fail", "also bad"),
    ]
    assert [c.name for c in failures(checks)] == ["b", "d"]


def test_warnings_filters_correctly():
    checks = [
        QACheck("a", "pass", "ok"),
        QACheck("b", "warn", "minor"),
        QACheck("c", "fail", "bad"),
    ]
    assert [c.name for c in warnings(checks)] == ["b"]


def test_all_pass_with_no_failures():
    checks = [QACheck("a", "pass", "ok"), QACheck("b", "warn", "minor")]
    assert all_pass(checks) is True


def test_all_pass_false_when_failure_present():
    checks = [QACheck("a", "pass", "ok"), QACheck("b", "fail", "bad")]
    assert all_pass(checks) is False


def test_qa_check_as_dict():
    c = QACheck("test", "pass", "ok", context={"key": "val"})
    d = c.as_dict()
    assert d == {"name": "test", "status": "pass", "message": "ok", "context": {"key": "val"}}


def test_all_pass_on_empty_list():
    assert all_pass([]) is True
