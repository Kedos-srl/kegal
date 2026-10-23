import unittest

from kegal.llm.llm_model import LLMStructuredSchema


class TestStructuredSchemaNormalization(unittest.TestCase):
    PROPS = {"response_txt": {"type": "string", "description": "answer"}}

    def test_parameters_alias_equals_properties(self):
        legacy = LLMStructuredSchema(**{"description": "d", "parameters": self.PROPS,
                                        "required": ["response_txt"]})
        standard = LLMStructuredSchema(**{"type": "object", "description": "d",
                                          "properties": self.PROPS, "required": ["response_txt"]})
        self.assertEqual(legacy.to_dict(), standard.to_dict())

    def test_type_object_added_when_missing(self):
        schema = LLMStructuredSchema(properties=self.PROPS)
        self.assertEqual(schema.to_dict()["type"], "object")

    def test_standard_schema_unchanged(self):
        data = {"type": "object", "properties": self.PROPS, "required": ["response_txt"]}
        self.assertEqual(LLMStructuredSchema(**data).to_dict(), data)

    def test_properties_wins_over_parameters(self):
        schema = LLMStructuredSchema(properties=self.PROPS, parameters={"x": {"type": "string"}})
        self.assertEqual(list(schema.to_dict()["properties"]), ["response_txt"])

    def test_scalar_schema_not_touched(self):
        self.assertEqual(LLMStructuredSchema(type="string").to_dict(), {"type": "string"})


if __name__ == "__main__":
    unittest.main()
