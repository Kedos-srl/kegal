import logging
from pathlib import Path

import yaml
import json
from graph_compiler import GraphCompiler, GraphData, LlmResponse
from log.ke_logging import custom_file_handler

custom_file_handler()


def compile_from_dict(config: dict):
    """Create instance from dictionary"""
    graph =  GraphCompiler(GraphData(**config))
    return graph()


# COMMPILE JSON
def compile_from_json(json_src_, message: str | None = None):
    """
    Create instance from JSON
    """
    try:
        config = json.load(json_src_)
        if not config:
            raise ValueError("Empty JSON configuration file")
        if message:
            config["nodes"][0]["prompt"]["placeholders"]["post"] = message
        return compile_from_dict(config)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON configuration file: {str(e)}")
    except TypeError as e:
        raise ValueError(f"Invalid configuration structure: {str(e)}")



def compile_from_json_file(json_file_path_: Path, message: str | None = None):
    """
    Create a GraphCompiler instance from a JSON description file.
    """
    if not isinstance(json_file_path_, Path):
        raise TypeError("json_file_path must be a Path object")

    try:
        with json_file_path_.open('r', encoding='utf-8') as json_file:
            return compile_from_json(json_file, message=message)
    except FileNotFoundError:
        raise FileNotFoundError(f"JSON file not found: {json_file_path_}")
    except Exception as e:
        raise RuntimeError(f"Error reading JSON file {json_file_path_}: {str(e)}")


# COMMPILE YAML

def compile_from_yaml(yaml_src_, message: str | None = None):
    """Create instance from YAML"""
    try:
        config = yaml.safe_load(yaml_src_)
        if message:
            config["nodes"][0]["prompt"]["placeholders"]["post"] = message
        if not config:
            raise ValueError("Empty YAML configuration file")
        return compile_from_dict(config)
    except yaml.YAMLError as yaml_err:
        raise ValueError(f"Failed to parse YAML configuration: {yaml_err}")
    except Exception as e:
        raise ValueError(f"Error creating GraphCompiler from config: {e}")



def compile_from_yaml_file(yaml_file_path_: Path, message: str | None = None):
    """
    Create a GraphCompiler instance from a YAL description file.
    """
    if not isinstance(yaml_file_path_, Path):
        raise TypeError("yaml_file_path must be a Path object")

    try:
        with yaml_file_path_.open('r', encoding='utf-8') as yaml_file:
            return compile_from_yaml(yaml_file, message=message)
    except FileNotFoundError:
        raise FileNotFoundError(f"YAML file not found: {yaml_file_path_}")
    except Exception as e:
        raise RuntimeError(f"Error reading YAML file {yaml_file_path_}: {str(e)}")

