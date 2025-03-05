# GraphData Schema Documentation

This document describes the high-level structure of the **GraphData** object and its primary components. The **GraphData** object serves as the main container, with the following sections explored in a logical sequence:
1. Models  
2. Systems  
3. Nodes  
4. Edges  

---

## 1. GraphData

**GraphData** is the top-level object in this schema, encompassing all essential parts of a graph-based system. It typically includes:

- A collection of model configurations (e.g., gpt, llama).  
- One or more system prompt templates.  
- A set of nodes that represent component entities within the graph.  
- A set of edges that define the relationships or data flows among nodes.

Users can reference and manipulate this object to create, validate, and interact with the overall graph structure.

---

## 2. Models

Within **GraphData**, the _models_ field is where you define one or more model configurations.  
- These configurations may include large language model details or external service credentials.  
- Each model configuration may reference additional parameters such as version information, API keys, or optional hosting details.  

### Example Key Attributes for a Model

- **llm**: Name of the large language model.  Supported id: "gpt", "ollama", "bedrock"
- **version**: id of the model. ex. "gpt-4o", llama3.1:8b-instruct-q4_K_M (ollama)   
- **host**: (Optional) Host server address for the model.  
- **api_key**: (Optional) Credential for authentication.  
- **aws_config**: (Optional) AWS configuration if services require AWS credentials.  

These fields can vary depending on the specific implementations and additional configuration requirements.

---

## 3. Systems

The _systems_ field in **GraphData** manages configurations for various system prompt templates used to guide an LLM (Large Language Model). 
These templates define the base instructions that direct the model's behavior and capabilities.

**Systems** might include:
- Instruction templates that define the model's general behavior.
- Parameters that control response style and tone.
- Custom configurations that optimize the model for specific tasks.

---

## 4. Nodes

The _nodes_ field in **GraphData** describes a list of node elements, each representing a component or step in your graph-based workflow. 
Nodes can hold any relevant configuration or processing instructions, such as:

- The name or identifier of the node.  
- The function or role the node serves (computation, data routing, etc.).  
- Any additional parameters necessary for that node’s operation.

Each node’s configuration may differ depending on its purpose within the graph.

---

## 5. Edges

The _edges_ field in **GraphData** defines connections between nodes. An edge typically includes:

- **source**: The originating node (by its identifier).  
- **target**: The destination node (by its identifier).  
- **attrib**: Specifies a particular form of output or data to be passed along (for example, messages, history, or other defined string values).

Edges are fundamental in illustrating how data flows from one node to another within your workflow.

---

## Conclusion

When using the **GraphData** object:

1. Define your **models** (like large language model configurations).  
2. Configure **systems** that might integrate with these models or external resources.  
3. Create **nodes** to represent key steps or components in your data pipeline or processing chain.  
4. Connect these nodes with **edges**, specifying how information traverses your graph.

With all these components in place, the **GraphData** structure empowers you to build a flexible graph-based framework for your application needs.