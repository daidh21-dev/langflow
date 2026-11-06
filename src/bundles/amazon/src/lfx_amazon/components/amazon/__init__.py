"""Lazy component re-exports for the ``amazon`` bundle.

Mirrors the pre-extraction layout of ``lfx.components.amazon`` so saved
flows that referenced the module-level class
(e.g. ``lfx.components.amazon.<Class>``) keep resolving via the
migration table after rewrite to
``lfx_amazon.components.amazon.<Class>``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from lfx.utils.lazy_import import import_mod

if TYPE_CHECKING:
    from .agentcore_browser_tool import AgentCoreBrowserToolComponent
    from .agentcore_code_interpreter import AgentCoreCodeInterpreterComponent
    from .agentcore_gateway_mcp import AgentCoreGatewayMCPComponent
    from .agentcore_guardrails import AgentCoreGuardrailsComponent
    from .agentcore_knowledge_base import AgentCoreKnowledgeBaseComponent
    from .agentcore_memory import AgentCoreMemoryComponent
    from .agentcore_runtime_invoker import AgentCoreRuntimeInvokerComponent
    from .agentcore_s3_packager import AgentCoreS3ArtifactPackagerComponent
    from .amazon_bedrock_converse import AmazonBedrockConverseComponent
    from .amazon_bedrock_embedding import AmazonBedrockEmbeddingsComponent
    from .amazon_bedrock_model import AmazonBedrockComponent
    from .s3_bucket_uploader import S3BucketUploaderComponent

_dynamic_imports = {
    "AgentCoreBrowserToolComponent": "agentcore_browser_tool",
    "AgentCoreCodeInterpreterComponent": "agentcore_code_interpreter",
    "AgentCoreGatewayMCPComponent": "agentcore_gateway_mcp",
    "AgentCoreGuardrailsComponent": "agentcore_guardrails",
    "AgentCoreKnowledgeBaseComponent": "agentcore_knowledge_base",
    "AgentCoreMemoryComponent": "agentcore_memory",
    "AgentCoreRuntimeInvokerComponent": "agentcore_runtime_invoker",
    "AgentCoreS3ArtifactPackagerComponent": "agentcore_s3_packager",
    "AmazonBedrockComponent": "amazon_bedrock_model",
    "AmazonBedrockConverseComponent": "amazon_bedrock_converse",
    "AmazonBedrockEmbeddingsComponent": "amazon_bedrock_embedding",
    "S3BucketUploaderComponent": "s3_bucket_uploader",
}

__all__ = [
    "AgentCoreBrowserToolComponent",
    "AgentCoreCodeInterpreterComponent",
    "AgentCoreGatewayMCPComponent",
    "AgentCoreGuardrailsComponent",
    "AgentCoreKnowledgeBaseComponent",
    "AgentCoreMemoryComponent",
    "AgentCoreRuntimeInvokerComponent",
    "AgentCoreS3ArtifactPackagerComponent",
    "AmazonBedrockComponent",
    "AmazonBedrockConverseComponent",
    "AmazonBedrockEmbeddingsComponent",
    "S3BucketUploaderComponent",
]


def __getattr__(attr_name: str) -> Any:
    if attr_name not in _dynamic_imports:
        msg = f"module {__name__!r} has no attribute {attr_name!r}"
        raise AttributeError(msg)
    try:
        result = import_mod(attr_name, _dynamic_imports[attr_name], __spec__.parent)
    except (ModuleNotFoundError, ImportError, AttributeError) as e:
        msg = f"Could not import {attr_name!r} from {__name__!r}: {e}"
        raise AttributeError(msg) from e
    globals()[attr_name] = result
    return result


def __dir__() -> list[str]:
    return list(__all__)
