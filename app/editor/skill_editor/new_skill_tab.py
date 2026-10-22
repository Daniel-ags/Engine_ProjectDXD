from __future__ import annotations

from typing import Optional
import os

from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QFileDialog
from app.editor.settings.main_settings_controller import MainSettingsController

import app.engine.skill_component_access as SCA
from app.data.database.skills import SkillCatalog, SkillPrefab
from app.editor.edit_history import HISTORY
from app.data.database.database_types import DatabaseType as DType
from app.editor import reference_dialogs, timer
from app.editor.new_editor_tab import NewEditorTab
from app.editor.data_editor import SingleDatabaseEditor
from app.editor.component_editor_properties import NewComponentProperties, component_search_text
from app.editor.skill_editor import skill_model, skill_import
from app.editor.custom_widgets import SkillBox

from app.utilities.typing import NID


class NewSkillProperties(NewComponentProperties[SkillPrefab]):
    title = "Skill"
    get_components = staticmethod(SCA.get_skill_components)
    get_templates = staticmethod(SCA.get_templates)
    get_tags = staticmethod(SCA.get_skill_tags)


class NewSkillDatabase(NewEditorTab):
    catalog_type = SkillCatalog
    properties_type = NewSkillProperties

    @classmethod
    def edit(cls, parent=None):
        timer.get_timer().stop_for_editor()  # Don't need these while running game
        window = SingleDatabaseEditor(NewSkillDatabase, parent)
        window.exec_()
        timer.get_timer().start_for_editor()

    @property
    def data(self):
        return self._db.skills

    def get_icon(self, skill_nid) -> Optional[QIcon]:
        pix = skill_model.get_pixmap(self.data.get(skill_nid))
        if pix:
            return QIcon(pix.scaled(32, 32))
        return None

    def get_search_text(self, nid: NID) -> str:
        return component_search_text(self.data.get(nid))

    def _on_delete(self, nid: NID) -> bool:
        """
        Returns whether the user wants to proceed with deletion
        """
        return reference_dialogs.check_delete(DType.SKILLS, nid, 'Skill',
                                              self, lambda: SkillBox(self, exclude=self.data.get(nid)))

    def _on_nid_changed(self, old_nid: NID, new_nid: NID) -> None:
        HISTORY.rewrite(DType.SKILLS, old_nid, new_nid)

    def import_xml(self):
        settings = MainSettingsController()
        starting_path = settings.get_last_open_path()
        fn, ok = QFileDialog.getOpenFileName(self, _("Import skills from status.xml"), starting_path, "Status XML (status.xml);;All Files(*)")
        if ok and fn.endswith('status.xml'):
            parent_dir = os.path.split(fn)[0]
            settings.set_last_open_path(parent_dir)
            new_skills = skill_import.get_from_xml(parent_dir, fn)
            for skill in new_skills:
                self.data.append(skill)
            self.reset()

    def import_csv(self):
        return

# Testing
# Run "python -m app.editor.skill_editor.new_skill_tab" from main directory
if __name__ == '__main__':
    import sys
    from app.data.database.database import DB
    from PyQt5.QtWidgets import QApplication
    app = QApplication(sys.argv)
    from app.data.resources.resources import RESOURCES
    from app.data.serialization.versions import CURRENT_SERIALIZATION_VERSION
    DB.load('default.ltproj', CURRENT_SERIALIZATION_VERSION)
    RESOURCES.load('default.ltproj', CURRENT_SERIALIZATION_VERSION)
    window = NewSkillDatabase(None, DB)
    window.show()
    app.exec_()
