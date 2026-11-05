from PyQt5.QtCore import Qt
from PyQt5.QtGui import qRgb, QPixmap, QIcon, QBrush, QColor, QImage

from typing import List, Tuple

from app.utilities.typing import NID

from app.utilities.data import Data
from app.data.resources.resources import RESOURCES
from app.data.resources import combat_anims

from app.editor.base_database_gui import ResourceCollectionModel
from app.editor.combat_animation_editor.combat_effect_model import CombatEffectModel
from app.editor.edit_history import HISTORY
from app.extensions.custom_gui import DeletionTab

from app.utilities import str_utils
from app.editor import utilities as editor_utilities

def palette_swap(pixmap: QPixmap, palette_nid: NID, with_colorkey=True) -> QImage:
    palette = RESOURCES.combat_palettes.get(palette_nid)
    if not palette:
        return pixmap.toImage()
    im = pixmap.toImage()
    conv_dict = editor_utilities.get_coord_conversion(palette)
    # print("palette_swap: %s" % editor_utilities.human_readable(conv_dict))
    im = editor_utilities.color_convert(im, conv_dict)
    if with_colorkey:
        im = editor_utilities.convert_colorkey(im)
    return im

def plays_sound(poses, nid: NID) -> bool:
    return any(command.has_sound() and command.value[0] == nid for pose in poses for command in pose.timeline)

def sound_users(nid: NID) -> Tuple[List[combat_anims.CombatAnimation], List[combat_anims.EffectAnimation]]:
    """The combat animations and effects whose timelines play or stop the sound"""
    anims = [anim for anim in RESOURCES.combat_anims
             if any(plays_sound(weapon_anim.poses, nid) for weapon_anim in anim.weapon_anims)]
    effects = [effect for effect in RESOURCES.combat_effects if plays_sound(effect.poses, nid)]
    return anims, effects

def modifying_sound_users(anims, effects):
    return HISTORY.modifying([(anim, RESOURCES.combat_anims) for anim in anims] +
                             [(effect, RESOURCES.combat_effects) for effect in effects])

def poses_of(anims, effects) -> List[combat_anims.Pose]:
    return [pose for anim in anims for weapon_anim in anim.weapon_anims for pose in weapon_anim.poses] + \
        [pose for effect in effects for pose in effect.poses]

def rename_sound(old_nid: NID, new_nid: NID):
    """Points the combat animation and effect commands that play or stop a sound at its
    new nid, recorded"""
    anims, effects = sound_users(old_nid)
    with modifying_sound_users(anims, effects):
        for pose in poses_of(anims, effects):
            for command in pose.timeline:
                if command.has_sound() and command.value[0] == old_nid:
                    command.value = (new_nid,) + tuple(command.value[1:])

def remove_sound(nid: NID):
    """Takes the commands that play or stop a deleted sound out of the combat animation
    and effect timelines, recorded"""
    anims, effects = sound_users(nid)
    with modifying_sound_users(anims, effects):
        for pose in poses_of(anims, effects):
            pose.timeline = [command for command in pose.timeline
                             if not (command.has_sound() and command.value[0] == nid)]

def sound_deletion_tabs(nid: NID) -> List[DeletionTab]:
    """What a sound's deletion would affect beyond the database's own references to it"""
    anims, effects = sound_users(nid)
    tabs = []
    if anims:
        msg = "Deleting Sound <b>%s</b> would take it out of these combat animations." % nid
        tabs.append(DeletionTab(anims, CombatAnimModel, msg, "Combat Animations"))
    if effects:
        msg = "Deleting Sound <b>%s</b> would take it out of these combat effects." % nid
        tabs.append(DeletionTab(effects, CombatEffectModel, msg, "Combat Effects"))
    return tabs

def get_combat_anim_icon(combat_anim_nid: str):
    combat_anim = RESOURCES.combat_anims.get(combat_anim_nid)
    if not combat_anim or not combat_anim.weapon_anims:
        return None
    weapon_anim = combat_anim.weapon_anims.get('Unarmed', combat_anim.weapon_anims[0])
    pose = weapon_anim.poses.get('Stand')
    if not pose:
        return None

    # Get palette and apply palette
    if not combat_anim.palettes:
        return None
    palette_names = [palette[0] for palette in combat_anim.palettes]
    if 'GenericBlue' in palette_names:
        idx = palette_names.index('GenericBlue')
        palette_name, palette_nid = combat_anim.palettes[idx]
    else:
        palette_name, palette_nid = combat_anim.palettes[0]
    palette = RESOURCES.combat_palettes.get(palette_nid)
    if not palette:
        return None
    convert_dict = editor_utilities.get_coord_conversion(palette)

    # Get first command that displays a frame
    for command in pose.timeline:
        if command.nid in ('frame', 'over_frame', 'under_frame', 'dual_frame'):
            frame_nid = command.value[1]
            frame = weapon_anim.frames.get(frame_nid)
            if not frame:
                continue
            if not frame.pixmap:
                frame.pixmap = QPixmap(weapon_anim.full_path).copy(*frame.rect)
            pixmap = frame.pixmap
            im = pixmap.toImage()
            im = editor_utilities.color_convert(im, convert_dict)
            im = editor_utilities.convert_colorkey(im)
            pixmap = QPixmap.fromImage(im)
            return pixmap
    return None

class CombatAnimModel(ResourceCollectionModel):
    def data(self, index, role):
        if not index.isValid():
            return None
        if role == Qt.DisplayRole:
            animation = self._data[index.row()]
            text = animation.nid
            return text
        elif role == Qt.DecorationRole:
            animation = self._data[index.row()]
            nid = animation.nid
            pix = get_combat_anim_icon(nid)
            if pix:
                return QIcon(pix)
        return None

    def create_new(self):
        nid = str_utils.get_next_name('New Combat Anim', self._data.keys())
        new_anim = combat_anims.CombatAnimation(nid)
        self._data.append(new_anim)
        return new_anim
    