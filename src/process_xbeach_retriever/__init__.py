from dotenv import load_dotenv
load_dotenv()

from .xbeach import _XBeachRetriever
import importlib.util
if importlib.util.find_spec('pygeoapi') is not None:
    from .xbeach import XBeachRetrieverProcessor

from .main import run_xbeach_retriever
from .utils.strings import parse_event
