# 向量检索与 bge-m3 ONNX 只读调查（2026-11-02）

调查范围：`backend/data/models/bge-m3-onnx`、`app/services/embedding/encoder.py`、`app/db/vector_store.py`、定稿建索引与三处检索调用点、配置与依赖。
本调查未修改任何小说数据，未调用 LLM，未安装依赖。

## 1. 模型目录实际内容

| 文件 | 大小 | 内容 |
|---|---:|---|
| `backend/data/models/bge-m3-onnx/model.onnx` | 25 B | `YOUTHINK_ONNX_PLACEHOLDER` |
| `backend/data/models/bge-m3-onnx/tokenizer.json` | 25 B | `YOUTHINK_ONNX_PLACEHOLDER` |
| `backend/data/models/bge-m3-onnx/manifest.json` | 75 B | `{"model_id": "bge-m3-onnx-int8", "source": "modelscope", "dimension": 1024}` |

**结论：当前目录里没有真实的 bge-m3 ONNX 权重和分词器，三个文件都是占位内容。**

### ONNX 读取结果

用 `onnxruntime.InferenceSession(..., providers=["CPUExecutionProvider"])` 读取：

```text
InvalidProtobuf [ONNXRuntimeError] : 7 : INVALID_PROTOBUF :
Load model from backend/data/models/bge-m3-onnx/model.onnx failed:Protobuf parsing failed.
```

因此无法从真实模型读出输入名、输出名、输出形状。按 bge-m3 常见 ONNX 导出约定，实现需要兼容：

- 输入：`input_ids`、`attention_mask`，以及可选的 `token_type_ids`；
- 输出：若为 3 维 `last_hidden_state`（`[batch, seq, hidden]`），取 `[CLS]` 即 `[:, 0, :]`；
- 输出：若为 2 维 `sentence_embedding` / `dense_vecs`（`[batch, hidden]`），直接使用；
- 隐层维度应为 1024；最后做 L2 归一化。

池化依据：bge-m3 的 dense embedding 约定是取首 token（`[CLS]`）的 last hidden state 并做 L2 归一化，维度 1024。实现会在加载时按输出 rank 自动判定：rank=3 用 CLS 池化，rank=2 视为模型已输出句向量；若维度不是 1024 直接报错，不截断、不补零。

### 分词器

- `tokenizer.json` 不是合法 JSON，`tokenizers.Tokenizer.from_file` 报 `expected value at line 1 column 1`。
- 目录内没有 `sentencepiece.bpe.model`、`special_tokens_map.json`、`config.json`。
- `tokenizers` 库可以直接消费 bge-m3 的 `tokenizer.json`；当前文件不可用。

### 依赖

`backend/requirements.txt` 已包含：

```text
onnxruntime>=1.17.0
tokenizers>=0.15.0
numpy>=1.26.0
```

当前环境已安装：

| 包 | 版本 |
|---|---|
| onnxruntime | 1.17.1 |
| tokenizers | 0.22.2 |
| numpy | 1.26.4 |
| transformers | 5.12.1（未使用） |

**不需要安装新的 Python 依赖。需要的是把真实的 `model.onnx` 和 `tokenizer.json` 放进模型目录。**

## 2. 当前编码方式（哈希近似）

`backend/app/services/embedding/encoder.py`：

- `EMBEDDING_DIM = 256`。
- `encode_text_sync(text)`：
  1. `jieba.cut_for_search` 切词；
  2. 每个词做 MD5，取前 2 字节映射到 256 维桶，第 3 字节决定正负号；
  3. 字符 bigram 再做一次同样映射；
  4. 最后整体 L2 归一化。
- `cosine_similarity(a, b)` 只是两向量点积，长度不同直接返回 0。

因此现有“向量”是**词/字符哈希桶**，不是语义模型；维度 256。

## 3. 向量库格式

`backend/app/db/vector_store.py`，文件位置：

```text
backend/data/<novel_uid>/vectors/chunks.json
```

每条记录（`VectorChunkRecord`）：

```text
chunk_id, chapter_id, chapter_sort_order, scene_id, character_ids,
location_id, story_time, embedding_model_id, text, vector, source_hash
```

当前作品 `novel_cf825d92d2d9` 的实测：

- 记录数：13
- 维度：全部 256
- `embedding_model_id`：全部 `bge-m3-onnx-int8`（名字写着 bge-m3，实际是哈希向量）
- 没有维度/版本字段；只能靠 `vector` 长度推断。

读写方式：整体读 JSON、整体写临时文件后 `replace`。检索时逐条做长度相等才点积，但旧代码在长度不等时返回 0，不会报“需要重建”。

## 4. 建索引调用点

`backend/app/services/memory/finalizer.py`：

- 定稿 `finalize_chapter` 在事务外先调用 `_prepare_chapter_chunks`，逐片调用 `encode_text_sync`。
- 切片：`split_text_chunks(content, chunk_size=650, overlap=100)`，按段落换行尽量切在边界。
- 每片记录章节 sort、`story_time`、第一个场景的 `scene_id`、该章所有 POV/在场人物、第一个地点、正文 hash。
- 事务内 `upsert_chapter_chunks` 发布整章向量。
- `rebuild_all_indexes` 先 `clear_all_vectors()`，再对 `status='final' AND continuity_review_required=0` 的章节重建并重做 FTS。

`_index_chapter_chunks_and_fts` 这个名字在当前代码中不存在；实际入口是 `finalize_chapter` + `_prepare_chapter_chunks`，以及 `rebuild_all_indexes`。

## 5. 检索调用点

### 5.1 写作上下文（assembler）

`backend/app/services/context/assembler.py`：

- 仅在 `vectors/chunks.json` 存在时检索。
- 查询词：`combined_beats.strip() or ch.title`，即章节梗概 + 场景节拍。
- 用 `encode_text_sync` 编码查询。
- `search_vectors(top_k=3, max_chapter_sort=本章 sort-0.0001, allowed_chapter_hashes=… )`。
- 只保留 `status='final'`、无需一致性复审、`content_hash` 与库中 `source_hash` 一致的章节，且排除本章和上一章。
- `filter_history_hits` 再排除与上一章尾部/本章已写内容有 20 字连续重叠的片段。
- 每条截断 260 字，写入 `rag_history` 块。
- **这条链路没有 FTS**；向量不可用时最多就是没有 RAG 块，目前不会提示原因。

### 5.2 记忆混合检索（retriever）

`backend/app/services/rag/retriever.py`：

- 查询编码同样走 `encode_text_sync`。
- 向量召回 `top_k*2`，FTS5 召回 `top_k*2`，用 RRF `1/(60+rank)` 融合。
- 返回 `embedding_model_mismatch`，前端提示“请重建全书索引”。
- 但只比较 `embedding_model_id` 字符串；旧库写的也是 `bge-m3-onnx-int8`，所以当前永远显示“一致”，尽管实际是 256 维哈希。

### 5.3 一致性审查（consistency）

`backend/app/services/memory/consistency.py`：

- 把待查正文切成 650 字片段，每段编码后检索定稿章节，取分数 ≥ 阈值的片段作为“检查表 F”参考。
- 整段包在 `try/except` 里，异常时静默返回空字符串；模型缺失不会提示作者。

## 6. 配置

- `backend/app/core/config.py`：`models_dir = data_dir / "models"`，`bge_m3_dir = models_dir / "bge-m3-onnx"`。
- `backend/app/db/init_schema.py` 默认设置：`embedding.model_id = "bge-m3-onnx-int8"`，`download_source = "modelscope"`。
- 没有 `max_length`、batch size、device 配置。
- `backend/app/services/embedding/manager.py` 的“下载”只写 25 字节占位文件并把状态标成 ready，这正是目录里占位文件的来源；它没有真正下载模型。

## 7. 改造要点

1. 新增 `OnnxEmbeddingEncoder`：惰性加载、全局单例、CPU、`max_length=512`（环境变量可配）、批量、1024 维、L2 归一化；加载/推理失败抛 `EmbeddingModelUnavailable`，不退回哈希。
2. 每条向量写 `embedding_model_id`、`embedding_dim`、`embedding_version`；旧记录缺字段时按向量长度推断，256 维视为旧哈希版本。
3. 检索前检查维度/版本；不兼容章节跳过向量召回并返回“需要重建索引”，FTS 照常。
4. assembler 在模型不可用时把 `rag_history` 块写成“向量模型不可用：…”，并把原因加入 `warnings`。
5. 设置接口 `/settings/embedding` 用实际文件校验和最近一次加载错误报告状态，不再只看文件是否存在。
6. 重建脚本默认 dry-run；`--apply` 先备份到 `backend/data/_loop_backups/embedding_<时间戳>/`，只处理已定稿章节。

## 8. 当前阻塞

真实模型文件缺失，因此：

- 无法实测真实 ONNX 的输入/输出名与输出形状；
- 无法生成 1024 维新向量；
- 无法完成“新编码 top3 对比”；
- 重建脚本 dry-run 可以统计章节与切片数，但 `--apply` 会在编码阶段明确失败，直到放入真实模型。

以上结论均来自只读检查，未改数据。

## 9. 真实 ONNX 模型复核（2026-11-02）

### 9.1 目录与文件差异

实际放入的文件并不在 `backend/data/models/bge-m3-onnx/` 的 BAAI 完整导出布局里：

| 目录 | 文件 | 大小（字节） | 结论 |
|---|---|---:|---|
| `data/models/bge-m3-onnx/` | `bge-m3.onnx` | 316,132 | AMD Ryzen AI NPU 导出，静态 `[1,512]` |
| | `bge-m3.onnx.data` | 2,271,019,008 | 与 `bge-m3.onnx` 相邻，可加载 |
| | `configuration.json` | 64 | 无 `tokenizer.json` |
| `data/models/bge-m3/onnx/` | `model.onnx` | 724,923 | BAAI/bge-m3 完整 ONNX 导出 |
| | `model.onnx_data` | 2,266,820,608 | 与 `model.onnx` 相邻，可加载 |
| | `tokenizer.json` | 17,082,821 | 可用 |
| | `sentencepiece.bpe.model` | 5,069,051 | 可用 |

`models/bge-m3-onnx` 不是本次代码期望的目录布局：它的输出是 `last_hidden_state` + `pooler_output`，缺少 tokenizer，且输入被固定为 `[1,512]`。因此配置解析改为优先使用 `models/bge-m3/onnx`（同时存在 `model.onnx` 与 `tokenizer.json` 时），并保留 `YOUTHINK_EMBEDDING_MODEL_DIR` 环境变量覆盖；两者都不满足时回退到 `models/bge-m3-onnx`，随后由真实加载/编码校验明确报错。

原调查记录的 `models/bge-m3-onnx/manifest.json`（75 B，`int8`）当前已不存在；实际可用的 `models/bge-m3/onnx/manifest.json` 已按真实编码器写入：

```json
{
  "embedding_model_id": "bge-m3-onnx-fp32",
  "embedding_version": "bge-m3-onnx-fp32-1024-v1",
  "dimension": 1024,
  "dtype": "fp32",
  "pooling": "cls",
  "normalize": true,
  "preferred_output": "sentence_embedding"
}
```

该文件位于被 `.gitignore` 忽略的 `backend/data/` 下，仅随本地模型存在，不进入提交。

### 9.2 输入、输出与池化

ONNX Runtime CPU 实际加载 `models/bge-m3/onnx/model.onnx`：

- 输入：
  - `input_ids`：`[batch_size, sequence_length]`，`tensor(int64)`
  - `attention_mask`：`[batch_size, sequence_length]`，`tensor(int64)`
- 输出：
  - `token_embeddings`：`[batch_size, sequence_length, 1024]`
  - `sentence_embedding`：`[batch_size, 1024]`

编码器优先选择名字含 `sentence` / `dense` / `pool` 的输出，因此取 `sentence_embedding`；没有此类输出时才选二维输出，否则取第一个输出并对三维结果做 CLS 池化。

对同一句“江边的黄昏照在旧码头上”实测：

- `sentence_embedding` 的 L2 范数：`0.9999999403953552`
- 手工对 `token_embeddings[:, 0, :]` 做 L2 归一化后，与 `sentence_embedding` 的余弦相似度：`1.0`
- 两者最大绝对差：`7.45e-9`

结论：`sentence_embedding` 就是 CLS 位置池化后再做 L2 归一化的结果，直接使用与 BGE-M3 约定完全一致，且避免把 `[batch, seq, 1024]` 误当作句向量。

### 9.3 实测耗时与内存

同一进程内实测（CPUExecutionProvider，Windows 11，Python 3.12）：

| 项目 | 数值 |
|---|---:|
| tokenizer 加载 | 531.7 ms |
| ONNX session 加载 | 2,187.4 ms |
| RSS 基线 | 48.4 MB |
| 加载后 RSS | 1,533.3 MB |
| 加载增量 | 1,484.9 MB |
| 首次编码后 RSS | 1,695.0 MB |
| 编码增量 | 161.8 MB |
| 单句推理（15 token，热态 4 次中位数） | 40.84 ms |
| 8 条批量推理（含 1 条约 400+ token 长段，padding 后） | 5,887.22 ms |
| 8 条批量折合单条 | 735.9 ms |

批量耗时主要受最长样本 padding 和长序列注意力影响；章节片段通常在 650 字、数百 token 量级，重建时应按实际切片长度评估，不能直接用单句 40 ms 乘以条数。

### 9.4 真实模型集成测试

`tests/test_embedding_onnx.py` 的真实模型用例不再 skip，验证：

- 输出 1024 维且 L2 范数为 1；
- 以下四句两两余弦相似度：

| 句子对 | 相似度 |
|---|---:|
| 江边黄昏 ↔ 傍晚江水落日 | 0.7160 |
| 江边黄昏 ↔ 新学期开学 | 0.4599 |
| 江边黄昏 ↔ 股市上涨 | 0.3628 |
| 傍晚江水落日 ↔ 新学期开学 | 0.4273 |
| 傍晚江水落日 ↔ 股市上涨 | 0.4398 |
| 新学期开学 ↔ 股市上涨 | 0.5028 |

语义相近的“江边黄昏 / 傍晚江水落日”相似度最高（0.7160），明显高于它与“股市上涨”的 0.3628；测试同时断言该相似度是四句所有配对中的最大值。

### 9.5 与旧索引的关系

现有 `vectors/chunks.json` 仍为 13 条 256 维旧哈希向量，元数据缺失时按维度推断为 `hash-ngram-256-v1`。新编码器使用 `bge-m3-onnx-fp32` / `bge-m3-onnx-fp32-1024-v1`，两者维度、版本、模型 id 均不兼容；旧索引仍必须重建，不能与新索引混用。dry-run 与新旧 top3 对比见 `PROGRESS.md` 的“真实模型复验”一节。
