from burrito.sandbox.sandbox import Sandbox


sandbox_manager = Sandbox()
def get_sandbox() -> Sandbox:
    """FastAPI dependency to provide the singleton Sandbox instance."""
    return sandbox_manager
