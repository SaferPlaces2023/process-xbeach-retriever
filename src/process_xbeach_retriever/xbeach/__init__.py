from .xbeach_retriever import _XBeachRetriever

import importlib.util
if importlib.util.find_spec('pygeoapi') is not None:
    from .xbeach_retriever_processor import XBeachRetrieverProcessor
