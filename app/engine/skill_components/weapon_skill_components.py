from app.data.database.skill_components import SkillComponent, SkillTags


class WeaponSkill(SkillComponent):
    nid = 'weapon_skill'
    desc = "Marks this skill as a weapon skill."
    tag = getattr(SkillTags, 'CUSTOM', getattr(SkillTags, 'BASE', next(iter(SkillTags))))