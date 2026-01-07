from burrito.handlers.generation_handler import AdapterGenerationHandler
from burrito.handlers.sandbox_handler import SandboxHandler
from burrito.handlers.browser_handler import BrowserHandler

generation_handler_singleton = AdapterGenerationHandler()
sandbox_handler_singleton = SandboxHandler()
browser_handler_singleton = BrowserHandler()


def get_generation_handler() -> AdapterGenerationHandler:
    return generation_handler_singleton


def get_sandbox_handler() -> SandboxHandler:
    return sandbox_handler_singleton


def get_browser_handler() -> BrowserHandler:
    return browser_handler_singleton
