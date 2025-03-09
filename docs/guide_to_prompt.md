# Prompt Guide Documentation


## Table of Contents
1. [Introduction](#1-introducion)
2. [Context Definition](#1-context-definition)
3. [Instructions](#2-instructions)
4. [Citations](#3-citations)
5. [History](#4-history)
6. [User Post and Poster](#5-user-post-and-poster)
7. [Tool](#6-tool)
8. [Output Configuration](#7-output-configuration)

---


## 1. Introduction

When writing prompts for a projects in our system, you must adhere to several important rules to ensure proper functionality.

**Placeholder Formatting**

The Python component of the graph computation will automatically complete your prompt templates using placeholder objects defined in the graph configuration. 
This means that certain variables are mandatory if they're expected in the prompt.


For example:
To reference conversation history, you must use: ***$history***
Other mandatory variables will be specified in your project documentation


All placeholders must use Python String Template formatting with the $ symbol rather than curly braces:
- Correct: ***$placeholder***
- Incorrect: ***{placeholder}***




***Output Definition***

Your output must strictly follow the format specified in the later sections of the guide.

This is critical because the Python graph uses the object returned by the response according to these predefined structures.
Following these guidelines will ensure that your prompts integrate correctly with the underlying system and produce the expected results for your legal project.

---


## 2. Context Definition

The Context section defines the background and environment for prompt execution:
- Establishes interaction scope
- Defines background information 
- Sets up contextual parameters
- Provides system state details

```markdown
## CONTEXT
```

#### Placeholders
- ***$assistant_role***: When defining assistant role


---


## 3. Instructions

The Instructions section provides specific guidelines:
- Step-by-step procedures
- Required actions
- Formatting requirements
- Constraints and limitations

```markdown
## INSTRUCTIONS
```
#### Placeholders
- This session, may contain any non-standard agent-specific placeholders

---


## 4. Citations
Citation section is used to deal with text chunks that comes from external 
resources like vector database.

```markdown
## CITATIONS
```

#### Placeholders
- ***$citations***: marks the point where all chunks coming from a vector database are inserted and referenced


---


## 5. History
The Conversation History section maintains previous interactions record.

```markdown
## CONVERSATION HISTORY
```

#### Placeholders
- ***$history***: marks the point where all chunks coming from a vector database are inserted and referenced


---

## 6. User Post and Poster
This section defines the user's role within a conversation.

# User post
```markdown
## POST
```


```markdown
## POSTER
```

#### Placeholders
- ***$post***: user message
- ***$poster***: user identification and role definition


---

## 7. Tools
Tool section specifications:
- Available tools/functions
- Access permissions
- Parameter requirements
- Execution context

```markdown
## TOOLS
```

#### Placeholders
Tolls should be described in such a way that they can be selected effectively according to their use.
A good example for creating placeholders for the use of the tools would be the following:

- ***$resize_image_tool***: placeholder to handle the python function that modifies an image, ex `image_processor.resize_image`
- ***$resize_image_description***: function description
- ***$resize_image_parameters***: description of the formal parameters of the function


---


## 8. Output Configuration

### ⚠️ CRITICAL REQUIREMENT
The JSON schemas provided below MUST be used EXACTLY as shown,
without any modifications to structure or content.

#### 1. Main Response Schema

```markdown
## OUTPUT
Generate final output by following the steps below:
1. Read the following schema:
    ```json 
        {
          "type": "object",
          "description": "This is the schema of the response object",
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
3. Make sure you generate a json,  Avoid to output json schema
4. Generate a draft json 
5. Validate and fixing it
6. Now generate only the valid json object with NO comments or additional text
```

**Purpose and Requirements:**
Both of the following fields are REQUIRED in every response
- `validation`: Boolean field for response validity. 
              This value is used in the python code to continue or not in the graph view
- `response_txt`, `response_obj`, `response_tool`:  response management field


***|N.B.|***
For each schema object the "description" field is extremely important to give the right reference
s on what the terms for validation should be or what and how a response should be sent.

#### Text Response Schema

```markdown
    ```json 
        "response_txt": {
          "type": "string",
          "description": ""
        }
    ```
```
**Purpose and Requirements:**
For simple text-based responses
- Defines plain text responses
- Must contain valid string data
- No additional formatting allowed



#### 3. Object Response Schema

```markdown
    ```json 
        "response_obj": {
          "type": "objct",
           $response_properties
        }
    ```
```
**Purpose and Requirements:**
For structured object responses
- `$response_properties`: Dynamic property placeholder
- Must maintain valid JSON structure
- Properties vary by context


#### 4. Tool Response Schema

```markdown
    ```json 
        "response_tool": {
          "type": "object",
          "description": "This is the schema of the tool object",
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

**Purpose and Requirements:**
Defines tool execution configuration
- `tool`:
  * MUST use 'module_name.function_name' format
  * Specifies tool function to execute
  * String type only
- `parameters`:
  * Contains tool-specific parameters
  * Must be valid JSON object
  * Values must match tool requirements 


### Schema Validation Rules
- Valid JSON syntax required
- All required fields must exist
- Exact data type matching
- Additional properties only where allowed
- Unchanged schema structure
- Clean JSON output without comments
