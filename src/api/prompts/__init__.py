def compile_prompt(system_prompt: str, user_prompt: str, **kwargs) -> list[dict]:
    """Compile a prompt by substituting {{variable}} placeholders and returning chat messages."""
    def substitute(text: str) -> str:
        for key, value in kwargs.items():
            text = text.replace(f"{{{{{key}}}}}", str(value))
        return text

    messages = [
        {"role": "system", "content": substitute(system_prompt)},
        {"role": "user", "content": substitute(user_prompt)},
    ]
    return messages
