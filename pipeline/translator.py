import json
import os.path
from typing import List, Optional, Dict

# Name of the definition that holds the "embedded" variant of each schema.
# Embedded instances have no "@id"; standalone instances must have one.
EMBEDDED_DEFINITION = "embedded"


def _embedded_ref(type_iri: str) -> str:
    return f"{type_iri}?format=json-schema#/definitions/{EMBEDDED_DEFINITION}"


# A pattern instead of "format" for UUIDs, since "uuid" is not a draft-07 format.
UUID_PATTERN = r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"


def _linked_id_spec() -> Dict:
    # References to linked instances may be given either as IRI or as UUID.
    return {
        "type": "string",
        "anyOf": [
            {"format": "iri"},
            {"pattern": UUID_PATTERN}
        ]
    }


class JSONSchemaBuilder(object):

    def __init__(self, schema_file_path:str, root_path:str):
        _relative_path_without_extension = schema_file_path[len(root_path)+1:].replace(".schema.omi.json", "").split("/")
        self.version = _relative_path_without_extension[0]
        self.relative_path_without_extension = _relative_path_without_extension[1:]
        with open(schema_file_path, "r") as schema_f:
            self._schema_payload = json.load(schema_f)

    def _target_file_without_extension(self) -> str:
        return os.path.join(self.version, "/".join(self.relative_path_without_extension))

    def _resolve_string_property(self, property) -> Dict:
        string_property_spec = {}
        if "_formats" in property and property["_formats"]:
            if len(property["_formats"]) == 1:
                string_property_spec["format"] = property["_formats"][0]
                string_property_spec["type"] = property["type"]
            elif len(property["_formats"]) > 1:
                string_property_spec["anyOf"] = []
                for format in property["_formats"]:
                    string_property_spec["anyOf"].append({
                        "type": property["type"],
                        "format": format
                    })
        else:
            string_property_spec["type"] = property["type"]
        if "pattern" in property and property["pattern"]:
            string_property_spec["pattern"] = property["pattern"]
        if "minLength" in property and property["minLength"]:
            string_property_spec["minLength"] = property["minLength"]
        if "maxLength" in property and property["maxLength"]:
            string_property_spec["maxLength"] = property["maxLength"]
        return string_property_spec

    def _resolve_number_property(self, property) -> Dict:
        number_property_spec = {"type": property["type"]}
        if "multipleOf" in property and property["multipleOf"]:
            number_property_spec["multipleOf"] = property["multipleOf"]
        if "minimum" in property and property["minimum"]:
            number_property_spec["minimum"] = property["minimum"]
        if "maximum" in property and property["maximum"]:
            number_property_spec["maximum"] = property["maximum"]
        return number_property_spec

    def _resolve_object_property(self, property):
        object_property_spec = {}
        if "_embeddedTypes" in property and property["_embeddedTypes"]:
            # Embedded instances are validated against the "embedded" variant
            # of the target schema, which does not require "@id".
            if len(property["_embeddedTypes"]) == 1:
                object_property_spec["type"] = "object"
                object_property_spec["$ref"] = _embedded_ref(property['_embeddedTypes'][0])
            elif len(property["_embeddedTypes"]) > 1:
                object_property_spec["anyOf"] = []
                for embedded_type in property["_embeddedTypes"]:
                    object_property_spec["anyOf"].append({
                        "type": "object",
                        "$ref": _embedded_ref(embedded_type)
                    })
        elif "_linkedTypes" in property and property["_linkedTypes"]:
            object_property_spec["type"] = "object"
            object_property_spec["if"] = {
                "required": ["@type"]
            }
            object_property_spec["then"] = {
                "properties": {
                    "@id": _linked_id_spec(),
                    "@type": {
                        "type": "string",
                        "format": "iri",
                        # remove duplicates while keeping the original order
                        "enum": list(dict.fromkeys(property["_linkedTypes"]))
                    }},
                "required": ["@id"]
            }
            object_property_spec["else"] = {
                "properties": {
                    "@id": _linked_id_spec()
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

        prop_description = property["description"] if "description" in property else None
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
        # Required properties shared by both variants (no "@id" here).
        # Copy the list so the source payload is not mutated.
        required_prop = set(self._schema_payload.get("required") or [])
        required_prop.discard("@id")
        required_prop.add("@type")

        description = self._schema_payload.get("description")

        # The "embedded" variant: all properties and constraints, "@id" optional.
        embedded_schema = {
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
            "type": "object"
        }

        if "properties" in self._schema_payload and self._schema_payload["properties"]:
            for prop_name, prop_spec in self._schema_payload["properties"].items():
                embedded_schema["properties"][prop_name] = self._translate_property_specifications(prop_spec)

        # The root (standalone) variant: everything from "embedded" plus a required "@id".
        self._translated_schema = {
            "$id": f"{self._schema_payload['_type']}?format=json-schema",
            "$schema": "http://json-schema.org/draft-07/schema#",
            "allOf": [
                {"$ref": f"#/definitions/{EMBEDDED_DEFINITION}"}
            ],
            "definitions": {
                EMBEDDED_DEFINITION: embedded_schema
            },
            "required": ["@id"],
            "title": self._schema_payload['name'],
            "type": "object"
        }
        if description:
            self._translated_schema["description"] = description

    def build(self):
        target_file = os.path.join("target", "schemas", f"{self._target_file_without_extension()}.schema.json")
        os.makedirs(os.path.dirname(target_file), exist_ok=True)

        self.translate()

        with open(target_file, "w") as target_file:
            target_file.write(json.dumps(self._translated_schema, indent=2, sort_keys=True))