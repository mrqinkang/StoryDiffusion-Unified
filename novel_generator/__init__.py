#novel_generator/__init__.py
"""Novel Generator Package - 延迟导入避免循环依赖"""

def __getattr__(name):
    """延迟导入，避免 __init__ 执行时子模块互相递归导入"""
    import importlib
    _module_mapping = {
        "Novel_architecture_generate": "novel_generator.architecture",
        "Chapter_blueprint_generate": "novel_generator.blueprint",
        "get_last_n_chapters_text": "novel_generator.chapter",
        "summarize_recent_chapters": "novel_generator.chapter",
        "get_filtered_knowledge_context": "novel_generator.chapter",
        "build_chapter_prompt": "novel_generator.chapter",
        "generate_chapter_draft": "novel_generator.chapter",
        "finalize_chapter": "novel_generator.finalization",
        "enrich_chapter_text": "novel_generator.finalization",
        "import_knowledge_file": "novel_generator.knowledge",
        "clear_vector_store": "novel_generator.vectorstore_utils",
    }
    if name in _module_mapping:
        mod = importlib.import_module(_module_mapping[name])
        return getattr(mod, name)
    raise AttributeError(f"module 'novel_generator' has no attribute '{name}'")
