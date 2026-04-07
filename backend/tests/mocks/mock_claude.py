class MockClaudeClient:
    def __init__(self, chunks: list[str] | None = None):
        self.chunks = chunks or ["测试", "输出"]

    async def stream(self):
        for chunk in self.chunks:
            yield chunk

