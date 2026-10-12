class FakeLLM:
    """Returns scripted replies. Used by tests and the offline demo."""
    def __init__(self, replies):
        self.replies = list(replies)
        self.prompts = []                     # remembers what it was asked
    def complete(self, prompt):
        self.prompts.append(prompt)
        return self.replies.pop(0)
