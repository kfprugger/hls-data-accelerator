from typing import List, Type, TypeVar, Union
import requests

T = TypeVar('T')

def handle_response(response: requests.Response, cls: Type[T]) -> Union[T, None]:
    if response.status_code == 200:
        try:
            data = response.json()
            return cls(data)
        except Exception as e:
            print(e)
            return cls({})
    elif response.status_code == 201:
        try:
            data = response.json()
            return cls(data)
        except Exception as e:
            print(e)
            return cls({})
    elif response.status_code == 202:
        return cls({})
    else:
        handle_failure_code(response)

def handle_list_response(response: requests.Response, cls: Type[T]) -> Union[List[T], None]:
    if response.status_code == 200:
        try:
            data = response.json()
        except Exception as e:
            return cls({})
        data = response.json()
        if "value" in data:
            return [cls(item) for item in data["value"]]
        if isinstance(data, list):
            return [cls(item) for item in data]
    
    elif response.status_code == 201:
        try:
            data = response.json()
        except Exception as e:
            return cls({})
        # print(data)
        if "value" in data:
            return [cls(item) for item in data["value"]]
        if isinstance(data, list):
            return [cls(item) for item in data]
    elif response.status_code == 202:
        try:
            data = response.json()
        except Exception as e:
            return cls({})
        return data
    else:
        handle_failure_code(response)

def handle_failure_code(response: requests.Response):
    if response.status_code == 404:
        print("Error: Resource not found.")
    elif response.status_code == 400:
        print(f"Error: Bad request, {response.content}")
    elif response.status_code == 500:
        print("Error: Server error.")
    else:
        print(f"Error: Received unexpected status code {response.status_code}: {response.content}")