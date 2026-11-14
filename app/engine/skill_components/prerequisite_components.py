from app.data.database.skill_components import SkillComponent, SkillTags
from app.data.database.components import ComponentType


class PrerequisiteSkills(SkillComponent):
    nid = 'prerequisite_skills'
    desc = "Requires all listed skills to be mastered/learned before this skill can be permanently learned."
    tag = getattr(SkillTags, 'CUSTOM', getattr(SkillTags, 'BASE', next(iter(SkillTags))))

    expose = (ComponentType.List, ComponentType.Skill)
    value = []