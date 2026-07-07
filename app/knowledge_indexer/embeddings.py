import hashlib
import math
from collections.abc import Sequence


class HashEmbedding:
    """本地确定性 embedding。

    MVP 初始化阶段避免依赖外部模型服务；后续可替换为 DeepSeek/Qwen/OpenAI embedding。
    """

    def __init__(self, dimension: int = 128):
        self.dimension = dimension

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        tokens = self._tokens(text)

        for token in tokens:
            digest = hashlib.md5(token.encode("utf-8")).hexdigest()
            index = int(digest[:8], 16) % self.dimension
            vector[index] += 1.0

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]

    def embed_many(self, texts: list[str]) -> list[Sequence[float]]:
        return [self.embed(text) for text in texts]

    def _tokens(self, text: str) -> list[str]:
        cleaned = "".join(char for char in text if not char.isspace())
        tokens = list(cleaned)
        tokens.extend(cleaned[index:index + 2] for index in range(max(len(cleaned) - 1, 0)))
        tokens.extend(cleaned[index:index + 3] for index in range(max(len(cleaned) - 2, 0)))
        return tokens
