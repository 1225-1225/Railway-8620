import sys
sys.path.insert(0, '/ragflow')

# Read the file
with open('/ragflow/rag/svr/task_executor_refactor/task_context.py', 'r') as f:
    content = f.read()

# Fix parser_config property
old1 = '''    @property
    def parser_config(self) -> Dict[str, Any]:
        """Document-level parser configuration."""
        return self._task.get("parser_config", {})'''

new1 = '''    @property
    def parser_config(self) -> Dict[str, Any]:
        """Document-level parser configuration."""
        val = self._task.get("parser_config", {})
        if isinstance(val, str):
            try:
                import json as _json
                val = _json.loads(val)
            except Exception:
                val = {}
        return val'''

if old1 in content:
    content = content.replace(old1, new1)
    print('Patched parser_config')
else:
    print('WARNING: parser_config patch target not found!')

# Fix kb_parser_config property
old2 = '''    @property
    def kb_parser_config(self) -> Dict[str, Any]:
        """Knowledge base level parser configuration."""
        return self._task.get("kb_parser_config", {})'''

new2 = '''    @property
    def kb_parser_config(self) -> Dict[str, Any]:
        """Knowledge base level parser configuration."""
        val = self._task.get("kb_parser_config", {})
        if isinstance(val, str):
            try:
                import json as _json
                val = _json.loads(val)
            except Exception:
                val = {}
        return val'''

if old2 in content:
    content = content.replace(old2, new2)
    print('Patched kb_parser_config')
else:
    print('WARNING: kb_parser_config patch target not found!')

# Write back
with open('/ragflow/rag/svr/task_executor_refactor/task_context.py', 'w') as f:
    f.write(content)

print('Patch applied successfully')
