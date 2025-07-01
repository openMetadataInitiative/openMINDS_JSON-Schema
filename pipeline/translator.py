import json
import os.path
from typing import List, Optional, Dict

from pipeline.utils import find_embedded_schema, find_source_schema_path

class JSONSchemaBuilder(object):
    property_name = None
    required_properties = []

    def __init__(self, schema_file_path:str, root_path:str):
        _relative_path_without_extension = schema_file_path[len(root_path)+1:].replace(".schema.omi.json", "").split("/")
        self.version = _relative_path_without_extension[0]
        self.relative_path_without_extension = _relative_path_without_extension[1:]
        with open(schema_file_path, "r") as schema_f:
            self._schema_payload = json.load(schema_f)

    def _target_file_without_extension(self) -> str:
        return os.path.join(self.version, "/".join(self.relative_path_without_extension))

    def _resolve_string_property(self, property: dict) -> Dict:
        string_property_spec = {}
        if "_formats" in property and property["_formats"]:
            if len(property["_formats"]) == 1:
                string_property_spec["format"] = property["_formats"][0]
                string_property_spec["type"] = property["type"]
                if self.property_name not in self.required_properties:
                    string_property_spec["type"] = [string_property_spec["type"], "null"]
            elif len(property["_formats"]) > 1:
                string_property_spec["anyOf"] = []
                for format in property["_formats"]:
                    string_property_spec["anyOf"].append({
                        "type": property["type"],
                        "format": format
                    })
                if self.property_name not in self.required_properties:
                    string_property_spec["anyOf"].append({
                        "type": "null"
                    })
        else:
            string_property_spec["type"] = property["type"]
            if self.property_name not in self.required_properties:
                string_property_spec["type"] = [string_property_spec["type"], "null"]
        if "pattern" in property and property["pattern"]:
            string_property_spec["pattern"] = property["pattern"]
        if "minLength" in property and property["minLength"]:
            string_property_spec["minLength"] = property["minLength"]
        if "maxLength" in property and property["maxLength"]:
            string_property_spec["maxLength"] = property["maxLength"]
        return string_property_spec

    def _resolve_number_property(self, property: dict) -> Dict:
        if self.property_name not in self.required_properties:
            number_property_spec = {"type": [property["type"], "null"]}
        else:
            number_property_spec = {"type": property["type"]}
        if "multipleOf" in property and property["multipleOf"]:
            number_property_spec["multipleOf"] = property["multipleOf"]
        if "minimum" in property and property["minimum"]:
            number_property_spec["minimum"] = property["minimum"]
        if "maximum" in property and property["maximum"]:
            number_property_spec["maximum"] = property["maximum"]
        return number_property_spec

    def _resolve_embedded_schema(self, embedded_type:str):
        """
        Retrieves the embedded JSON Schema for the given type.

        If a pre-generated embedded schema is found, it is returned directly.
        Otherwise, the function attempts to locate the source schema and generates the embedded schema file.
        """
        embedded = find_embedded_schema(self.version, embedded_type.split('/')[-1])
        if embedded:
            return embedded
        else:
            embedded_path = find_source_schema_path(self.version, embedded_type.split('/')[-1])
            if embedded_path:
                return JSONSchemaBuilder(embedded_path, os.path.join(os.path.realpath("."), "sources", "schemas")).build()
        return  None

    def _resolve_object_property(self, property: dict):
        object_property_spec = {}
        if "_embeddedTypes" in property and property["_embeddedTypes"]:
            if len(property["_embeddedTypes"]) == 1:
                embedded_schema = self._resolve_embedded_schema(property['_embeddedTypes'][0])
                del embedded_schema['$schema']
                object_property_spec = embedded_schema

            elif len(property["_embeddedTypes"]) > 1:
                object_property_spec["anyOf"] = []
                for embedded_type in property["_embeddedTypes"]:
                    embedded_schema = self._resolve_embedded_schema(embedded_type)
                    del embedded_schema['$schema']
                    object_property_spec["anyOf"].append(embedded_schema)
                if self.property_name not in self.required_properties:
                    object_property_spec["anyOf"].append({
                        "type": "null"
                    })
        elif "_linkedTypes" in property and property["_linkedTypes"]:
            object_property_spec["type"] = "object"
            object_property_spec["if"] = {
                "required": ["@type"]
            }
            if self.property_name not in self.required_properties:
                object_property_spec["then"] = {
                    "properties": {
                        "@id": {
                            "type": "string",
                            "format": "iri"
                        },
                        "@type": {
                            "type": ["string", "null"],
                            "format": "iri",
                            "enum": property["_linkedTypes"] + [ "null" ]
                        }},
                    "required": ["@id"]
                }
            else:
                object_property_spec["then"] = {
                    "properties": {
                        "@id": {
                            "type": "string",
                            "format": "iri"
                        },
                        "@type": {
                            "type": "string",
                            "format": "iri",
                            "enum": property["_linkedTypes"]
                        }},
                    "required": ["@id"]
                }
            object_property_spec["else"] = {
                "properties": {
                    "@id": {
                        "type": "string",
                        "format": "iri"
                    }
                },
                "required": ["@id"]
            }

        return object_property_spec

    def _resolve_array_property(self, property):
        array_property_spec = {"type": property["type"]}
        if "items" in property and property["items"]:
            if "type" in property["items"] and property["items"]["type"]:
                if property["items"]["type"] == "string":
                    array_property_spec["items"] = self._resolve_string_property(property["items"])
                elif property["items"]["type"] in ["number", "float", "integer"]:
                    array_property_spec["items"] = self._resolve_number_property(property["items"])
                else:
                    array_property_spec["items"] = {"type": "UNKNOWN_TYPE"}
        else:
            array_property_spec["items"] = self._resolve_object_property(property)
        if "minItems" in property and property["minItems"]:
            array_property_spec["minItems"] = property["minItems"]
        if "maxItems" in property and property["maxItems"]:
            array_property_spec["maxItems"] = property["maxItems"]
        if "uniqueItems" in property and property["uniqueItems"]:
            array_property_spec["uniqueItems"] = property["uniqueItems"]

        return array_property_spec

    def _translate_property_specifications(self, property) -> Dict:
        self._translated_prop_spec = {}

        prop_description = property["description"] if "description" in property else "null"
        self._translated_prop_spec["description"] = prop_description

        self._translated_prop_spec["name"] = property["name"]

        prop_type = property["type"] if "type" in property else "object"

        if prop_type == "string":
            self._translated_prop_spec.update(self._resolve_string_property(property))
        elif prop_type in ["number", "float", "integer"]:
            self._translated_prop_spec.update(self._resolve_number_property(property))
        elif prop_type == "object":
            self._translated_prop_spec.update(self._resolve_object_property(property))
        elif prop_type == "array":
            self._translated_prop_spec.update(self._resolve_array_property(property))
        else:
            self._translated_prop_spec["type"] = "UNKNOWN_TYPE"

        return self._translated_prop_spec

    def translate(self):
        # set required properties
        required_prop = self._schema_payload["required"] if "required" in self._schema_payload else []
        self.required_properties = required_prop
        required_prop.extend(["@id", "@type"])
        # set description
        description = self._schema_payload['description'] if "description" in self._schema_payload else "null"

        self._translated_schema = {
            "$id": f"{self._schema_payload['_type']}?format=json-schema",
            "$schema": "http://json-schema.org/draft-07/schema#",
            "description": description,
            "properties": {
                "@id": {
                    "description": "Metadata node identifier.",
                    "type": "string"
                },
                "@type": {
                    "const": self._schema_payload['_type'],
                    "description": "Metadata schema identifier.",
                    "type": "string"
                }
            },
            "required": sorted(required_prop),
            "title": self._schema_payload['name'],
            "type": "object"
        }

        if "properties" in self._schema_payload and self._schema_payload["properties"]:
            for prop_name, prop_spec in self._schema_payload["properties"].items():
                self.property_name = prop_name
                self._translated_schema["properties"][prop_name] = self._translate_property_specifications(prop_spec)

    def build(self):
        target_file = os.path.join("target", "schemas", f"{self._target_file_without_extension()}.schema.json")
        os.makedirs(os.path.dirname(target_file), exist_ok=True)

        self.translate()

        with open(target_file, "w") as target_file:
            target_file.write(json.dumps(self._translated_schema, indent=2, sort_keys=True))

        return self._translated_schema
