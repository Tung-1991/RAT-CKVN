# -*- coding: utf-8 -*-
import shutil
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def cleanup_repo_test_account():
    repo_root = Path(__file__).resolve().parents[1]
    artifact = repo_root / "data" / "TEST_ACCOUNT"
    if artifact.exists():
        shutil.rmtree(artifact)
    yield
    if artifact.exists():
        shutil.rmtree(artifact)
