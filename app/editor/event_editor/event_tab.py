from PyQt5.QtWidgets import QTableView

from app.data.database.database import DB

from app.editor.base_database_gui import DatabaseTab
from app.extensions.custom_gui import TableView
from app.editor.data_editor import SingleDatabaseEditor

from app.editor.event_editor import event_model, event_properties

class EventDatabase(DatabaseTab):
    # Its script highlighting checks commands against the event's level: its units,
    # unit groups and map size
    reads_maps = True

    @classmethod
    def create(cls, parent=None):
        data = DB.events
        title: str = "Event"
        right_frame = event_properties.EventProperties

        collection_model = event_model.EventModel
        collection = event_properties.EventCollection
        dialog = cls(data, title, right_frame, None, collection_model, parent, view_type=QTableView, collection_type=collection)
        return dialog

    def reset(self):
        self.left_frame.fill_level_filter()
        # An undo may have moved the shown event to another level, out of the filter's
        current = self.right_frame.current
        if current is not None and any(event is current for event in self._data):
            self.left_frame.filter_to_level_of(current)
        super().reset()

# Testing
# Run "python -m app.editor.event_editor.event_tab"
if __name__ == '__main__':
    import sys
    from PyQt5.QtWidgets import QApplication
    app = QApplication(sys.argv)
    from app.data.serialization.versions import CURRENT_SERIALIZATION_VERSION
    DB.load('default.ltproj', CURRENT_SERIALIZATION_VERSION)
    window = SingleDatabaseEditor(EventDatabase)
    window.show()
    app.exec_()
