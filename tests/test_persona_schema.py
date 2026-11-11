import unittest

from service.persona.schema import (
    add_self_change,
    render_profile_sections,
    render_self_sections,
    validate_profile_sections,
    validate_self_sections,
)


class PersonaSchemaTest(unittest.TestCase):
    def test_self_sections_render(self):
        data = validate_self_sections({
            "changes": ["我学会先听完"],
            "learned": ["不确定就先查"],
            "open_questions": [],
        })
        text = render_self_sections(data)
        self.assertIn("## 最近的变化", text)
        self.assertIn("- 我学会先听完", text)
        merged = add_self_change(text, "我学会不急着接圆")
        self.assertIn("- 我学会先听完", merged)
        self.assertIn("- 我学会不急着接圆", merged)

    def test_self_rejects_rules(self):
        with self.assertRaises(ValueError):
            validate_self_sections({"changes": ["回答时要短"]})
        with self.assertRaises(ValueError):
            validate_self_sections({"facts": ["主人喜欢奶龙"]})

    def test_profile_sections_render(self):
        data = validate_profile_sections({
            "stable_facts": ["主人晚睡"],
            "appearance": [],
            "preferences": [],
            "values": [],
        })
        text = render_profile_sections(data)
        self.assertIn("**他是谁**", text)
        self.assertIn("- 主人晚睡", text)

    def test_profile_rejects_instructions(self):
        with self.assertRaises(ValueError):
            validate_profile_sections({"appearance": ["你应该默认贴来源"]})
        with self.assertRaises(ValueError):
            validate_profile_sections({"persona": ["傲娇"]})


if __name__ == "__main__":
    unittest.main(verbosity=2)
