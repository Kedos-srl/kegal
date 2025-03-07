# 1. Context definition

```markdown
## CONTEXT
```

# 2. Instructions

```markdown
## INSTRUCTIONS
```

# 3. Citations
```markdown
## CITATIONS
```

# 4. History
```markdown
## CONVERSATION HISTORY
```
# User post
```markdown
## POST
```

# 5. User role/id/name
```markdown
## POSTER
```

# 6. Tool
## TOOL

# 7. Output configuration

```markdown
## OUTPUT
- Generate final output by following the steps below:
1. Read the following schema:
    ```json 
        {
          "type": "object",
          "properties": {
            "validation": {
              "type": "boolean",
              "description": ""
            },
            "response_txt": {
              "type": "string",
              "description": ""
            }
          },
          "required": [
            "validation",
            "response_txt"
          ]
        }
    ```
2. For each element of the schema generate a corresponding valid key according to its description
3. Generate a draft json
4. Validate and fixing it
5. Now generate only the valid json object with NO comments or additional text
```


```markdown
    ```json 
        "response_txt": {
          "type": "string",
          "description": ""
        }
    ```
```

```markdown
    ```json 
        "response_obj": {
          "type": "objct",
           $response_properties
        }
    ```
```

```markdown
    ```json 
        "response_tool": {
          "type": "object",
          "description": "Configuration for executing a tool function with its parameters",
          "properties": {
            "tool": {
              "type": "string",
              "description": "The tool identifier in 'module_name.function_name' format that specifies which tool to execute",
              "examples": "image_processor.resize_image"
            },
            "parameters": {
              "type": "object",
              "description": "Dictionary containing the parameters to be passed to the tool function",
              "additionalProperties": true,
              "examples": {
                "width": 800,
                "height": 600,
                "path": "image.jpg"
              }
            }
          },
          "required": ["tool", "parameters"],
        }
    ```
```