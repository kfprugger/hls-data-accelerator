# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------
import html

class OpenAIClientUtils:
     
    @staticmethod
    def create_messages(user_query: str, messages: list) -> list:
        """
        Create a list of messages with the user message based on the provided prompt.

        Args:
            user_query (str): The user query.
            messages (list): A list of existing messages.

        Returns:
            list: A list of messages with the user message.
        """
        user_input = f"##INPUT##\n{html.escape(user_query)}\n##INPUT##"
        messages.append({"role": "user", "content": user_input})
        return messages

    @staticmethod
    def create_system_instructions(system_message: str, examples: list = None) -> list:
        """
        Create a list of messages with the system message and user message based on the provided prompt.

        Args:
            system_message (str): The system instruction message.
            examples (list, optional): A list of dictionaries containing user and assistant messages. Defaults to None.

        Returns:
            list: A list of messages with the system message and user message.
        """
        
        messages = [{"role": "system", "content": system_message}]  
        
        if examples:
            for example in examples:  
                user_message = example.get("user")  
                assistant_message = example.get("assistant")  
        
                if user_message:  
                    messages.append({"role": user_message['role'], "content": user_message['content']})  
                
                if assistant_message:  
                    messages.append({"role": "assistant", "content": str(assistant_message)})  
        
        return messages
  
    @staticmethod
    def process_completion_message(chat_completion) -> str:  
        """  
        Process the chat completion message and handle errors if any.  
    
        Args:  
            chat_completion: The chat completion object returned by the OpenAI API.  
    
        Returns:  
            str: The processed completion message or an error message.  
        """  
        choice = next(iter(chat_completion.choices), None)  
        return choice.message.content.strip()  
