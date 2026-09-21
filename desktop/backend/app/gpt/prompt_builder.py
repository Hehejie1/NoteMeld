from app.db import note_style_dao
from app.gpt.prompt import BASE_PROMPT
from app.services.note_style_prompt_builder import build_note_style_instruction

note_formats = [
    {'label': '目录', 'value': 'toc'},
    {'label': '原片跳转', 'value': 'link'},
    {'label': '原片截图', 'value': 'screenshot'},
    {'label': 'AI总结', 'value': 'summary'}
]

note_styles = [
    {'label': '知识卡片', 'value': 'knowledge_card'},
    {'label': '深度研究', 'value': 'deep_research'},
    {'label': '快速摘要', 'value': 'quick_summary'},
    {'label': '行动清单', 'value': 'action_list'},
    {'label': '视频解析', 'value': 'video_analysis'},
    {'label': '网页提炼', 'value': 'web_digest'},
    {'label': '工具网站', 'value': 'tool_website'},
    {'label': 'AI 对话沉淀', 'value': 'ai_conversation'},
    {'label': '会议纪要', 'value': 'meeting_minutes'}
]


# 生成 BASE_PROMPT 函数
def generate_base_prompt(title, segment_text, tags, _format=None, style=None, extras=None):
    # 生成 Base Prompt 开头部分
    prompt = BASE_PROMPT.format(
        video_title=title,
        segment_text=segment_text,
        tags=tags
    )

    # 添加用户选择的格式
    if _format:
        prompt += "\n" + "\n".join([get_format_function(f) for f in _format])

    # 根据用户选择的笔记风格添加描述
    if style:
        style_template = note_style_dao.get_style_template(style)
        if style_template:
            prompt += "\n" + build_note_style_instruction(style_template)
        else:
            prompt += "\n" + get_style_format(style)

    # 添加额外内容
    if extras:
        prompt += f"\n{extras}"
    return prompt


# 获取格式函数
def get_format_function(format_type):
    format_map = {
        'toc': get_toc_format,
        'link': get_link_format,
        'screenshot': get_screenshot_format,
        'summary': get_summary_format
    }
    return format_map.get(format_type, lambda: '')()


# 风格描述的处理
def get_style_format(style):
    style_map = {
        'knowledge_card': '1. **知识卡片**: 结论先行，提炼关键发现、知识整理、可执行建议和待追问，适合沉淀为个人知识库。',
        'deep_research': '2. **深度研究**: 完整保留背景、观点、证据、案例和延伸问题，适合长视频、长网页、论文和报告。',
        'quick_summary': '3. **快速摘要**: 只保留一句话结论、关键要点和少量值得保留的信息。',
        'action_list': '4. **行动清单**: 把内容转化为目标、行动项、验收标准、风险和注意事项。',
        'meeting_minutes': '5. **会议纪要**: 结构化呈现会议概览、议题讨论、决议和行动项。',
        'video_analysis': '6. **视频解析**: 融合字幕、画面语境、评论弹幕线索，提炼视频主旨和关键片段。',
        'web_digest': '7. **网页提炼**: 提炼网页观点、引用线索、链接来源和适合沉淀的知识点。',
        'tool_website': '8. **工具网站**: 面向工具型网站，提炼原始链接、可解决的问题、适用场景、使用限制和推荐触发词，方便后续按任务召回并打开原站。',
        'ai_conversation': '9. **AI 对话沉淀**: 沉淀问题背景、关键决策、方案、待执行任务和可复用提示。',
    }
    return style_map.get(style, '')


# 格式化输出内容
def get_toc_format():
    return '''
    9. **目录**: 自动生成一个基于 `##` 级标题的目录。不需要插入原片跳转
    '''


def get_link_format():
    return '''
    10. **原片跳转**: 为每个主要章节添加时间戳，使用格式 `*Content-[mm:ss]`。 
    重要：**始终**在章节标题前加上 `*Content` 前缀，例如：`AI 的发展史 *Content-[01:23]`。一定是标题在前 插入标记在后
    '''


def get_screenshot_format():
    return '''
11. **原片截图**:你收到的截图一般是一个网格，网格的每张图片就是一个时间点，左上角会包含时间mm:ss的格式，请你结合我发你的图片插入截图提示，请你帮助用户更好的理解视频内容，请你认真的分析每个图片和对应的转写文案，插入最合适的内容来备注用户理解，请一定按照这个格式 返回否则系统无法解析：
- 格式：`*Screenshot-[mm:ss]`

    '''


def get_summary_format():
    return '''
    12. **AI总结**: 在笔记末尾加入简短的AI生成总结,并且二级标题 就是 AI 总结 例如 ## AI 总结。
    '''
