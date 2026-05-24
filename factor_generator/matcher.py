"""Embedding 字段匹配引擎。

将 LLM 产出的自然语言数据需求，与用户配置的数据字典进行语义匹配。
使用 sentence-transformers，模型从 HuggingFace 镜像自动下载缓存。
"""

import logging
import os
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# 镜像地址（模型自动下载用）
_HF_MIRROR = 'https://hf-mirror.com'
# 默认模型
_DEFAULT_MODEL = 'TencentBAC/Conan-embedding-v1'

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
        self._field_index: list[tuple[str, str, str, np.ndarray]] = []

    def build_index(self, model_name: str | None = None) -> bool:
        """构建字段 embedding 索引。

        将数据字典中所有字段编码为向量。
        模型自动从镜像下载，首次调用会下载缓存，之后直接用。

        Args:
            model_name: 可选，指定模型名，默认 TencentBAC/Conan-embedding-v1

        Returns:
            True 索引构建成功，False 失败（不影响后续使用）
        """
        if model_name is None:
            model_name = _DEFAULT_MODEL

        # 设镜像环境变量，让 sentence-transformers 从镜像下载
        if 'HF_ENDPOINT' not in os.environ:
            os.environ['HF_ENDPOINT'] = _HF_MIRROR

        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(model_name)
        except Exception as e:
            logger.warning('Embedding 模型加载失败: %s', e)
            print(f'  [factor_generator] Embedding 模型加载失败，跳过匹配: {e}')
            print(f'  可手动设环境变量 HF_ENDPOINT=https://hf-mirror.com 后重试')
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
            requirements: LLM 产出的数据需求列表，每项 {description, ...}

        Returns:
            标注后的需求列表，每项附加 status / matched_table / matched_field / confidence
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
