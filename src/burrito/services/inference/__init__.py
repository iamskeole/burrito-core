from .inference_service_hosted import generate_hosted
from .inference_service_native import generate_native

__all__ = [
    "generate_hosted",
    "generate_native",
]
