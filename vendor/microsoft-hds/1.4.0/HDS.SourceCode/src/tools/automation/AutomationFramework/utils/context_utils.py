
from typing import Any, Dict

def update_context(context: Dict, key: str, value: Any):
    context[key] = value

def get_value_from_context(name, context: Dict, kwargs, default: Any = None):
    if name in kwargs:
        # If the param name is found in kwargs, check to see if the stored value
        # is located in the context
        param_value = kwargs[name]
        if isinstance(param_value, str) and param_value in context:
            return context[param_value]
        return default
    elif name in context:
        return context[name]
    else:
        return default

def get_value(name: str, context: Dict, kwargs: Dict, default: Any = None):
    if name in context:
        return context[name]
    if name in kwargs:
        param_value = kwargs[name]
        if isinstance(param_value, str) and param_value.startswith("$") and param_value[1:] in context:
            return context[param_value[1:]]
        return param_value
    else:
        return default

def set_value(obj, path, value):
    """_summary_
    A helper function to update a value in a json object

    Args:
        obj (_type_): A json object
        path (_type_): A string representing the path to the value to be updated
        value (_type_): The value to be updated
    """
    keys = path.strip("$.").split(".")
    for key in keys[:-1]:
        if key.isdigit():
            key = int(key)
        if isinstance(obj, list):
            while len(obj) <= key:
                obj.append({})
            obj = obj[key]
        elif isinstance(obj, dict):
            if key not in obj:
                obj[key] = {}
            obj = obj[key]
        else:
            print(f"Path '{path}' does not exist in the JSON object.")
            return
    last_key = keys[-1]
    if last_key.isdigit():
        last_key = int(last_key)
    if isinstance(obj, list):
        while len(obj) <= last_key:
            obj.append({})
        obj[last_key] = value
    elif isinstance(obj, dict):
        obj[last_key] = value
    else:
        print(f"Path '{path}' does not exist in the JSON object.")
        return
    
def update_json(json_obj, edits):
    """_summary_

    Args:
        json_obj (_type_): A json object
        edits (_type_): A list of edits to apply to the object

    Example usage:
        input_json = {
            "name": "example",
            "items": [
                {"id": 1, "value": "item1"},
                {"id": 2, "value": "item2"}
            ],
            "nested": {
                "level1": {
                    "level2": {
                        "level3": "deep_value",
                        "list": [
                            {"id": 1, "value": "list_item1"},
                            {"id": 2, "value": "list_item2"}
                        ]
                    }
                }
            }
        }

        edits = [
            {"path": "$.name", "value": "updated_example"},
            {"path": "$.items.0.value", "value": "updated_item1"},
            {"path": "$.items.2.value", "value": "new_item"},
            {"path": "$.nested.level1.level2.level3", "value": "updated_deep_value"},
            {"path": "$.nested.level1.level2.list.0.value", "value": "updated_list_item1"},
            {"path": "$.new.nested.path", "value": "new_value"}
        ]

    Returns:
        _type_: _description_
    """
    for edit in edits:
        path = edit['path']
        value = edit['value']
        set_value(json_obj, path, value)
    
    return json_obj