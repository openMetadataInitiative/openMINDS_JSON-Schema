import glob
import json
import os
import shutil
from pathlib import Path
from typing import List

from git import Repo, GitCommandError

def clone_sources():
    if os.path.exists("sources"):
        shutil.rmtree("sources")
    Repo.clone_from("https://github.com/openMetadataInitiative/openMINDS.git", to_path="sources", depth=1)

def find_embedded_schema(version, class_name):
    """
    Searches a returns a pre-generated (embedded) JSON Schema file for a given class name and version.
    """
    directory = Path(f"./target/schemas/{version}/")
    #camel_case = class_name[:1].lower() + class_name[1:]

    # Search for exact filename matches
    for case in [class_name]:
        for file_path in directory.glob(f"**/{case}.schema.json"):
            return json.loads(file_path.read_text())
    return None

def find_source_schema_path(version, class_name):
    """
    Locates the source JSON Schema file path for a given class name and version.
    """
    directory = Path(f"./sources/schemas/{version}/")
    camel_case = class_name[:1].lower() + class_name[1:]

    # Search for exact filename matches
    for case in [camel_case, class_name]:
        for file_path in directory.glob(f"**/{case}.schema.omi.json"):
            return os.path.abspath(file_path)
    return None

class SchemaLoader(object):

    def __init__(self):
        self._root_directory = os.path.realpath(".")
        self.schemas_sources = os.path.join(self._root_directory, "sources", "schemas")

    def get_schema_versions(self) -> List[str]:
        return os.listdir(self.schemas_sources)

    def find_schemas(self, version:str) -> List[str]:
        return glob.glob(os.path.join(self.schemas_sources, version, f'**/*.schema.omi.json'), recursive=True)
