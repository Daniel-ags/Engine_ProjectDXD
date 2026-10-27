from PyQt5.QtGui import QIcon, QPixmap, QColor
from PyQt5.QtCore import Qt

from app.data.database.database import DB
from app.data.resources.resources import RESOURCES

from app.editor.edit_history import HISTORY
from app.data.database.database_types import DatabaseType as DType
from app.editor import reference_dialogs
from app.extensions.custom_gui import DeletionTab

from app.editor.custom_widgets import TerrainBox
from app.editor.base_database_gui import DragDropCollectionModel

class TerrainModel(DragDropCollectionModel):
    def data(self, index, role):
        if not index.isValid():
            return None
        if role == Qt.DisplayRole:
            terrain = self._data[index.row()]
            text = terrain.nid + " : " + terrain.name
            return text
        elif role == Qt.DecorationRole:
            terrain = self._data[index.row()]
            color = terrain.color
            pixmap = QPixmap(32, 32)
            pixmap.fill(QColor(color[0], color[1], color[2]))
            return QIcon(pixmap)
        return None

    def delete(self, idx):
        # Check to see what is using me?
        res = self._data[idx]
        nid = res.nid

        def check_tilemap(tilemap) -> bool:
            for layer in tilemap.layers:
                for key, terrain in layer.terrain_grid.items():
                    if terrain == nid:
                        return True
            return False

        def check_tileset(tileset) -> bool:
            for key, terrain in tileset.terrain_grid.items():
                if terrain == nid:
                    return True
            return False

        affected_tilemaps = [tilemap for tilemap in RESOURCES.tilemaps if check_tilemap(tilemap)]
        affected_tilesets = [tileset for tileset in RESOURCES.tilesets if check_tileset(tileset)]

        deletion_tabs = []
        if affected_tilemaps:
            from app.editor.tile_editor.tile_model import TileMapModel
            model = TileMapModel
            msg = "Deleting Terrain <b>%s</b> would affect these tilemaps." % nid
            deletion_tabs.append(DeletionTab(affected_tilemaps, model, msg, "Tilemaps"))
        if affected_tilesets:
            from app.editor.tile_editor.tile_model import TileSetModel
            model = TileSetModel
            msg = "Deleting Terrain <b>%s</b> would affect these tilesets." % nid
            deletion_tabs.append(DeletionTab(affected_tilesets, model, msg, "Tilesets"))

        # Tilemaps and tilesets live in resources, which the reference schema does not cover yet
        with HISTORY.change_set('Delete %s' % nid):
            if reference_dialogs.check_delete(DType.TERRAIN, nid, 'Terrain', self.window,
                                              lambda: TerrainBox(self.window, exclude=res),
                                              extra_tabs=deletion_tabs,
                                              on_swap=lambda swap_nid: self.swap_in_resources(nid, swap_nid)):
                super().delete(idx)

    def on_nid_changed(self, old_nid, new_nid):
        HISTORY.rewrite(DType.TERRAIN, old_nid, new_nid)
        self.swap_in_resources(old_nid, new_nid)

    def swap_in_resources(self, old_nid, new_nid):
        tilemaps = [tilemap for tilemap in RESOURCES.tilemaps
                    if any(old_nid in layer.terrain_grid.values() for layer in tilemap.layers)]
        tilesets = [tileset for tileset in RESOURCES.tilesets if old_nid in tileset.terrain_grid.values()]
        with HISTORY.modifying([(tilemap, RESOURCES.tilemaps) for tilemap in tilemaps] +
                               [(tileset, RESOURCES.tilesets) for tileset in tilesets]):
            for tilemap in tilemaps:
                for layer in tilemap.layers:
                    for coord, terrain in layer.terrain_grid.items():
                        if terrain == old_nid:
                            layer.terrain_grid[coord] = new_nid
            for tileset in tilesets:
                for coord, terrain in tileset.terrain_grid.items():
                    if terrain == old_nid:
                        tileset.terrain_grid[coord] = new_nid

    def create_new(self):
        new_terrain = DB.terrain.create_new(DB)
        return new_terrain
