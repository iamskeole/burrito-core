import re
from typing import Dict, Any, Union

class QueryProcessor:
    """
    Evaluates JSON-based logic against text blocks.
    Used by browser_scan to allow the model to filter content programmatically.
    """

    @staticmethod
    def evaluate(text: str, query: Union[str, Dict[str, Any]]) -> bool:
        # 1. Simple String Case
        if isinstance(query, str):
            return query.lower() in text.lower()

        # 2. Complex Dictionary Case
        op = query.get("op", "contains").lower()
        
        if op == "contains":
            val = query.get("value", "")
            return val.lower() in text.lower()
        
        elif op == "regex":
            pattern = query.get("value", "")
            try:
                return re.search(pattern, text, re.IGNORECASE | re.MULTILINE) is not None
            except re.error:
                return False

        elif op == "starts_with":
            val = query.get("value", "")
            return text.strip().lower().startswith(val.lower())

        elif op == "and":
            conditions = query.get("conditions", [])
            return all(QueryProcessor.evaluate(text, cond) for cond in conditions)

        elif op == "or":
            conditions = query.get("conditions", [])
            return any(QueryProcessor.evaluate(text, cond) for cond in conditions)

        elif op == "not":
            condition = query.get("condition", {})
            return not QueryProcessor.evaluate(text, condition)

        return False

    @staticmethod
    def filter_markdown(markdown_content: str, query: Union[str, Dict]) -> str:
        """
        Splits markdown into logical blocks (paragraphs/headers) 
        and returns only those matching the query.
        """
        if not markdown_content:
            return "No content to scan."

        # Split by double newline to preserve paragraph structure
        blocks = markdown_content.split('\n\n')
        matching_blocks = []
        
        for i, block in enumerate(blocks):
            clean_block = block.strip()
            if not clean_block:
                continue

            if QueryProcessor.evaluate(clean_block, query):
                matching_blocks.append(f"--- Match {len(matching_blocks)+1} (Block {i}) ---\n{clean_block}")

        if not matching_blocks:
            return "No matches found for the given criteria."

        header = f"## Scan Results (Found {len(matching_blocks)} matches)\nCriteria: {query}\n\n"
        return header + "\n\n".join(matching_blocks)