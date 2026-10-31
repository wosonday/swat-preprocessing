from importlib.metadata import version

import swatprep


def test_version_matches_installed_metadata():
    assert swatprep.__version__ == version("swatprep")
