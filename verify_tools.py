import sys
import os
import json
import asyncio

# Ensure src is in python path
sys.path.append(os.path.join(os.getcwd(), 'src'))

from burrito.tools.browser.tool import BrowserTool
from burrito.tools.python.tool import PythonTool

async def verify():
    print("--- Verifying BrowserTool ---")
    bt = BrowserTool()
    schema = bt.get_tool_definition()
    print(f"Generated {len(schema)} tool actions.")
    # print(json.dumps(schema, indent=2))
    
    # Check for specific actions
    names = [s['function']['name'] for s in schema]
    print(f"Action names: {names}")
    
    expected = [
        "browser_search", "browser_open", "browser_find"
    ]
    missing = set(expected) - set(names)
    if missing:
        print(f"MISSING ACTIONS: {missing}")
    else:
        print("All expected BrowserTool actions present.")

    # Check Union type handling in scan_page - REMOVED
    # scan = next(s for s in schema if s['function']['name'] == 'browser_scan')
    # query_param = scan['function']['parameters']['properties']['query']
    # print(f"browser_scan 'query' param schema: {json.dumps(query_param)}")

    print("\n--- Verifying PythonTool ---")
    pt = PythonTool()
    py_schema = pt.get_tool_definition()
    print(f"Action names: {[s['function']['name'] for s in py_schema]}")

if __name__ == "__main__":
    asyncio.run(verify())
