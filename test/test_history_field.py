#!/usr/bin/env python
"""Test script to verify chat_history field is correctly parsed and used"""

import yaml
from pathlib import Path

# Carica il YAML direttamente
yaml_path = Path('test/graphs/rag_graph.yml')
with open(yaml_path, 'r') as f:
    graph_data = yaml.safe_load(f)

# Crea un oggetto semplice per simulare il grafo
class SimpleGraph:
    def __init__(self, data):
        self.chat_history = data.get('chat_history')
        self.nodes = []
        for node_data in data.get('nodes', []):
            self.nodes.append(SimpleNode(node_data))

class SimpleNode:
    def __init__(self, data):
        self.id = data.get('id')
        self.show = data.get('show')
        prompt_data = data.get('prompt')
        if prompt_data:
            self.prompt = SimplePrompt(prompt_data)
        else:
            self.prompt = None

class SimplePrompt:
    def __init__(self, data):
        self.chat_history = data.get('chat_history')
        self.user_message = data.get('user_message')
        self.retrieved_chunks = data.get('retrieved_chunks')
        self.template = data.get('template')

graph = SimpleGraph(graph_data)

print("=== Test Parsing del Grafo ===\n")

# Verifica che il grafo abbia chat_history globale
print(f"Chat history globale definita: {graph.chat_history is not None}")
if graph.chat_history:
    print(f"Chiavi chat_history: {list(graph.chat_history.keys())}")
print()

# Verifica ogni nodo
print("=== Analisi Nodi ===\n")
for node in graph.nodes:
    print(f"Node ID: {node.id}")
    print(f"  Ha prompt: {node.prompt is not None}")

    if node.prompt:
        print(f"  Prompt.chat_history: {node.prompt.chat_history}")
        print(f"  Prompt.user_message: {node.prompt.user_message}")
        print(f"  Prompt.retrieved_chunks: {node.prompt.retrieved_chunks}")

    print(f"  Show: {node.show}")
    print()

print("\n=== Verifica Logica _chat_history_check ===\n")

# Simula la logica del metodo _chat_history_check
for node in graph.nodes:
    would_enable_history = False

    if node.prompt is not None and node.prompt.chat_history is not None and graph.chat_history is not None:
        if node.prompt.chat_history in graph.chat_history:
            would_enable_history = True

    print(f"Node '{node.id}': history sarebbe {would_enable_history}")
    if node.prompt and node.prompt.chat_history:
        print(f"  -> chat_history configurata: '{node.prompt.chat_history}'")
        if graph.chat_history:
            print(f"  -> chiave esiste in graph.chat_history: {node.prompt.chat_history in graph.chat_history}")
    print()

print("\n✅ Test completato!")
