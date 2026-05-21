"""Embedding 字段匹配引擎。

将 LLM 产出的自然语言数据需求，与用户配置的数据字典进行语义匹配。
使用 sentence-transformers 本地模型，模型需自行下载。

模型下载（有网络时执行一次即可）：
    python3 -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-zh-v1.5')"
"""

import logging
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# 相似度阈值
_TH_HIGH = 0.82   # available
_TH_LOW = 0.50    # missing 临界线


class FieldMatcher:
    """数据字典字段匹配器。

    Usage:
        matcher = FieldMatcher(data_dict)
        ok = matcher.build_index()
        if ok:
            results = matcher.match(requirements)
    """

    def __init__(self, data_dict: dict[str, Any]):
        self._data_dict = data_dict
        self._model = None
        self._model_loaded = False
        # 索引：所有字段的 (table_name, field_name, description, embedding)
        self._field_index: list[tuple[str, str, str, np.ndarray]] = []

    def build_index(self, model_name: str = 'BAAI/bge-small-zh-v1.5') -> bool:
        """构建字段 embedding 索引。

        将数据字典中所有字段编码为向量。
        首次加载模型时会自动下载（约 33MB）。
        如果网络不通或模型未下载，返回 False 并记录警告。

        Args:
            model_name: sentence-transformers 模型名

        Returns:
            True 索引构建成功，False 失败（不影响后续使用）
        """
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(model_name)
        except Exception as e:
            logger.warning('Embedding 模型加载失败（可稍后下载）: %s', e)
            print(f'  [factor_generator] Embedding 模型加载失败，跳过匹配: {e}')
            print(f'  有网络时执行以下命令下载模型：')
            print(f'    python3 -c "from sentence_transformers import SentenceTransformer;'
                  f' SentenceTransformer(\'{model_name}\')"')
            return False

        self._field_index.clear()
        texts: list[str] = []
        for table in self._data_dict.get('tables', []):
            tname = table['name']
            for field in table.get('fields', []):
                fname = field['name']
                desc = field.get('description', '')
                texts.append(f'{fname} {desc}')
                self._field_index.append((tname, fname, desc, np.array([], dtype=np.float32)))

        embeddings = self._model.encode(texts, normalize_embeddings=True)
        for i, emb in enumerate(embeddings):
            self._field_index[i] = (
                self._field_index[i][0],
                self._field_index[i][1],
                self._field_index[i][2],
                emb,
            )

        self._model_loaded = True
        return True

    def match(self, requirements: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """匹配数据需求到数据字典字段。

        如果索引未构建成功，所有需求标为 missing。

        Args:
            requirements: LLM 产出的数据需求列表
                每项格式: {description: "自然语言描述", ...}

        Returns:
            标注后的需求列表，每项附加:
                status: "available" | "missing" | "need_derive"
                matched_table: 匹配的表名或 None
                matched_field: 匹配的字段名或 None
                confidence: 相似度分值或 None
        """
        if not self._model_loaded or not self._field_index:
            return [
                {**r, 'status': 'missing', 'matched_table': None,
                 'matched_field': None, 'confidence': None}
                for r in requirements
            ]

        results: list[dict[str, Any]] = []
        texts = [r.get('description', '') for r in requirements]
        if not any(texts):
            return []

        req_embs = self._model.encode(texts, normalize_embeddings=True)

        for i, req in enumerate(requirements):
            req_desc = texts[i]
            if not req_desc:
                results.append({
                    **req, 'status': 'missing',
                    'matched_table': None, 'matched_field': None,
                    'confidence': None,
                })
                continue

            # 取字段索引的所有 embedding 组成矩阵
            field_embs = np.array([f[3] for f in self._field_index])
            scores = np.dot(field_embs, req_embs[i])

            best_idx = int(np.argmax(scores))
            best_score = float(scores[best_idx])
            best_table, best_field, best_desc = self._field_index[best_idx][:3]

            if best_score >= _TH_HIGH:
                status = 'available'
            elif best_score >= _TH_LOW:
                status = 'need_derive'
            else:
                status = 'missing'
                best_table = None
                best_field = None
                best_score = None

            results.append({
                **req, 'status': status,
                'matched_table': best_table, 'matched_field': best_field,
                'confidence': best_score,
                'matched_desc': best_desc if status != 'missing' else None,
            })

        return results
