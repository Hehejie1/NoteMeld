import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]


class TestCoreModelServiceContracts(unittest.TestCase):
    def test_add_new_model_does_not_probe_capability_on_save(self):
        model_service = (ROOT / "backend" / "app" / "services" / "model.py").read_text(encoding="utf-8")

        add_new_model_section = model_service.split("def add_new_model", 1)[1]
        add_new_model_section = add_new_model_section.split("if __name__ == '__main__':", 1)[0]

        self.assertNotIn("probe_json_mode_safe", add_new_model_section)


if __name__ == "__main__":
    unittest.main()
