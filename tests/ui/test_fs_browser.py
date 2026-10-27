import pytest

from app.services.fs_browser import OutsideRootError, human_size, list_dir, resolve_inside


@pytest.fixture
def tree(tmp_path):
    (tmp_path / "b_dir").mkdir()
    (tmp_path / "A_dir").mkdir()
    (tmp_path / ".hidden").mkdir()
    (tmp_path / "z.tif").write_bytes(b"x" * 10)
    (tmp_path / "a.csv").write_text("id\n")
    (tmp_path / ".env").write_text("SECRET=1")
    return tmp_path


def test_folders_first_then_files_sorted_case_insensitive(tree):
    names = [e.name for e in list_dir(tree)]
    assert names == ["A_dir", "b_dir", "a.csv", "z.tif"]


def test_hidden_entries_are_skipped(tree):
    assert not any(e.name.startswith(".") for e in list_dir(tree))


def test_suffix_filter_keeps_folders(tree):
    names = [e.name for e in list_dir(tree, suffixes=(".tif",))]
    assert names == ["A_dir", "b_dir", "z.tif"]


def test_files_have_size_folders_do_not(tree):
    entries = {e.name: e for e in list_dir(tree)}
    assert entries["z.tif"].size == 10
    assert entries["A_dir"].size is None


def test_subfolder_listing(tree):
    (tree / "A_dir" / "dem.tif").write_text("")
    assert [e.name for e in list_dir(tree, "A_dir")] == ["dem.tif"]


def test_traversal_outside_root_is_refused(tree):
    with pytest.raises(OutsideRootError):
        list_dir(tree, "../")


def test_root_itself_is_allowed(tree):
    assert resolve_inside(tree, "") == tree.resolve()


def test_human_size():
    assert human_size(None) == ""
    assert human_size(512) == "512 B"
    assert human_size(1536) == "1.5 KB"
    assert human_size(5 * 1024**3) == "5.0 GB"
