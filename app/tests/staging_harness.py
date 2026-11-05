import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from app.editor.file_manager.staging import STAGING


def use_temporary_staging(case: unittest.TestCase, project_path: str = 'test.ltproj') -> None:
    """Gives a test a staging session in a temporary folder, as if it had loaded the
    project at project_path, and puts the editor's own staging back afterwards"""
    folder = tempfile.mkdtemp()
    case.addCleanup(shutil.rmtree, folder, ignore_errors=True)
    for patcher in (patch.object(STAGING, 'root', os.path.join(folder, 'staging')),
                    patch.object(STAGING, 'fallback_root', lambda: os.path.join(folder, 'fallback')),
                    patch.object(STAGING, 'project_name', STAGING.project_name),
                    patch.object(STAGING, 'cleaned', STAGING.cleaned)):
        patcher.start()
        case.addCleanup(patcher.stop)
    STAGING.start(project_path)
    case.addCleanup(STAGING.end)
