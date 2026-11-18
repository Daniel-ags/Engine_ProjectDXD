from app.data.database.skill_components import SkillComponent, SkillTags


class UniqueSkill(SkillComponent):
    nid = 'unique_skill'
    desc = "Marks this skill as a unit's innate unique skill (costs 0 personal slots and cannot be unequipped)."
    tag = getattr(SkillTags, 'CUSTOM', getattr(SkillTags, 'BASE', next(iter(SkillTags))))