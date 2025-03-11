import importlib
import json
from typing import Any, Dict
from pydantic import BaseModel

from pathlib import Path
import sys

TOOLS_DIR = Path(__file__).parent / "tools"


class ToolConfig(BaseModel):
    tool: str
    parameters: dict[str, Any]


class ToolsManager:
    def __init__(self):
        self.loaded_modules = {}

    def load_module(self, module_name: str) -> Any:
        """
        Dynamically load a Python module from TOOLS_DIR.

        Args:
            module_name: Name of the module to load
        Returns:
            Loaded module object
        """
        if module_name not in self.loaded_modules:
            try:
                # Add TOOLS_DIR to Python path temporarily
                import sys
                if str(TOOLS_DIR) not in sys.path:
                    sys.path.insert(0, str(TOOLS_DIR))

                # Try to load the module
                self.loaded_modules[module_name] = importlib.import_module(module_name)

            except ImportError as e:
                raise ImportError(f"Failed to load module {module_name} from {TOOLS_DIR}: {str(e)}")
        return self.loaded_modules[module_name]

    def execute_from_config(self, config: ToolConfig) -> Any:
        """
        Execute a function based on configuration.

        Args:
            config: Dictionary containing:
                   - tool: string in format "module_name.function_name"
                   - parameters: dictionary of parameters to pass to the function

        Returns:
            Result of the function execution
        """
        if not isinstance(config, ToolConfig):
            raise ValueError("Config must be a ToolConfig object")


        # Split module and function names
        if not config.tool or config.tool == "":
            raise ValueError("Tool is empty")
        try:
            module_name, func_name = config.tool.rsplit(".", 1)
        except ValueError:
            raise ValueError(f"Tool must be in format 'module_name.function_name {config.tool}")

        # Load module
        module = self.load_module(module_name)

        # Get function
        if not hasattr(module, func_name):
            raise AttributeError(f"Function {func_name} not found in module {module_name}")
        func = getattr(module, func_name)

        # Get parameters
        parameters = config.parameters

        # Execute function
        return func(**parameters)

