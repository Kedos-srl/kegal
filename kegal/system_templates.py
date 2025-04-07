import urllib.request
from urllib.error import URLError, HTTPError

from pathlib import Path
from string import Template

from .graph_data import SystemPrompt




class SystemStringTemplate(Template):

    def substitute_placeholders(self, placeholders_: dict) -> str:
        # Validate input
        if not isinstance(placeholders_, dict):
            raise TypeError("placeholders_ must be a dictionary")

        # Filter out None values to prevent 'None' strings in output
        cleaned_placeholders = {
            k: str(v) if v is not None else ''
            for k, v in placeholders_.items()
        }

        try:
            return self.safe_substitute(**cleaned_placeholders)
        except ValueError as e:
            raise ValueError(f"Invalid placeholder values: {e}")

class SystemTemplates:
    """
     Handles initialization of system prompts, validating and loading them from text, file, or URL.

     :param self: Reference to the current instance of the class.
     :param systems_: A list of `SystemPrompt` instances containing the information for each system.
     :raises ValueError: If a system template contains neither valid text, path, nor URL.
    """

    def __init__(self, systems_: list[SystemPrompt]):
        self.systems: list[SystemStringTemplate] = []
        for system in systems_:
            if system.text is not None:
                self.systems.append(SystemStringTemplate(system.text))
            elif system.path is not None:
                file_path = Path(system.path)
                if file_path.is_file():
                    try:
                        with file_path.open("r", encoding="utf-8") as f:
                            text = f.read()
                        # Load file content to `text`
                        self.systems.append(SystemStringTemplate(text))
                    except (OSError, IOError) as e:
                        print(f"Failed to load file {system.path}: {e}")
            elif system.url is not None:
                try:
                    with urllib.request.urlopen(system.url) as response:
                        text = response.read().decode("utf-8")
                        self.systems.append(text)
                except (HTTPError, URLError) as e:
                    print(f"Failed to fetch URL {system.url}: {e}")
            else:
                raise ValueError("Invalid system template")

    def __getitem__(self, index: int):
        try:
            return self.systems[index]
        except IndexError:
            raise IndexError(f"Index {index} is out of range. The valid indices are 0 to {len(self.systems) - 1}.")
        except TypeError:
            raise TypeError(f"Invalid index type {type(index).__name__}. Index must be an integer or slice.")
