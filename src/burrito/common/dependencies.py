from burrito.handlers.generation_handler import AdapterGenerationHandler

generation_handler_singleton = AdapterGenerationHandler()


def get_generation_handler() -> AdapterGenerationHandler:
    return generation_handler_singleton
