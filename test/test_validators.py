import unittest

from pydantic import BaseModel, Field

from kegal.kegal.validators import print_validation_input_schema,  validate_llm_input_schema



# ============================================================
# VALID SCHEMA (Anthropic-compliant)
# ============================================================



class Product(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    price: float = Field(ge=0, le=10000)
    rating: int = Field(ge=1, le=5)

class TestValidators(unittest.TestCase):



    def test_schema_anthropic(self):
        model_name = "anthropic"

        # Example 0: Check Pydantic model
        print("=" * 60)
        print("Example 0: Schema standard 2020-12 check")
        print("=" * 60)
        invalid_standard = {
            "type": "object",
            "properties": {
                "age": {
                    "type": "integer",
                    "minimum": "10"  # ❌ Dovrebbe essere un numero, non stringa
                }
            }
        }
        issues = validate_llm_input_schema(invalid_standard, model_name)
        print_validation_input_schema(issues)
        self.assertGreater(len(issues), 0)

        # Example 1: Check Pydantic model
        print("=" * 60)
        print("Example 1: Pydantic Model with Issues")
        print("=" * 60)

        issues = validate_llm_input_schema(Product, model_name)
        print_validation_input_schema(issues)
        self.assertGreater(len(issues), 0)

        # Example 2: Check raw JSON schema
        print("=" * 60)
        print("Example 2: Raw JSON Schema")
        print("=" * 60)

        my_schema = {
            "type": "object",
            "properties": {
                "id": {"type": "integer", "minimum": 1},
                "email": {"type": "string", "format": "email"},
                "user reference": {"type": "string"},
                "user.address": {"type": "string"},
            },
            "required": ["id", "email"]
        }

        issues = validate_llm_input_schema(my_schema, model_name)
        print_validation_input_schema(issues)
        self.assertGreater(len(issues), 0)

        # Example 3: Valid schema
        print("=" * 60)
        print("Example 3: Valid Schema")
        print("=" * 60)

        valid_schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer"}
            },
            "required": ["name", "age"],
            "additionalProperties": False
        }

        issues = validate_llm_input_schema(valid_schema, model_name)
        print_validation_input_schema(issues)
        self.assertEqual(len(issues), 0)