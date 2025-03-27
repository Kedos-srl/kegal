## Table of Contents
- [Installation Requirements](#installation-requirements)
- [Data Loading Functions](#data-loading-functions)
    - [graph_data_from_dictionary](#graph_data_from_dictionary)
    - [graph_data_from_json](#graph_data_from_json)
    - [graph_data_from_yaml](#graph_data_from_yaml)

- [GraphData Manipulation Functions](#graphdata-manipulation-functions)
    - [insert_user_message_to_graph_data](#insert_user_message_to_graph_data)
    - [insert_citations_to_graph_data](#insert_citations_to_graph_data)
    - [update_graph_data_history](#update_graph_data_history)

- [Export Functions](#export-functions)
    - [export_graph_as_json](#export_graph_as_json)
    - [export_graph_as_yaml](#export_graph_as_yaml)

- [File Update Functions](#file-update-functions)
    - [update_yml_file_data_history](#update_yml_file_data_history)
    - [update_json_file_data_history](#update_json_file_data_history)

- [Complete Examples](#complete-examples)
    - [Example 1: Managing a Conversation Graph](#example-1-managing-a-conversation-graph)
    - [Example 2: Adding Citations to a Response](#example-2-adding-citations-to-a-response)

    
  

## Installation Requirements

### Using pip

This module requires the following dependencies, which can be installed using pip:

```bash
pip install -r requirements.txt
```

### Using conda

Alternatively, you can set up the conda environment:

```bash
conda env update --file conda_env.yml
# Or to reset the environment completely:
# conda env update --file conda_env.yml --prune
```



## Data Loading Functions


### graph_data_from_dictionary
Creates a `GraphData` object from a dictionary.
**Parameters:**
- `graph_data_dict` (dict): The dictionary containing graph data.

**Returns:**
- `GraphData`: A new GraphData object.

**Example:**
``` python
graph_dict = {
    "models": [...],
    "systems": [...],
    "nodes": [
        {
            "id": "node0",
            "prompt": {
                "placeholders": {"post": "Good Morning", "history": ""}
            }
        },
        ...
    ],
    "edges": [..]
}

graph = graph_data_from_dictionary(graph_dict)
```
### graph_data_from_json
Loads a `GraphData` object from a JSON file.

**Parameters:**
- `json_file_path_` (Path): Path to the JSON file.

**Returns:**
- `GraphData`: A new GraphData object.

**Raises:**
- `TypeError`: If `json_file_path_` is not a Path object.
- `FileNotFoundError`: If the JSON file doesn't exist.
- `RuntimeError`: For other errors during file reading.

**Example:**
``` python
from pathlib import Path

try:
    graph = graph_data_from_json(Path("graph_config.json"))
    print(f"Loaded graph with {len(graph["nodes"])} nodes")
except FileNotFoundError as e:
    print(f"Error: {e}")
```
### graph_data_from_yaml
Loads a `GraphData` object from a YAML file.
**Parameters:**
- `yaml_file_path_` (Path): Path to the YAML file.

**Returns:**
- `GraphData`: A new GraphData object.

**Raises:**
- `TypeError`: If `yaml_file_path_` is not a Path object.
- `FileNotFoundError`: If the YAML file doesn't exist.
- `RuntimeError`: For other errors during file reading.

**Example:**
``` python
from pathlib import Path

try:
    graph = graph_data_from_yaml(Path("graph_config.yaml"))
    print(f"Loaded graph with {len(graph["nodes"])} nodes")
except Exception as e:
    print(f"Error loading YAML: {e}")
```
## GraphData Manipulation Functions

### insert_user_message_to_graph_data
Inserts a user message into the first node of the graph data.

**Parameters:**
- `graph_data` (GraphData): The graph data object to be updated.
- `user_message` (str): The user's message to be inserted.

**Returns:**
- `GraphData`: The updated graph data object.

**Raises:**
- `KeyError`: If 'post' placeholder is not found in the ***first*** node's prompt.

**Example:**
``` python
from pathlib import Path

# Load a graph
graph = graph_data_from_yaml(Path("conversation_graph.yaml"))

# Insert a user message
try:
    updated_graph = insert_user_message_to_graph_data(graph, "How can I create a new project?")
    print("User message inserted successfully")
except KeyError as e:
    print(f"Error: {e}")
```
### insert_citations_to_graph_data
Adds citation chunks to nodes that contain a 'citations' placeholder in their prompts.
**Parameters:**
- `graph_data` (GraphData): The graph data object containing nodes to be updated.
- `chunks` (list[str]): List of citation text chunks to be added.

**Returns:**
- `GraphData`: The updated graph data object with citations added.

**Example:**
``` python
# Citation chunks from a knowledge base
citations = [
    "According to document A, the recommended approach is X.",
    "Document B states that alternative Y can be used in specific cases.",
    "The latest research paper C suggests Z as a best practice."
]

# Add citations to the graph data
graph_with_citations = insert_citations_to_graph_data(graph, citations)
print("Citations added to applicable nodes")
```
### update_graph_data_history
Update the graph data, for all posts with $history in the placeholder, with the conversation history from LLM replies.

**Parameters:**
- `graph_data` (GraphData): The graph data object containing nodes to be updated.
- `responses` (list[LlmResponse]): List of LLM response objects.

**Returns:**
- `GraphData`: The updated graph data object with modified history placeholders.

**Example:**
``` python
from llm.llm_response import LlmResponse

# Example LLM responses
responses = [
    LlmResponse(
        id="node1",
        message_content="What are the benefits of microservices?",
        response_content={
            "validation: True,
            "response_txt": "Microservices offer several benefits including scalability, technology flexibility, and resilience."
        }
    )
]

# Update graph with conversation history
updated_graph = update_graph_data_history(graph, responses)
print("Conversation history updated in the graph")
```


## Export Functions

### export_graph_as_json
Exports a GraphData object to a JSON file.

**Parameters:**
- `graph_data` (GraphData): The graph data to export.
- `file_path` (Path): The file path where the JSON will be saved.

**Example:**
``` python
from pathlib import Path

# Export the graph to a JSON file
export_graph_as_json(graph, Path("updated_graph.json"))
print("Graph exported to JSON successfully")
```
### export_graph_as_yaml
Exports a GraphData object to a YAML file.
**Parameters:**
- `graph_data` (GraphData): The graph data to export.
- `file_path` (Path): The file path where the YAML will be saved.

**Example:**
``` python
from pathlib import Path

# Export the graph to a YAML file
export_graph_as_yaml(graph, Path("updated_graph.yaml"))
print("Graph exported to YAML successfully")
```
## File Update Functions
### update_yml_file_data_history

Updates conversation history in a YAML file with new LLM responses.

**Parameters:**
- `yaml_file_path_` (Path): Path to the YAML file.
- `responses` (list[LlmResponse]): List of LLM response objects.

**Raises:**
- `TypeError`: If `yaml_file_path_` is not a Path object.
- `FileNotFoundError`: If the YAML file doesn't exist.
- `RuntimeError`: For other errors during file reading or writing.

**Example:**
``` python
from pathlib import Path
from llm.llm_response import LlmResponse

# Example response
response = LlmResponse(
    id="node2",
    message_content="How do I implement authentication?",
    response_content={
        "validation": True,
        "response_txt": "You can implement authentication using OAuth2 or JWT tokens."
    }
)

# Update YAML file with new response
try:
    update_yml_file_data_history(Path("conversation_graph.yaml"), [response])
    print("YAML file updated with conversation history")
except Exception as e:
    print(f"Error updating YAML file: {e}")
```
### update_json_file_data_history
Updates conversation history in a JSON file with new LLM responses.

**Parameters:**
- `json_file_path_` (Path): Path to the JSON file.
- `responses` (list[LlmResponse]): List of LLM response objects.

**Raises:**
- `TypeError`: If `json_file_path_` is not a Path object.
- `FileNotFoundError`: If the JSON file doesn't exist.
- `RuntimeError`: For other errors during file reading or writing.

**Example:**
``` python
from pathlib import Path
from llm.llm_response import LlmResponse

# Example response
response = LlmResponse(
    id="node3",
    message_content="What's the best database for my application?",
    response_content={
        "validation": True,
        "response_txt": "The best database depends on your specific needs. For relational data, consider PostgreSQL."
    }
)

# Update JSON file with new response
try:
    update_json_file_data_history(Path("conversation_graph.json"), [response])
    print("JSON file updated with conversation history")
except Exception as e:
    print(f"Error updating JSON file: {e}")
```


## Complete Examples

### Example 1: Managing a Conversation Graph

This example demonstrates loading a graph, inserting a user message, updating with LLM responses, and saving the result:

``` python
from pathlib import Path
from graph_utils import (graph_data_from_yaml, insert_user_message_to_graph_data,
                         update_graph_data_history, export_graph_as_yaml)
from llm.llm_response import LlmResponse

# 1. Load the graph from a YAML file
graph_path = Path("conversation_graph.yaml")
graph = graph_data_from_yaml(graph_path)

# 2. Insert a user message
user_query = "How do I optimize database performance?"
graph = insert_user_message_to_graph_data(graph, user_query)

# 3. Simulate an LLM response
response = LlmResponse(
    id="node1",
    message_content=user_query,
    response_content={
        "validation": True,
        "response_txt": "To optimize database performance, consider indexing, query optimization, and connection pooling."
    }
)

# 4. Update the graph with the conversation history
graph = update_graph_data_history(graph, [response])

# 5. Save the updated graph
export_graph_as_yaml(graph, Path("updated_conversation.yaml"))


```
### Example 2: Adding Citations to a Response
This example shows how to add citations to a graph and update a file:
``` python
from pathlib import Path
from graph_utils import (graph_data_from_json, insert_citations_to_graph_data,
                         update_json_file_data_history)
from llm.llm_response import LlmResponse

# 1. Load a graph from a JSON file
json_path = Path("knowledge_graph.json")
graph = graph_data_from_json(json_path)

# 2. Add citations from retrieved documents
citations = [
    "Database indexing can improve query performance by up to 300% (Source: Database Performance Quarterly, 2023)",
    "Connection pooling reduced database load by 45% in our benchmark tests (TechReport, 2022)",
    "Query optimizers typically evaluate multiple execution plans (Database Systems: The Complete Book, 2019)"
]
graph = insert_citations_to_graph_data(graph, citations)

# 3. Create a response with the citations
response = LlmResponse(
    id="response_node",
    message_content="How can I make my database faster?",
    response_content={
         "validation": True,
        "response_txt": "I've analyzed your database and found several optimization opportunities...",
    }
)

# 4. Update the JSON file directly
update_json_file_data_history(json_path, [response])
```


### Example 3: Distributed Graph Processing 

Below is a conceptual example,  showing how it is possible to  structure two separate Python applications that use FastAPI to communicate. 

The first application serves as a "compiler" for the graph.
It simply takes a JSON file describing the graph, processes it, and returns a list of "LlmResponse"-like objects.

The second application acts as a "hub": it receives a user message,
performs tasks such as looking up data in a vector database, updates the graph with user messages or citations ,
sends the updated graph to the compiler application, then finally returns responses back to the front-end.


This example wants to illustrate the separation of responsibilities:
- KeGal (the compiler) is focused on handling the graph structure and producing the relevant LlmResponse objects.
- The "Hub" application handles the broader tasks like user interaction, vector database lookups, and final assembly of the conversation flow.

**KeGal Compiler Service**
```python
# compiler_service.py
import json
from pathlib import Path
from fastapi import FastAPI, HTTPException, UploadFile, File, Body
from pydantic import BaseModel
from typing import List, Dict, Any
import tempfile

from graph_data import GraphData
from llm.llm_response import LlmResponse
from kegal_compiler import compile_graph  # Assuming this is the main compilation function

app = FastAPI(title="KeGal Graph Compiler Service")




@app.post("/compile-graph")
async def compile_graph_endpoint(graph_json: Dict[str, Any] = Body(...)):
    """
    Compiles a graph from provided JSON data and returns the LLM responses.
    
    This is the main endpoint of the compiler service, which:
    1. Converts the JSON data to a GraphData object
    2. Runs the KeGal compiler on the graph
    3. Returns the resulting LLM responses
    """
    try:
        # Create GraphData from the provided JSON
        graph_data = GraphData(**graph_json)

        # Compile the graph (this is the core KeGal function that processes the graph)
        responses: List[LlmResponse] = compile_graph(graph_data)

        return responses

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Graph compilation error: {str(e)}")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
```


**Frontend Interface Service**

```python
# interface_service.py
import json
import requests
from pathlib import Path
from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import tempfile
import chromadb
from chromadb.config import Settings

from graph_data import GraphData
from llm.llm_response import LlmResponse

# Import functions from the module shown in the original code
from kegal_utils import (
    graph_data_from_json,
    insert_user_message_to_graph_data,
    insert_citations_to_graph_data,
    update_graph_data_history,
    export_graph_as_json
)

app = FastAPI(title="KeGal Frontend Interface Service")

# Initialize ChromaDB client
chroma_client = chromadb.Client(Settings(
    chroma_db_impl="duckdb+parquet",
    persist_directory="./chroma_db"
))

# Create or get collection
collection = chroma_client.get_or_create_collection(name="document_collection")


class UserMessageRequest(BaseModel):
    message: str
    graph_template_path: Optional[str] = "templates/default_graph.json"





@app.post("/process-message")
async def process_message(request: UserMessageRequest):
    """
    Process a user message through the full pipeline:
    1. Receive message from frontend
    2. Perform vector search for relevant content
    3. Update graph with citations and user message
    4. Send graph to compiler service
    5. Update graph history with responses
    6. Return response to frontend
    """
    try:
        # 1. Get the user message
        user_message = request.message

        # 2. Perform vector search in ChromaDB
        search_results = collection.query(
            query_texts=[user_message],
            n_results=3
        )

        # Extract citation chunks from search results
        citation_chunks = search_results.get('documents', [[]])[0]

        # 3. Load graph template
        graph_template_path = Path(request.graph_template_path)
        graph_data = graph_data_from_json(graph_template_path)

        # Update graph with user message and citations
        graph_data = insert_user_message_to_graph_data(graph_data, user_message)
        graph_data = insert_citations_to_graph_data(graph_data, citation_chunks)

        # 4. Prepare and send graph to compiler service
        graph_json = json.loads(graph_data.model_dump_json())

        # Call the compiler service
        compiler_responses = requests.post(
            "http://compiler-service:8000/compile-graph",
            json=graph_json
        )

        if compiler_responses.status_code != 200:
            raise HTTPException(status_code=502, detail=f"Compiler service error: {compiler_response.text}")

        # 5. Process the compiler response
        responses_data = HTTPException.json()

        # Convert the response data back to LlmResponse objects

        # 6. Update graph history with responses
        updated_graph = update_graph_data_history(graph_data, responses_data)

        # Save the updated graph
        temp_output_path = Path(f"./conversation_history/{graph_template_path.stem}_{hash(user_message)}.json")
        export_graph_as_json(updated_graph, temp_output_path)

        # 7. Return the responses to the frontend 
        return responses_data

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing message: {str(e)}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)

```