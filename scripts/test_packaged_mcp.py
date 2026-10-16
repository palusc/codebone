"""Speak real MCP stdio to the packaged bridge and query a live indexed project."""
import asyncio
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from src.config import Config, find_free_port
from src.providers import FastFallbackProvider
from src.windows_runtime import DesktopRuntime


async def main():
    executable = str(Path(sys.argv[1]).resolve())
    os.environ['CODEBONE_NO_MCP_PATCH'] = '1'
    with tempfile.TemporaryDirectory(prefix='codebone-mcp-test-') as folder:
        root = Path(folder)
        project = root / 'project'
        project.mkdir()
        (project / 'billing.py').write_text('def process_invoice():\n    return "invoice paid"\n', encoding='utf-8')
        config = Config(root / 'data/config.json')
        config.set('server_port', find_free_port(18053))
        runtime = DesktopRuntime(config)
        runtime.service.provider = FastFallbackProvider()
        try:
            runtime.start()
            runtime.open_project(project)
            params = StdioServerParameters(command=executable, env={**os.environ, 'CODEBONE_PORT': str(runtime.server.port)})
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    assert 'cb' in {tool.name for tool in tools.tools}
                    result = await session.call_tool('cb', {})
                    assert result.content and not result.isError
                    text = '\n'.join(getattr(item, 'text', '') for item in result.content)
                    assert 'billing.py' in text and 'not reachable' not in text, text
                    print('Packaged MCP initialized, listed tools and retrieved indexed billing.py')
        finally:
            runtime.close()


if __name__ == '__main__':
    asyncio.run(asyncio.wait_for(main(), timeout=60))
