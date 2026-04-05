SUMMARY_PROMPT = """
【Task】
请对以下对话做简洁摘要。

【保留内容】
- 用户目标
- 关键限制条件
- 已经确认的结论
- 后续对话仍然需要依赖的上下文

【Constraints】
1. 不要保留寒暄、重复表述和无关细节
2. 摘要尽量短，但不能丢掉关键限制条件
3. 输出自然语言摘要，不要输出 JSON

对话：
{dialog_text}
"""


EXTRACT_MEMORY_PROMPT = """
【Task】
分析以下对话，提取用户明确表达的、具有一定稳定性的个人偏好或长期信息。
只输出 JSON，不要解释。

【Extraction Rules】
1. 只提取稳定信息，不要提取一次性任务、临时问题或当前会话短期目标
2. 如果信息不明确，不要猜测
3. 如果没有可提取内容，返回空 JSON
4. 不要把用户当前这一次的问题主题误当成长期偏好
5. 如果一个字段没有可靠信息，就不要输出该字段

字段：
- name
- preference
- dietary_restriction
- hobby
- work_style
- language_preference

对话：
{dialog}
"""
