import re
from typing import Any, Dict, List
from pydantic import BaseModel

from jsonschema import Draft202012Validator, SchemaError
from jsonschema.validators import validator_for

# ================================================
# STRUCTURED OUTPUT AND TOOL SCHEMA VALIDATORS
# ================================================


class SchemaIssue(BaseModel):
    """Single schema validation issue"""
    path: str
    rule: str
    message: str
    value: Any = None

def print_validation_input_schema(issues: List[SchemaIssue]):
    """Print validation report"""
    if not issues:
        print("✓ Schema is VALID for Claude structured outputs\n")
        return

    print(f"✗ Schema is INVALID - {len(issues)} issue(s) found:\n")
    for i, issue in enumerate(issues, 1):
        print(f"Issue #{i}:")
        print(f"  Path: {issue.path}")
        print(f"  Rule: {issue.rule}")
        print(f"  Message: {issue.message}")
        if issue.value is not None:
            print(f"  Value: {issue.value}")


def validate_anthropic_schema(schema: Dict[str, Any]) -> List[SchemaIssue]:
    """
    Validate JSON schema against Claude's structured output limitations

    Args:
        schema: JSON schema dictionary

    Returns:
        List of SchemaIssue objects (empty list = valid schema)
    """
    issues = []

    # Check $schema version
    # Check $schema version
    schema_version = schema.get('$schema')
    supported_version = 'https://json-schema.org/draft/2020-12/schema'

    if schema_version:
        # Normalize schema URI
        normalized = schema_version.rstrip('#')
        expected_normalized = supported_version.rstrip('#')

        if not (normalized == expected_normalized or
                normalized == expected_normalized.replace('https://', 'http://')):
            issues.append(SchemaIssue(
                path="root.$schema",
                rule="INVALID_SCHEMA_VERSION",
                message=f"KeXtract requires JSON Schema 2020-12, got '{schema_version}'",
                value=schema_version
            ))

    # Validate schema structure using jsonschema library
    try:
        # Get the appropriate validator class
        ValidatorClass = validator_for(schema)

        # Check if the validator is Draft 2020-12
        if ValidatorClass != Draft202012Validator:
            issues.append(SchemaIssue(
                path="root.$schema",
                rule="UNSUPPORTED_SCHEMA_VERSION",
                message=f"Schema uses {ValidatorClass.META_SCHEMA.get('$id', 'unknown')}, but Anthropic requires 2020-12",
                value=schema.get('$schema')
            ))

        # Validate the schema itself
        Draft202012Validator.check_schema(schema)

    except SchemaError as e:
        # Schema is malformed
        error_path = '.'.join(str(p) for p in e.path) if e.path else 'root'
        issues.append(SchemaIssue(
            path=error_path,
            rule="INVALID_JSON_SCHEMA",
            message=f"Invalid JSON Schema: {e.message}",
            value=e.instance if hasattr(e, 'instance') else None
        ))
        # Don't continue if schema is fundamentally broken
        return issues
    except Exception as e:
        issues.append(SchemaIssue(
            path="root",
            rule="SCHEMA_VALIDATION_ERROR",
            message=f"Error validating schema: {str(e)}",
            value=None
        ))
        return issues


    VALID_PROPERTY_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9_.-]{1,64}$')

    def check_node(node: Any, path: str):
        if not isinstance(node, dict):
            return

        # Rule: No numeric constraints
        for constraint in ['minimum', 'maximum', 'exclusiveMinimum', 'exclusiveMaximum', 'multipleOf']:
            if constraint in node:
                issues.append(SchemaIssue(
                    path=path,
                    rule=f"NO_{constraint.upper()}",
                    message=f"Numeric constraint '{constraint}' not supported",
                    value=node[constraint]
                ))

        # Rule: No string constraints
        for constraint in ['minLength', 'maxLength']:
            if constraint in node:
                issues.append(SchemaIssue(
                    path=path,
                    rule=f"NO_{constraint.upper()}",
                    message=f"String constraint '{constraint}' not supported",
                    value=node[constraint]
                ))

        # Rule: No array constraints (except minItems 0 or 1)
        for constraint in ['maxItems', 'uniqueItems', 'contains']:
            if constraint in node:
                issues.append(SchemaIssue(
                    path=path,
                    rule=f"NO_{constraint.upper()}",
                    message=f"Array constraint '{constraint}' not supported",
                    value=node[constraint]
                ))

        # Rule: minItems only 0 or 1
        if 'minItems' in node and node['minItems'] not in [0, 1]:
            issues.append(SchemaIssue(
                path=path,
                rule="MINITEMS_0_OR_1",
                message=f"minItems must be 0 or 1, got {node['minItems']}",
                value=node['minItems']
            ))

        # Rule: Objects must have additionalProperties: false
        if node.get('type') == 'object':
            if 'additionalProperties' in node and  node['additionalProperties'] is not False:
                issues.append(SchemaIssue(
                    path=path,
                    rule="ADDITIONAL_PROPERTIES_FALSE",
                    message=f"additionalProperties must be false, got {node['additionalProperties']}",
                    value=node['additionalProperties']
                ))
        # Rule: No external $ref
        if '$ref' in node and (node['$ref'].startswith('http://') or node['$ref'].startswith('https://')):
            issues.append(SchemaIssue(
                path=path,
                rule="NO_EXTERNAL_REF",
                message="External $ref not supported",
                value=node['$ref']
            ))

        # Rule: No complex types in enum
        if 'enum' in node:
            for item in node['enum']:
                if isinstance(item, (dict, list)):
                    issues.append(SchemaIssue(
                        path=path,
                        rule="NO_COMPLEX_ENUM",
                        message="Complex types in enum not supported",
                        value=type(item).__name__
                    ))
                    break

        # Rule: No allOf with $ref
        if 'allOf' in node:
            for item in node['allOf']:
                if '$ref' in item:
                    issues.append(SchemaIssue(
                        path=path,
                        rule="NO_ALLOF_REF",
                        message="allOf with $ref not supported",
                        value=item['$ref']
                    ))
                    break

        # Rule: Validate property names
        if 'properties' in node:
            for prop_name, prop_schema in node['properties'].items():
                # Check if property name matches the required pattern
                if not VALID_PROPERTY_NAME_PATTERN.match(prop_name):
                    issues.append(SchemaIssue(
                        path=f"{path}.{prop_name}",
                        rule="INVALID_PROPERTY_NAME",
                        message=f"Property name '{prop_name}' must match pattern ^[a-zA-Z0-9_.-]{{1,64}}$",
                        value=prop_name
                    ))
                # Recursively check the property schema
                check_node(prop_schema, f"{path}.{prop_name}")


        if 'items' in node and isinstance(node['items'], dict):
            check_node(node['items'], f"{path}[]")

        if 'anyOf' in node:
            for i, subschema in enumerate(node['anyOf']):
                check_node(subschema, f"{path}.anyOf[{i}]")

        if 'allOf' in node:
            for i, subschema in enumerate(node['allOf']):
                check_node(subschema, f"{path}.allOf[{i}]")


        if '$defs' in node:
            for def_name, def_schema in node['$defs'].items():
                # Validate definition name
                if not VALID_PROPERTY_NAME_PATTERN.match(def_name):
                    issues.append(SchemaIssue(
                        path=f"$defs.{def_name}",
                        rule="INVALID_DEFINITION_NAME",
                        message=f"Definition name '{def_name}' must match pattern ^[a-zA-Z0-9_.-]{{1,64}}$",
                        value=def_name
                    ))
                check_node(def_schema, f"$defs.{def_name}")

    check_node(schema, "root")
    return issues



def validate_openai_schema(schema: dict[str, Any]) -> List[SchemaIssue]:
    issues = []
    def check_node(node: Any, path: str):
        if not isinstance(node, dict):
            return []

        # Example: forbid unsupported JSON-Schema features
        for bad in ['format', 'pattern', 'patternProperties', 'unevaluatedProperties', 'dependentSchemas']:
            if bad in node:
                issues.append(SchemaIssue(
                    path=path,
                    rule=f"NO_{bad.upper()}",
                    message=f"JSON Schema keyword '{bad}' may not be supported by OpenAI Structured Outputs",
                    value=node[bad]
                ))

        # (Optional) you may forbid more constraints if you know they break CFG-based decoding
        # e.g. regex-based string constraints, maybe certain numeric constraints, etc.

        # Recurse
        for k in node.get('properties', {}):
            check_node(node['properties'][k], f"{path}.{k}")
        if 'items' in node and isinstance(node['items'], dict):
            check_node(node['items'], f"{path}[]")
        for comb in ('anyOf','allOf','oneOf'):
            if comb in node:
                for i, s2 in enumerate(node[comb]):
                    check_node(s2, f"{path}.{comb}[{i}]")

    check_node(schema, "root")
    return issues




"""
anthropic_aws
anthropic
bedrock
ollama
openai
"""


def validate_llm_input_schema(input_schema: type[BaseModel] | dict[str, Any], model: str) -> List[SchemaIssue]:
    """Validate LLM schema against provider-specific requirements

    Args:
        input_schema: Pydantic BaseModel class or JSON schema dict
        model: LLM provider name

    Returns:
        List of SchemaIssue objects (empty if valid)
    """
    # Convert Pydantic model to JSON schema dict
    if isinstance(input_schema, type):
        schema = input_schema.model_json_schema()
    else:
        schema = input_schema  # <-- Mancava l'else!

    # Validate based on provider
    if model in ["anthropic_aws", "anthropic", "bedrock"]:
        return validate_anthropic_schema(schema)
    elif model in ["openai", "ollama"]:
        return validate_openai_schema(schema)
    else:
        return []





