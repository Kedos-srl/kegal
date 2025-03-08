
This documentation provides a structured outline of an architecture designed to define and execute a computational graph 
consisting of discrete units of work called “nodes.”
Each node relies on prompts—effectively acting as scripts—to determine how tasks are performed.
The architecture prioritizes reusability, modularity, and transparency in the flow of data between nodes.

## Core Concepts

### Node-Centric Design
Each node is a self-contained unit performing a single specific task in the computational graph. 
This modular design ensures that the responsibilities of a node remain focused, making the workflow easy to maintain and expand.

[//]: # (### Handling Self-Referential Nodes)

[//]: # (In some cases, a node might need to reference its own output &#40;e.g., iterative processing&#41;.)

[//]: # (The architecture supports self-referencing by allowing edges to feed a node’s output back into itself. )

[//]: # (This should be configured carefully to avoid unintended loops or excessive recursion. )

[//]: # (Typically, a node’s prompt definitions and the data flow management system must incorporate logic to handle iteration stops or convergence criteria.)

### Prompt-Based Execution
Rather than embedding functionality directly into the application, each node’s logic is dictated by prompts. 
This approach treats prompts like “code,” which a node interprets when it runs. 
It brings flexibility—nodes can be quickly updated by modifying the prompt, without reworking extensive underlying logic.

### Graph Structure
The system treats nodes as vertices in a ***directed graph***.
Connections, or  ***edges***, define how data flows among these nodes. 

In a directed graph: 
- Node outputs can be passed forward to subsequent nodes.
- Nodes may receive inputs from multiple sources, enabling complex workflows.

This structure allows for clear traceability of data and provides a visual representation of the overall process.


## Workflow Outline

1. **Configuration Setup**
- Define ***models*** (processing engines or services) that the nodes will invoke.
- Create ***systems*** to house shared prompts or configurations used by multiple nodes.
- Describe individual ***nodes***, each of which references a model and a system prompt. 
  Node descriptions include any parameters or placeholders needed for that node’s specific function.

  Follow the instructions on how to write the prompt: [guide_to_prompt.md](guide_to_prompt.md)
- Establish ***edges*** between these nodes to indicate dependencies or data flow paths.


2. **Execution Process**
- Each node interprets its assigned prompt and performs its single task.
- Relevant outputs are then transmitted along configured edges
  **only if an LLM inside the node validates the output**, 
  ensuring any downline nodes receive the inputs they require.

Taken together, this creates a cohesive sequence of steps where every node’s activity is traceable and well-defined.

## Example Use Case
Consider a text processing workflow consisting of three nodes:
- **Node A** – A prompt guard that takes care of maintaining the security of the conversation.
- **Node B** – Preprocesses raw input (e.g., cleaning or formatting the data).
- **Node C** – Performs advanced analysis (such as syntactic tagging) using a language model.
- **Node D** – Generates a refined summary based on the output of Node B.
By configuring edges to relay the outputs properly (A → B → C), the system processes the input in a step-wise manner, producing a final summary in a transparent and modular fashion.

## Benefits
1. **Modular Architecture**
Nodes remain self-contained, promoting easier maintenance and future enhancements.
2. **Flexible Configuration**
With behavior driven by prompts, updates can be applied quickly by adjusting configuration files or prompt definitions.
3. **Transparent Data Flow**
Directed edges clarify the relationships and data dependencies between tasks, simplifying debugging and monitoring.
4. **Scalable Design**
Additional nodes can be seamlessly introduced to the graph. Because each node is responsible for a single task, new functionality can be integrated without upheaval to the rest of the system.


---
# Graph Data Structure


## 1. Main Graph Structure


The overall structure, referred to as the “Graph,” incorporates four key collections:
- **models**: Holds a set of model specifications.
- **systems**: Holds a set of system prompts or configurations.
- **nodes**: Represents discrete points or vertices in the graph, each often tied to a particular model or prompt.
- **edges**: Represents connections or flows between nodes,


```json
{
  "models": [],
  "systems": [],
  "nodes": [],
  "edges": []
}
```

```yaml
    models:
    systems:
    nodes:
    edges:
```
---


## 2. Models

Each item in the **models** collection represents a configuration defining how to handle and interact with various tasks or services. These items include:
- **llm** (string): Identifies the model or service type.
- **version** (string): Optionally specifies a version or variant of the model.
- **aws_config** (object): Contains properties for region, access credentials, and other relevant fields if the model interactions rely on certain services.
    - **region** (string): The designated region for a service.
    - **access_key** (string): The access credential used to authenticate.
    - **secret_key** (string): The secret credential paired with the access key.

- **host** (string or null): A location or endpoint for the service.
- **api_key** (string or null): An additional key for authentication or authorization purposes.

When a particular interaction does not require a given property (for instance, no host or access credentials), that field can be left blank or set null.


```json
{
  "models": [
    {
      "llm": "bedrock",
      "version": "",
      "aws_config": {
        "region": "",
        "access_key": "",
        "secret_key": ""
      },
      "host": null,
      "api_key": null
    },
    {
      "llm": "ollama",
      "version": "model:version",
      "aws_config": null,
      "host": "http://localhost:11434",
      "api_key": null
    },
    {
      "llm": "gpt",
      "version": "",
      "aws_config": null,
      "host": null,
      "api_key": ""
    }
  ]
}
```

```yaml
models:
  - llm: bedrock
    version: ""
    aws_config:
      region: ""
      access_key: ""
      secret_key: ""
    host: null
    api_key: null
  - llm: ollama
    version: "model:version"
    aws_config: null
    host: "http://localhost:11434"
    api_key: null
  - llm: gpt
    version: ""
    aws_config: null
    host: null
    api_key: ""
```

---

## 3. Systems

Each item under **systems** represents some form of prompt or system directive. Different attributes may be used, 
depending on whether the prompt includes text for direct display, a file path to load, or a remote location:
- **text** (string): Contains textual instructions or content used directly.
- **path** (string): Points to a file or resource to read from the local environment.
- **url** (string): Points to an external resource to fetch remotely.

```json
{
  "systems": [
    {
      "text": ""
    },
    {
      "path": ""
    },
    {
      "url": ""
    }
  ]
}
```

```yaml
    systems:
      - text: |
          log text prompt
        path: null
        url: null
      - text: null
        path: ""
        url: null
      - text: null
        path: null
        url: ""
```

---

## 4. Nodes
Each item under **nodes** represents a discrete unit of processing or interaction in the overall structure. 
A node typically specifies:

- **id** (string): A unique identifier.
- **llm** (numeric index): References which model configuration or service this node uses.
- **temperature** (numeric): A floating-point adjustment for variability or sampling in content generation.
- **show** (boolean): Indicates if this node output is visible or is only used within the graph.
- **prompt** (object): Holds details about the prompt used for this node, typically referencing:
    - **system** (numeric index): Points to one of the previously defined system template entries.
    - **placeholders** (object): Carries key-value pairs that fill the prompt’s structure.  The default ones are:
        - **post** (string): Content to be processed.
        - **history** (string): Prior interactions or context.
        - **citations** (string): External references or accreditation.
        - **user_role** (string): Indicates the role or perspective of a user.
        - **assistant_role** (string): Indicates the role or perspective of an assistant or automated agent.
      



```json
{
  "nodes": [
    {
      "id": "",
      "llm": 0,
      "temperature": 0.0,
      "show": true,
      "prompt": {
        "system": 0,
        "placeholders": {
          "post": "",
          "history": "",
          "citations": "",
          "user_role": "",
          "assistant_role": ""
        }
      }
    }
  ]
}
```


```yaml
nodes:
  - id: ""
    llm: 0
    temperature: 0.0
    show: true
    prompt:
      system: 0
      placeholders:
        post: ""
        history: ""
        citations: ""
        user_role: ""
        assistant_role: ""
```

## 5. Edges

Each item under **edges** establishes a connection from one node to another. 
Along with source and target identifiers, an **attrib** property describes the nature or the role of that connection. 
The fields include:

- **source** (string): Origin node’s identifier.
- **target** (string): Destination node’s identifier.
- **attrib** (string): Provides a label for the relationship or the type of data flowing along this connection (e.g., “chat_messages,” “user_message,” “assistant_message,” “history,” etc.).

Edges allow the overall structure to represent sequences, dependencies, or flows of content and logic between nodes.


```json
{
  "edges": [
    {
      "source": "node_id_a",
      "target": "node_id_b",
      "attrib": "chat_messages"
    },
    {
      "source": "node_id_b",
      "target": "node_id_c",
      "attrib": "user_message"
    },
    {
      "source": "node_id_c",
      "target": "node_id_d",
      "attrib": "assistant_message"
    },
    {
      "source": "node_id_c",
      "target": "node_id_d",
      "attrib": "history"
    },
    {
      "source": "node_id_e",
      "target": "node_id_f",
      "attrib": "empty"
    }
  ]
}
```

```yaml
edges:
  - source: node_id_a
    target: node_id_b
    attrib: chat_messages
  - source: node_id_b
    target: node_id_c
    attrib: user_message
  - source: node_id_c
    target: node_id_d
    attrib: assistant_message
  - source: node_id_c
    target: node_id_d
    attrib: history
  - source: node_id_e
    target: node_id_f
    attrib: empty
```

### ⚠️ CRITICAL REQUIREMENT
The graph compilation starts from the first node of the graph.
So if the connections of the edges start from Node A, the new user message must be inserted
in the post field in the node placeholder before passing the configuration to the compiler.


