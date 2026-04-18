# RAG Offline Evaluation

这套评测模块是**离线评估框架**，不会接入当前线上接口，也不会影响现有部署。

## 目标

先提供一个最小可用版本，支持 3 层评测：

1. 检索层
2. 生成层
3. 端到端层

其中：

- 检索层默认可用
- `LLM as Judge` 为可选开关
- `RAGAs` 为可选开关，没有安装依赖时自动跳过

## 数据集格式

评测集使用 JSON 文件，结构如下：

```json
{
  "dataset_name": "rag-eval-dev",
  "version": "v1",
  "samples": [
    {
      "sample_id": "sample-001",
      "question": "系统支持哪些文档格式？",
      "question_type": "fact",
      "gold_answer": "系统支持 txt、md、pdf、docx 文档上传。",
      "gold_chunks": [
        {
          "filename": "README.md",
          "content_substring": "txt / md / pdf / docx"
        }
      ],
      "metadata": {
        "source": "manual"
      }
    }
  ]
}
```

仓库里还提供了一个静态 schema，方便后续校验：

- `backend/evaluation/examples/rag_eval_dataset.schema.json`

### `gold_chunks` 标注说明

每个 `gold_chunk` 支持这些字段：

- `filename`
- `content_substring`
- `chunk_index`

建议至少标：

- `filename`
- `content_substring`

这样即使 chunk 重新切分，只要核心片段还在，评测也还能继续用。

## 输出结果

评测输出是一个 JSON 报告，包含：

- 总体 summary
- 每条样本的检索指标
- 每条样本的生成指标
- 每条样本的端到端指标
- 模型生成答案
- 实际检索上下文

## 运行方式

在 `backend` 目录下执行：

```bash
python -m evaluation.cli --dataset evaluation/examples/rag_eval_dataset.example.json
```

启用 `LLM as Judge`：

```bash
python -m evaluation.cli \
  --dataset evaluation/examples/rag_eval_dataset.example.json \
  --use-llm-judge
```

启用 `RAGAs`：

```bash
python -m evaluation.cli \
  --dataset evaluation/examples/rag_eval_dataset.example.json \
  --use-ragas
```

## 可选依赖

如果你需要跑 `RAGAs`，请额外安装：

```bash
pip install -r backend/requirements-eval.txt
```

## 当前实现边界

这是最小可用版本，目前重点是：

- 代码结构先搭起来
- 数据格式先固定下来
- 支持后续继续补数据、补指标、补报告对比

暂时没有做：

- 前端评测页面
- 自动化数据标注
- 多版本实验对比面板
- 人工评测工作台
