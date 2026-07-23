"""
AdapterFactory — returns the right ContextAdapter for each content type.
"""
from apps.interfaces.adapter import ContextAdapter


class AdapterFactory:
    @staticmethod
    def get(type: str) -> ContextAdapter:
        match type:
            case "doc" | "file":  # "file" is the directive name; both map to DocAdapter
                from apps.implementations.adapters.doc_adapter import DocAdapter
                return DocAdapter()

            case "code":
                from apps.implementations.adapters.code_adapter import CodeAdapter
                return CodeAdapter()

            case _:
                raise ValueError(f"Unknown context adapter type: {type!r}")
